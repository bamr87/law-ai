"""The LSAT door speaks the ocrmd sink contract (spec 055).

``GET`` answers with a descriptor so the scanner can draw this door's real options;
``POST`` takes the scanner's envelope — text, provenance, catalogue entry, options — and
answers in the contract's terms (``summary``, ``items``, ``warnings``) on top of the
gate-level detail the door always returned. The legacy shape keeps working.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from rest_framework.test import APIClient

from tests.agents.test_lsat_source_extractor import (
    PAGE_TEXT,
    _extract_payload,
    _llm_result,
)

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _envelope(**options: Any) -> dict[str, Any]:
    return {
        "ocrmd": 1,
        "kind": "page",
        "text": PAGE_TEXT,
        "provenance": {
            "tool": "ocrmd",
            "tool_version": "0.9.0",
            "envelope": 1,
            "document": "lsat",
            "page": 15,
            "page_id": "deadbeef",
            "page_label": "37",
            "captured_at": "2026-09-06T10:00:00",
            "ocr_engine": "apple_vision@26.5+rapidocr@3.9.2",
            "llm_model": "claude-opus-5-5",
            "agreement": 0.98,
            "overlap": 0.99,
            "flagged_spans": 1,
            "unresolved": 1,
            "status": "flagged",
            "image_url": "http://127.0.0.1:8765/api/documents/lsat/pages/15/image/flat",
            "page_url": "http://127.0.0.1:8765/#/doc/lsat/page/15",
        },
        "document": {
            "slug": "lsat",
            "title": "LSAT Prep",
            "author": ["Someone"],
            "kind": "textbook",
            "tags": ["study"],
        },
        "options": {"hint": "question 15", "section": "LR", "max_items": 3, **options},
    }


class TestDescriptor:
    def test_get_answers_with_the_sink_descriptor(self) -> None:
        res = APIClient().get("/api/lsat/intake/ocr")
        assert res.status_code == 200, res.content
        body = res.json()
        assert body["ocrmd_sink"] == 1
        assert body["name"].startswith("Law AI")
        assert "page" in body["accepts"] and "region" in body["accepts"]
        keys = [o["key"] for o in body["options"]]
        assert keys == ["hint", "section", "difficulty", "max_items"]
        section = next(o for o in body["options"] if o["key"] == "section")
        assert section["type"] == "enum" and section["choices"] == ["LR", "RC", "LG"]
        assert (
            next(o for o in body["options"] if o["key"] == "max_items")["default"] == 5
        )


class TestEnvelope:
    def test_the_envelope_is_taken_in_and_answered_in_the_contract(
        self, tmp_path: Any, settings: Any
    ) -> None:
        settings.LSAT_PROPOSALS_DIR = str(tmp_path)
        with patch(
            "law_ai.core.llm.agenerate",
            new=AsyncMock(return_value=_llm_result(_extract_payload())),
        ):
            res = APIClient().post("/api/lsat/intake/ocr", _envelope(), format="json")
        assert res.status_code == 202, res.content
        body = res.json()
        assert body["summary"].startswith("1 question(s) queued for review")
        assert body["items"][0]["status"] == "pending"
        assert body["items"][0]["id"].startswith("prop-")
        assert "LR/med" in body["items"][0]["detail"]
        assert body["warnings"] == []
        # the gate-level detail the door always returned is still there
        assert len(body["accepted"]) == 1 and body["degraded"] is False

        from law_ai.lsat.services.proposals import get_proposal

        row = get_proposal(body["accepted"][0]["id"])
        assert row is not None and row["status"] == "pending"
        src = row["meta"]["source"]
        assert src["page_id"] == "deadbeef" and src["page"] == 15
        assert src["document_title"] == "LSAT Prep"
        assert src["unresolved"] == 1 and src["page_url"].endswith("page/15")
        assert row["meta"]["hint"] == "question 15"

    def test_the_legacy_shape_still_works(self, tmp_path: Any, settings: Any) -> None:
        settings.LSAT_PROPOSALS_DIR = str(tmp_path)
        with patch(
            "law_ai.core.llm.agenerate",
            new=AsyncMock(return_value=_llm_result(_extract_payload())),
        ):
            res = APIClient().post(
                "/api/lsat/intake/ocr",
                {
                    "source_text": PAGE_TEXT,
                    "hint": "question 15",
                    "provenance": {"tool": "ocrmd", "document": "lsat", "page": 15},
                },
                format="json",
            )
        assert res.status_code == 202, res.content
        assert res.json()["summary"].startswith("1 question(s) queued")

    def test_an_option_outside_the_descriptor_is_422(self) -> None:
        res = APIClient().post(
            "/api/lsat/intake/ocr", _envelope(section="WS"), format="json"
        )
        assert res.status_code == 422

    def test_sending_the_same_page_twice_is_a_warning_not_a_second_draft(
        self, tmp_path: Any, settings: Any
    ) -> None:
        """Rescanning a page is one keystroke; the receiver deduplicates and says so."""
        settings.LSAT_PROPOSALS_DIR = str(tmp_path)
        with patch(
            "law_ai.core.llm.agenerate",
            new=AsyncMock(return_value=_llm_result(_extract_payload())),
        ):
            first = APIClient().post("/api/lsat/intake/ocr", _envelope(), format="json")
            second = APIClient().post(
                "/api/lsat/intake/ocr", _envelope(), format="json"
            )
        assert first.status_code == 202 and second.status_code == 202
        body = second.json()
        assert body["accepted"] == [] and body["items"] == []
        assert body["summary"].startswith("nothing queued")
        assert any("duplicate" in w for w in body["warnings"])
