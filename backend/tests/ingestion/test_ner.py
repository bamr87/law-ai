"""Optional NER pass in ``IngestionScout`` (BL-20260429-03).

The model itself is never loaded here: ``get_nlp`` is patched, which is the
point of the lazy shim — an opted-out suite (the default) pays no model-load
time at all.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from law_ai.ingestionapp.services import ner as ner_mod
from law_ai.ingestionapp.services.ner import extract_ner_entities, get_nlp, ner_enabled
from law_ai.ingestionapp.services.scout import IngestionScout, _extract_entities


class _FakeDoc:
    def __init__(self, ents: list[Any]) -> None:
        self.ents = ents


def _span(text: str, label: str) -> Any:
    return SimpleNamespace(text=text, label_=label)


def _fake_nlp(ents: list[Any]) -> Any:
    return lambda text: _FakeDoc(ents)


@pytest.fixture(autouse=True)
def _clear_model_cache() -> Any:
    get_nlp.cache_clear()
    yield
    get_nlp.cache_clear()


# ---------------------------------------------------------------------------
# Flag + laziness
# ---------------------------------------------------------------------------


def test_disabled_by_default(settings: Any) -> None:
    assert ner_enabled() is False


def test_disabled_flag_short_circuits_before_loading_the_model(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lazy shim's contract: no model load when the flag is off."""
    settings.ENABLE_NER = False
    loaded: list[str] = []
    monkeypatch.setattr(
        ner_mod, "get_nlp", lambda: loaded.append("loaded") or None  # type: ignore[func-returns-value]
    )
    assert extract_ner_entities("Smith v. Jones was decided today.") == []
    assert loaded == []


def test_empty_text_short_circuits(settings: Any) -> None:
    settings.ENABLE_NER = True
    assert extract_ner_entities("") == []


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------


def test_maps_spacy_labels_onto_law_ai_labels(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.ENABLE_NER = True
    monkeypatch.setattr(
        ner_mod,
        "get_nlp",
        lambda: _fake_nlp(
            [
                _span("Jane Smith", "PERSON"),
                _span("Acme Corp.", "ORG"),
                _span("Supreme Court of Colorado", "ORG"),
                _span("Civil Rights Act", "LAW"),
                _span("Colorado", "GPE"),  # unmapped → dropped
            ]
        ),
    )
    entities = extract_ner_entities("irrelevant, the pipeline is faked")
    assert [(e.text, e.label) for e in entities] == [
        ("Jane Smith", "PARTY"),
        ("Acme Corp.", "PARTY"),
        ("Supreme Court of Colorado", "COURT"),
        ("Civil Rights Act", "STATUTE"),
    ]


def test_deduplicates_and_caps(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.ENABLE_NER = True
    spans = [_span("Jane  Smith", "PERSON")] * 3 + [
        _span(f"Party {i}", "PERSON") for i in range(10)
    ]
    monkeypatch.setattr(ner_mod, "get_nlp", lambda: _fake_nlp(spans))
    entities = extract_ner_entities("x", limit=4)
    assert len(entities) == 4
    # Whitespace is normalised, and the triple is collapsed to one.
    assert entities[0].text == "Jane Smith"
    assert [e.text for e in entities[1:]] == ["Party 0", "Party 1", "Party 2"]


# ---------------------------------------------------------------------------
# Failure modes never break ingestion
# ---------------------------------------------------------------------------


def test_missing_model_degrades_to_no_entities(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.ENABLE_NER = True

    class _Spacy:
        @staticmethod
        def load(name: str, **kwargs: Any) -> Any:
            raise OSError(f"[E050] Can't find model '{name}'")

    monkeypatch.setitem(__import__("sys").modules, "spacy", _Spacy)
    assert get_nlp() is None
    assert extract_ner_entities("Smith v. Jones") == []


def test_pipeline_error_degrades_to_no_entities(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.ENABLE_NER = True

    def _boom(text: str) -> Any:
        raise RuntimeError("model exploded")

    monkeypatch.setattr(ner_mod, "get_nlp", lambda: _boom)
    assert extract_ner_entities("Smith v. Jones") == []


# ---------------------------------------------------------------------------
# Wiring into the scout
# ---------------------------------------------------------------------------


PAYLOAD = {
    "id": "ner-1",
    "case_name": "Smith v. Acme Corp.",
    "plain_text": "Jane Smith sued Acme Corp. in the Supreme Court of Colorado.",
    "cluster": {"court": "Supreme Court of Colorado", "judges": "Alito, Kagan"},
}


def test_scout_entities_unchanged_when_ner_is_off(settings: Any) -> None:
    settings.ENABLE_NER = False
    entities = _extract_entities(PAYLOAD, text=str(PAYLOAD["plain_text"]))
    assert [(e.text, e.label) for e in entities] == [
        ("Alito", "JUDGE"),
        ("Kagan", "JUDGE"),
        ("Supreme Court of Colorado", "COURT"),
    ]


def test_scout_merges_ner_entities_without_duplicating_structured_ones(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.ENABLE_NER = True
    monkeypatch.setattr(
        ner_mod,
        "get_nlp",
        lambda: _fake_nlp(
            [
                _span("Jane Smith", "PERSON"),
                # Already present as a structured COURT entity → not duplicated.
                _span("Supreme Court of Colorado", "ORG"),
                # Already present as a structured JUDGE entity → not duplicated.
                _span("Kagan", "PERSON"),
            ]
        ),
    )
    entities = _extract_entities(PAYLOAD, text=str(PAYLOAD["plain_text"]))
    labels = [(e.text, e.label) for e in entities]
    assert ("Jane Smith", "PARTY") in labels
    assert labels.count(("Supreme Court of Colorado", "COURT")) == 1
    assert ("Kagan", "PARTY") not in labels
    assert labels.count(("Kagan", "JUDGE")) == 1


def test_ner_never_changes_confidence(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NER may enrich entities but must never move a doc across the HITL gate."""
    settings.ENABLE_NER = False
    baseline = IngestionScout().extract(dict(PAYLOAD)).confidence

    settings.ENABLE_NER = True
    monkeypatch.setattr(
        ner_mod,
        "get_nlp",
        lambda: _fake_nlp([_span(f"Party {i}", "PERSON") for i in range(20)]),
    )
    enriched = IngestionScout().extract(dict(PAYLOAD))
    assert enriched.confidence == baseline
    assert len(enriched.entities) > 3
