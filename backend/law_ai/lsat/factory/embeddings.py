"""Embedding-backed near-duplicate detection for factory intake.

Spec 024 AC-3, extended by BL-20260702-01. Intake gate 3 compares stems by
token-Jaccard: that catches copies and light rewordings but is blind to
paraphrase — "which one of the following must be true?" and "each of the
following could be false EXCEPT" share almost no tokens with a restatement of
the same question in other words. This module supplies a second, semantic
opinion: stems are embedded by the local Ollama embedding model (default
``nomic-embed-text``, already bootstrapped by the compose stack) and compared
by cosine similarity, so a paraphrase scores high even when Jaccard does not.

Three properties keep it cheap, local, and safe:

* **Local only.** The embedder talks to ``OLLAMA_BASE_URL`` and nothing else;
  no third-party tier is ever consulted, so intake dedup carries no vendor
  dependency and no per-draft cost.
* **Cached per bank revision.** Vectors live in a JSON cache named for the
  model and the current bank revision (a sha256 over the bank/passage data
  files), content-addressed by a hash of the embedded text. One revision
  embeds its corpus once; a new revision inherits the vectors of every stem it
  kept and only pays for what actually changed.
* **Fail-open.** If Ollama is unreachable or the model is not pulled,
  :class:`EmbeddingUnavailable` is raised and intake drops the semantic
  opinion, keeping the Jaccard gate and recording a warning on the
  ``IngestResult``. An offline test run (and an offline operator) sees exactly
  the pre-BL-20260702-01 behaviour.

Every batch that reaches the network writes one ``embedding_batch``
provenance event (constitution §4: retrieval-side model calls are auditable
too), carrying the model, the bank revision, and the cached/computed split.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

from law_ai.core.provenance import provenance
from law_ai.core.settings_proxy import settings_proxy as settings
from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.services import bank as bank_mod

logger = logging.getLogger("law_ai.lsat.factory.embeddings")

#: Model used when ``OLLAMA_EMBED_MODEL`` is unset — the one the compose stack
#: pulls at bootstrap, so the default path needs no operator action.
DEFAULT_EMBED_MODEL = "nomic-embed-text"

#: Bank/passage files whose contents define a "bank revision" for the cache.
_REVISION_FILES = (
    "lr_bank.json",
    "rc_bank.json",
    "lg_bank.json",
    "passages.json",
)

_FLOAT_PLACES = 6


class EmbeddingUnavailable(RuntimeError):
    """The embedding backend could not serve a batch (callers fail open)."""


def bank_revision() -> str:
    """Short digest of the current bank contents (cache generation key)."""
    digest = hashlib.sha256()
    data_dir = Path(bank_mod.DATA_DIR)
    for name in _REVISION_FILES:
        path = data_dir / name
        digest.update(name.encode("utf-8"))
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two vectors; 0.0 for empty or mismatched inputs."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _text_key(text: str) -> str:
    return hashlib.sha256(" ".join(text.lower().split()).encode("utf-8")).hexdigest()


def _model_slug(model: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in model)


class EmbeddingIndex:
    """Cached Ollama embeddings for a bank revision.

    Not thread-safe and deliberately synchronous: intake is a synchronous
    batch step, and the cache means a warm run makes no calls at all.
    """

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        timeout: float,
        cache_path: Path,
        revision: str,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cache_path = cache_path
        self.revision = revision
        self.computed = 0
        self.cached_hits = 0
        self._vectors: dict[str, list[float]] = {}
        self._dirty = False
        self._load_cache()

    # -- construction ------------------------------------------------------

    @classmethod
    def from_config(cls, config: FactoryConfig) -> EmbeddingIndex:
        """Build an index rooted in the run's artifacts dir."""
        model = str(getattr(settings, "OLLAMA_EMBED_MODEL", "") or DEFAULT_EMBED_MODEL)
        revision = bank_revision()
        cache_dir = config.resolved_output_dir() / "embeddings"
        cache_path = cache_dir / f"{_model_slug(model)}-{revision}.json"
        return cls(
            model=model,
            base_url=str(settings.OLLAMA_BASE_URL),
            timeout=float(getattr(settings, "OLLAMA_REQUEST_TIMEOUT_S", 120.0)),
            cache_path=cache_path,
            revision=revision,
        )

    # -- cache -------------------------------------------------------------

    def _load_cache(self) -> None:
        path = self._seed_path()
        if path is None:
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("ignoring unreadable embedding cache %s (%s)", path, exc)
            return
        vectors = payload.get("vectors")
        if isinstance(vectors, dict):
            self._vectors = {
                str(key): [float(x) for x in value]
                for key, value in vectors.items()
                if isinstance(value, list)
            }
            # Inherited from an older revision: persist under this one on flush.
            self._dirty = path != self.cache_path

    def _seed_path(self) -> Path | None:
        """This revision's cache file, else the newest one for the same model."""
        if self.cache_path.is_file():
            return self.cache_path
        parent = self.cache_path.parent
        if not parent.is_dir():
            return None
        siblings = sorted(
            (
                p
                for p in parent.glob(f"{_model_slug(self.model)}-*.json")
                if p.is_file()
            ),
            key=lambda p: p.stat().st_mtime,
        )
        return siblings[-1] if siblings else None

    def flush(self) -> None:
        """Persist newly computed vectors (no-op when nothing changed)."""
        if not self._dirty:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": self.model,
            "bank_revision": self.revision,
            "vectors": self._vectors,
        }
        self.cache_path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        self._dirty = False

    # -- embedding ---------------------------------------------------------

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Vectors for *texts*, in order; raises on backend failure."""
        wanted = [t for t in texts if t.strip()]
        missing: list[str] = []
        seen: set[str] = set()
        for text in wanted:
            key = _text_key(text)
            if key in self._vectors or key in seen:
                continue
            seen.add(key)
            missing.append(text)
        self.cached_hits += len(wanted) - len(missing)
        if missing:
            self._compute(missing)
        return [self._vectors.get(_text_key(t), []) for t in texts]

    def _compute(self, texts: Sequence[str]) -> None:
        started = time.perf_counter()
        url = f"{self.base_url}/api/embeddings"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                for text in texts:
                    response = client.post(
                        url, json={"model": self.model, "prompt": text}
                    )
                    response.raise_for_status()
                    self._vectors[_text_key(text)] = _round_vector(
                        _extract_vector(response.json())
                    )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise EmbeddingUnavailable(
                f"ollama embeddings unavailable at {url} ({exc})"
            ) from exc
        self.computed += len(texts)
        self._dirty = True
        latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
        provenance.log_event(
            "embedding_batch",
            {
                "component": "lsat_factory_intake",
                "model": self.model,
                "bank_revision": self.revision,
                "computed": len(texts),
                "cached_hits": self.cached_hits,
                "latency_ms": latency_ms,
            },
        )


def _extract_vector(payload: Any) -> list[float]:
    """Pull the vector out of an ``/api/embeddings`` response."""
    if not isinstance(payload, dict):
        raise ValueError("embedding response is not an object")
    vector = payload.get("embedding")
    if vector is None:
        embeddings = payload.get("embeddings")
        if isinstance(embeddings, list) and embeddings:
            vector = embeddings[0]
    if not isinstance(vector, list) or not vector:
        raise ValueError("embedding response carries no vector")
    return [float(x) for x in vector]


def _round_vector(vector: list[float]) -> list[float]:
    return [round(x, _FLOAT_PLACES) for x in vector]


def closest_by_embedding(
    text: str,
    corpus: Sequence[tuple[str, str]],
    index: EmbeddingIndex,
) -> tuple[str, float]:
    """Best cosine match for *text* among ``(source_id, text)`` *corpus* rows.

    Raises :class:`EmbeddingUnavailable` when the backend cannot serve the
    batch; callers are expected to fail open onto the Jaccard gate.
    """
    if not corpus or not text.strip():
        return "", 0.0
    vectors = index.embed([text, *(row_text for _, row_text in corpus)])
    target = vectors[0]
    best_id, best_score = "", 0.0
    for (source_id, _), vector in zip(corpus, vectors[1:], strict=True):
        score = cosine(target, vector)
        if score > best_score:
            best_id, best_score = source_id, score
    return best_id, best_score
