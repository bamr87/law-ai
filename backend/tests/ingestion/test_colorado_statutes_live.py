"""Live-network drift smoke test for the Colorado statutes adapter.

BL-20260511-07 (resolves the overlap with BL-20260509-04). Every other test of
this parser runs against a frozen fixture
(``tests/ingestion/fixtures/co/title_18_article_3.html``), which means a
Justia markup change goes unnoticed until an ingestion run silently returns
zero sections. This test fetches **one** real title and re-runs the parser, so
upstream HTML drift surfaces as a failing nightly job instead of an empty
corpus.

Guardrails:

* Skipped unless ``LIVE_NETWORK=1`` — never runs in ``make test-backend``
  (also excluded by the ``integration`` marker) nor in per-PR CI.
* One request per run. Do not loop titles: Justia's crawl-delay is the reason
  ``ColoradoStatutesAdapter.rate_limit_rps`` is 0.5.
* Wired into the nightly workflow with ``continue-on-error`` — an upstream
  outage is a warning, never a red build.

Run it with ``make test-live-network``.
"""

from __future__ import annotations

import os
import re

import pytest

from law_ai.ingestionapp.sources import SOURCE_REGISTRY
from law_ai.ingestionapp.sources.colorado_statutes import ColoradoStatutesAdapter

pytestmark = [
    pytest.mark.integration,
    pytest.mark.network,
    pytest.mark.skipif(
        os.getenv("LIVE_NETWORK") != "1",
        reason="live upstream fetch — set LIVE_NETWORK=1 (nightly only)",
    ),
]

CITATION_RE = re.compile(r"^C\.R\.S\. § \d+[A-Z]?-\d+-\d+(\.\d+)?$")

#: CRS Title 18 (Criminal Code) — the title spec 016 shipped against.
TITLE = "18"


def test_live_justia_fetch_still_parses() -> None:
    """One real fetch; drift shows up as zero sections or a shape mismatch."""
    adapter = ColoradoStatutesAdapter()
    docs = list(adapter.fetch(TITLE, limit=5))

    assert docs, (
        "colorado_statutes returned no sections for CRS Title 18 — either "
        "Justia's markup changed (update the CSS hooks in "
        "services/colorado_statutes.py and the frozen fixture) or the title "
        "page moved"
    )
    for doc in docs:
        assert doc.source_name == "colorado_statutes"
        assert CITATION_RE.match(doc.title), f"unexpected citation: {doc.title!r}"
        assert doc.text.strip(), f"empty body for {doc.title}"
        assert doc.metadata["title_id"] == TITLE
        assert doc.metadata["section_id"].startswith("us-co/crs/")


def test_live_adapter_respects_its_registry_metadata() -> None:
    """The live adapter is the same object the registry hands the autonomy loop."""
    registered = SOURCE_REGISTRY["colorado_statutes"]
    assert isinstance(registered, ColoradoStatutesAdapter)
    assert registered.rate_limit_rps <= 1.0, "do not hammer Justia"
