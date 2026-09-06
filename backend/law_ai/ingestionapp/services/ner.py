"""Optional NER pass over opinion text (BL-20260429-03).

The original follow-up asked for **Blackstone** NER behind a lazy-loading
shim. Blackstone cannot be reintroduced: it pins ``spacy==2.1.8`` against
this project's ``spacy>=3.8``, spaCy 2.1/thinc 7 publish no wheels for the
Python 3.12 base image, and upstream ICLRandD/Blackstone has been unmaintained
since 2024 (see docs/related-github-repos.md). What the item actually wanted —
entities beyond the two structured fields ``IngestionScout`` reads, without
paying a model load at import time — is delivered here on spaCy 3.

Design constraints this module honours:

* **Lazy** — the model is loaded on first use inside an ``lru_cache``, never
  at import. A suite that does not call :func:`extract_ner_entities` pays
  nothing, which is the "doesn't break test startup time" clause.
* **Off by default** — gated by ``ENABLE_NER`` (settings), so ingestion
  behaviour only changes when an operator opts in.
* **Never fatal** — a missing model or a spaCy error degrades to "no NER
  entities", because ingestion must not fail over an optional enrichment.
* **Never confidence-raising** — the caller merges these into the entity list
  only; ``scout._score`` does not read entities, so noisy generic NER on US
  case text can never push a document past the HITL threshold.

Enable it with::

    pip install -e ".[nlp]"     # installs the en_core_web_sm wheel
    ENABLE_NER=true
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from law_ai.core.schemas.extraction import Entity

logger = logging.getLogger("law_ai.ingestion.ner")

#: spaCy pipeline used when NER is enabled. Small on purpose (~12 MB).
MODEL_NAME = "en_core_web_sm"

#: Cap on the characters fed to the model — opinions run to hundreds of KB and
#: the tail of a slip opinion is boilerplate, not parties.
MAX_CHARS = 20_000

#: Cap on emitted entities so one long opinion cannot bloat a graph node.
MAX_ENTITIES = 50

#: spaCy label → Law AI ``Entity.label``. Anything unmapped is dropped rather
#: than smuggled in as OTHER: an unlabelled span is noise, not knowledge.
LABEL_MAP: dict[str, str] = {
    "PERSON": "PARTY",
    "ORG": "PARTY",
    "LAW": "STATUTE",
}

#: ORG spans that name a court are relabelled — "Supreme Court of Colorado" is
#: a COURT, not a party.
_COURT_HINTS = ("court", "tribunal", "circuit", "judiciary")


@lru_cache(maxsize=1)
def get_nlp() -> Any | None:
    """Load (once) the spaCy pipeline, or return ``None`` if unavailable.

    Cached so the model load happens at most once per process, and only when
    something actually asks for NER. Returns ``None`` — rather than raising —
    when spaCy or the model is not installed, so an operator who flips
    ``ENABLE_NER`` without installing the ``nlp`` extra gets a warning and
    structured-field extraction, not a broken ingestion run.
    """
    try:
        import spacy
    except Exception as exc:  # pragma: no cover — spacy is a declared dep
        logger.warning("NER disabled: spaCy import failed (%s)", type(exc).__name__)
        return None
    try:
        # Only the NER component is needed; skipping the rest roughly halves
        # both load time and per-document latency.
        return spacy.load(MODEL_NAME, exclude=["lemmatizer", "textcat"])
    except Exception as exc:
        logger.warning(
            "NER disabled: could not load %s (%s). Install it with "
            'pip install -e ".[nlp]"',
            MODEL_NAME,
            type(exc).__name__,
        )
        return None


def ner_enabled() -> bool:
    """Whether the optional NER pass is armed (``ENABLE_NER``, default False).

    Read at call time, not import time, so an operator (or a test) can flip
    the flag per run.
    """
    try:
        from law_ai.core.settings_proxy import settings_proxy

        return bool(getattr(settings_proxy, "ENABLE_NER", False))
    except Exception:  # pragma: no cover — settings always configured in app
        return False


def _label_for(span_label: str, text: str) -> str | None:
    mapped = LABEL_MAP.get(span_label)
    if mapped is None:
        return None
    if span_label == "ORG" and any(h in text.lower() for h in _COURT_HINTS):
        return "COURT"
    return mapped


def extract_ner_entities(text: str, *, limit: int = MAX_ENTITIES) -> list[Entity]:
    """Return NER entities for *text*; empty list when NER is off or unusable.

    Deduplicates on ``(text, label)`` and never raises.
    """
    if not text or not ner_enabled():
        return []
    nlp = get_nlp()
    if nlp is None:
        return []
    try:
        doc = nlp(text[:MAX_CHARS])
    except Exception as exc:
        logger.warning(
            "NER pass failed (%s); continuing without it", type(exc).__name__
        )
        return []

    seen: set[tuple[str, str]] = set()
    entities: list[Entity] = []
    for span in getattr(doc, "ents", []):
        cleaned = " ".join(str(span.text).split())
        if not cleaned:
            continue
        label = _label_for(str(span.label_), cleaned)
        if label is None:
            continue
        key = (cleaned, label)
        if key in seen:
            continue
        seen.add(key)
        entities.append(Entity(text=cleaned, label=label))  # type: ignore[arg-type]
        if len(entities) >= limit:
            break
    return entities


__all__ = [
    "MAX_CHARS",
    "MAX_ENTITIES",
    "MODEL_NAME",
    "extract_ner_entities",
    "get_nlp",
    "ner_enabled",
]
