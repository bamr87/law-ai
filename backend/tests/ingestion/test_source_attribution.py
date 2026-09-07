"""``PendingReview.source`` names the real adapter (BL-20260602-07).

Dispatch routed every adapter's ``RawDoc`` through ``IngestionScout`` with a
hardcoded ``source="courtlistener"``, so a quarantined Colorado statute row
claimed to come from CourtListener and HITL rows were only addressable by
primary key — ``PendingReview.objects.filter(source="colorado_statutes")``
returned nothing. These tests pin the attribution end to end.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from law_ai.agents_runtime.graphs.topic_frontier import _dispatch_target
from law_ai.ingestionapp.models import PendingReview
from law_ai.ingestionapp.services.scout import IngestionScout
from law_ai.ingestionapp.sources.base import RawDoc, SourceAdapter

PAYLOAD: dict[str, Any] = {
    "id": "https://law.justia.com/codes/colorado/2024/title-18/",
    "case_name": "C.R.S. § 18-3-102",
    "plain_text": "Murder in the first degree.",
    "source_name": "colorado_statutes",
}


def test_extract_uses_the_payload_source_name() -> None:
    result = IngestionScout().extract(PAYLOAD)
    assert result.source == "colorado_statutes"


def test_extract_defaults_to_courtlistener_without_source_name() -> None:
    payload = {k: v for k, v in PAYLOAD.items() if k != "source_name"}
    assert IngestionScout().extract(payload).source == "courtlistener"


@pytest.mark.django_db
def test_quarantined_row_is_filterable_by_its_real_source() -> None:
    """The regression: filtering the HITL queue by source used to be useless."""
    from law_ai.ingestionapp.tasks import quarantine_extraction

    scout = IngestionScout()
    result = scout.extract(PAYLOAD)
    scout._quarantine_via_celery(result, PAYLOAD)

    rows = list(PendingReview.objects.filter(source="colorado_statutes"))
    assert [r.pk for r in rows] == [PAYLOAD["id"]]
    assert quarantine_extraction is not None  # task is the single writer


@pytest.mark.asyncio
async def test_dispatch_forwards_the_adapter_name_to_the_scout() -> None:
    adapter = MagicMock()
    adapter.name = "colorado_statutes"
    adapter.extractor = None
    doc = RawDoc(
        source_name="colorado_statutes",
        source_url="https://law.justia.com/codes/colorado/2024/title-18/",
        title="C.R.S. § 18-3-102",
        text="Murder in the first degree.",
    )
    adapter.fetch.return_value = [doc]

    scout = MagicMock()
    scout.run_and_commit = AsyncMock(
        return_value={"committed": False, "confidence": 0.5, "edges": 0}
    )

    await _dispatch_target(scout, adapter, "18", [])

    sent = scout.run_and_commit.await_args.args[0]
    assert sent["source_name"] == "colorado_statutes"


@pytest.mark.asyncio
async def test_adapter_declared_extractor_is_used_over_the_default() -> None:
    """Per-adapter extractor selection (BL-20260602-07 step 3)."""
    from law_ai.agents_runtime.graphs.topic_frontier import _node_dispatch

    used: list[str] = []

    class _Extractor:
        def __init__(self) -> None:
            used.append("adapter-extractor")

        async def run_and_commit(
            self, payload: dict[str, Any], *, force_quarantine: bool = False
        ) -> dict[str, Any]:
            return {"committed": False, "confidence": 0.4, "edges": 0}

    class _Adapter(SourceAdapter):
        name = "unit-test"
        jurisdiction = "*"
        license = "n/a"
        extractor = _Extractor

        async def afetch(self, query: str, *, limit: int = 10) -> list[RawDoc]:
            return [
                RawDoc(
                    source_name=self.name,
                    source_url="https://unit.test/1",
                    title="Doc",
                    text="body",
                )
            ]

    def _default_scout() -> Any:
        used.append("default-scout")
        return MagicMock()

    import law_ai.agents_runtime.graphs.topic_frontier as tf_module

    with patch.object(
        tf_module.settings, "AUTONOMY_ALLOWED_SOURCES", ["unit-test"], create=True
    ):
        state = await _node_dispatch(
            {"targets": [{"query": "q", "jurisdiction": "*"}]},  # type: ignore[arg-type]
            registry={"unit-test": _Adapter()},
            scout_factory=_default_scout,
        )

    assert used == ["adapter-extractor"]
    assert state["dispatched"][0]["source_name"] == "unit-test"


def test_shipped_adapters_declare_no_extractor_yet() -> None:
    """Documented state: all three emit opinion-shaped docs (BL-20260811-03)."""
    from law_ai.ingestionapp.sources import SOURCE_REGISTRY

    assert all(a.extractor is None for a in SOURCE_REGISTRY.values())
