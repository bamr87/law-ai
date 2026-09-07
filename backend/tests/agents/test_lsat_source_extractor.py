"""Tests for LSATSourceExtractor + the scanned-page intake path.

The load-bearing behaviour here is refusal: the extractor must not turn a page it
could only partly read into a complete question. The grounding check is what makes
that testable — a fabricated choice shares almost no content words with the page.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

# One page of ocrmd's output: the two readings disagreed on "assumes", so it carries
# the ==mark==, and a footnote at the bottom lists both candidates.
PAGE_TEXT = """\
15. The mayor's transit proposal ==assumes==[^ocrmd-1] that ridership will rise once
fares are cut. But ridership fell in the three cities that cut fares last year, and
in each the transit authority had also reduced service frequency.

Which one of the following, if true, most weakens the argument above?

(A) The three cities that cut fares had older rolling stock than the mayor's city.
(B) Reduced service frequency depresses ridership more than a fare cut raises it.
(C) The mayor's proposal would be funded by a increase in the city sales tax.
(D) Transit ridership in the mayor's city has been flat for six consecutive years.
(E) Most riders in the three cities were unaware that fares had been cut.

[^ocrmd-1]: OCR read "assumes"; the model read "assumed".
"""


def _extract_payload(**overrides):
    draft = {
        "section": "LR",
        "difficulty": "med",
        "stem": "Which one of the following, if true, most weakens the argument above?",
        "choices": [
            {
                "label": "A",
                "text": "The three cities that cut fares had older rolling stock than the mayor's city.",
            },
            {
                "label": "B",
                "text": "Reduced service frequency depresses ridership more than a fare cut raises it.",
            },
            {
                "label": "C",
                "text": "The mayor's proposal would be funded by a increase in the city sales tax.",
            },
            {
                "label": "D",
                "text": "Transit ridership in the mayor's city has been flat for six consecutive years.",
            },
            {
                "label": "E",
                "text": "Most riders in the three cities were unaware that fares had been cut.",
            },
        ],
        "correct": "B",
        "key_source": "inferred",
        "explanation": "B severs the fare-cut/ridership link by naming the confound.",
        "explanation_source": "inferred",
        "concepts": [],
        "confidence": 0.9,
        "source_excerpt": "15. The mayor's transit proposal assumes that…",
        "notes": "",
    }
    draft.update(overrides)
    return json.dumps({"drafts": [draft], "notes": ""})


def _llm_result(text: str):
    from law_ai.core.llm.base import LLMResult

    return LLMResult(
        text=text, provider="claude_code", model="claude-opus-5", latency_ms=1.0
    )


class TestContracts:
    def test_input_rejects_the_writing_section(self) -> None:
        """WS produces an essay, not a keyed item — it can never come off this path."""
        from law_ai.agents_runtime.crews.lsat_source_extractor import (
            ExtractQuestionsInput,
        )

        with pytest.raises(ValidationError):
            ExtractQuestionsInput(source_text="x", section="WS")

    def test_four_choices_is_not_a_draft(self) -> None:
        from law_ai.agents_runtime.crews.lsat_source_extractor import ExtractedQuestion

        with pytest.raises(ValidationError):
            ExtractedQuestion(
                section="LR",
                difficulty="med",
                stem="x",
                choices=[{"label": lb, "text": "y"} for lb in "ABCD"],  # type: ignore[arg-type]
                correct="A",
                explanation="z",
            )

    def test_as_draft_drops_the_extraction_fields(self) -> None:
        """The bank has no column for key_source; it must not leak into the draft."""
        from law_ai.agents_runtime.crews.lsat_source_extractor import ExtractedQuestion

        e = ExtractedQuestion(
            section="LR",
            difficulty="med",
            stem="x",
            choices=[{"label": lb, "text": "y"} for lb in "ABCDE"],  # type: ignore[arg-type]
            correct="A",
            explanation="z",
            key_source="printed",
            grounding=1.0,
        )
        assert "key_source" not in e.as_draft().model_dump()
        assert "grounding" not in e.as_draft().model_dump()


class TestPageTextCleaning:
    def test_disagreement_marks_and_footnotes_are_stripped(self) -> None:
        from law_ai.agents_runtime.crews.lsat_source_extractor import clean_page_text

        out = clean_page_text(PAGE_TEXT)
        assert "==" not in out and "[^ocrmd-1]" not in out
        assert "proposal assumes that" in out  # the word itself survives
        assert "OCR read" not in out  # the footnote body does not


class TestGrounding:
    @pytest.mark.asyncio
    async def test_a_faithful_transcription_is_kept(self) -> None:
        from law_ai.agents_runtime.crews.lsat_source_extractor import (
            LSATSourceExtractor,
        )

        with patch(
            "law_ai.core.llm.agenerate",
            new=AsyncMock(return_value=_llm_result(_extract_payload())),
        ):
            out = await LSATSourceExtractor().run(
                {"source_text": PAGE_TEXT, "hint": "question 15"}
            )
        assert len(out.drafts) == 1
        assert not out.ungrounded
        assert out.drafts[0].grounding >= 0.9
        assert out.drafts[0].correct == "B"

    @pytest.mark.asyncio
    async def test_an_invented_choice_is_dropped(self) -> None:
        """The failure this whole path exists to prevent: a fifth choice nobody printed."""
        from law_ai.agents_runtime.crews.lsat_source_extractor import (
            LSATSourceExtractor,
        )

        fabricated = json.loads(_extract_payload())
        fabricated["drafts"][0]["choices"][4] = {
            "label": "E",
            "text": (
                "Municipal bond covenants generally prohibit pledging farebox revenue "
                "against capital obligations issued before refinancing."
            ),
        }
        with patch(
            "law_ai.core.llm.agenerate",
            new=AsyncMock(return_value=_llm_result(json.dumps(fabricated))),
        ):
            out = await LSATSourceExtractor().run({"source_text": PAGE_TEXT})
        assert out.drafts == []
        assert len(out.ungrounded) == 1
        assert out.ungrounded[0]["grounding"] < 0.75

    @pytest.mark.asyncio
    async def test_grounding_is_the_weakest_part_not_the_average(self) -> None:
        """One invented choice must not be averaged away by four faithful ones."""
        from law_ai.agents_runtime.crews.lsat_source_extractor import (
            ExtractedQuestion,
            _content_tokens,
            _score_grounding,
            clean_page_text,
        )

        tokens = frozenset(_content_tokens(clean_page_text(PAGE_TEXT)))
        draft = ExtractedQuestion.model_validate(
            json.loads(_extract_payload())["drafts"][0]
        )
        faithful = _score_grounding(draft, tokens)
        draft.choices[4].text = "Zebra quantum tarpaulin heresy voluminous sandalwood."
        assert _score_grounding(draft, tokens) < faithful
        assert _score_grounding(draft, tokens) < 0.3


class TestDegradedPath:
    @pytest.mark.asyncio
    async def test_no_provider_returns_no_drafts_rather_than_a_placeholder(
        self,
    ) -> None:
        """LSATContentAuthor invents a placeholder when offline. This must not."""
        from law_ai.agents_runtime.crews.lsat_source_extractor import (
            LSATSourceExtractor,
        )
        from law_ai.core.llm import LLMUnavailableError

        with patch(
            "law_ai.core.llm.agenerate",
            new=AsyncMock(side_effect=LLMUnavailableError("no provider")),
        ):
            out = await LSATSourceExtractor().run({"source_text": PAGE_TEXT})
        assert out.drafts == []
        assert out.degraded is True
        assert "unavailable" in out.notes


class TestIntakeService:
    def test_accepted_proposal_names_its_page(self, tmp_path, settings) -> None:
        """An extracted question you cannot take back to the photograph is a rumour."""
        settings.LSAT_PROPOSALS_DIR = str(tmp_path)
        from law_ai.lsat.services.ocr_intake import (
            IngestScanRequest,
            ScanProvenance,
            ingest_scan,
        )
        from law_ai.lsat.services.proposals import get_proposal

        with patch(
            "law_ai.core.llm.agenerate",
            new=AsyncMock(return_value=_llm_result(_extract_payload())),
        ):
            result = ingest_scan(
                IngestScanRequest(
                    source_text=PAGE_TEXT,
                    hint="question 15",
                    provenance=ScanProvenance(
                        document="lsat", page=15, page_id="deadbeef", agreement=0.96
                    ),
                )
            )
        assert len(result.accepted) == 1, result
        row = get_proposal(result.accepted[0]["id"])
        assert row is not None
        assert row["status"] == "pending"  # never the live bank
        assert row["meta"]["source"]["document"] == "lsat"
        assert row["meta"]["source"]["page"] == 15
        assert row["meta"]["source"]["page_id"] == "deadbeef"
        assert row["meta"]["extraction"]["key_source"] == "inferred"

    def test_the_same_page_scanned_twice_is_deduped(self, tmp_path, settings) -> None:
        """Rescanning a page is one keystroke; the second copy must not land."""
        settings.LSAT_PROPOSALS_DIR = str(tmp_path)
        from law_ai.lsat.services.ocr_intake import IngestScanRequest, ingest_scan

        with patch(
            "law_ai.core.llm.agenerate",
            new=AsyncMock(return_value=_llm_result(_extract_payload())),
        ):
            req = IngestScanRequest(source_text=PAGE_TEXT, hint="question 15")
            first = ingest_scan(req)
            second = ingest_scan(req)
        assert len(first.accepted) == 1
        assert second.accepted == []
        assert [r.reason for r in second.rejected] == ["duplicate"]


class TestEndpoint:
    def test_post_returns_202_with_the_pending_proposal(
        self, client, tmp_path, settings
    ) -> None:
        settings.LSAT_PROPOSALS_DIR = str(tmp_path)
        with patch(
            "law_ai.core.llm.agenerate",
            new=AsyncMock(return_value=_llm_result(_extract_payload())),
        ):
            resp = client.post(
                "/api/lsat/intake/ocr",
                {
                    "source_text": PAGE_TEXT,
                    "hint": "question 15",
                    "provenance": {"tool": "ocrmd", "document": "lsat", "page": 15},
                },
                format="json",
            )
        assert resp.status_code == 202, resp.content
        body = resp.json()
        assert len(body["accepted"]) == 1
        assert body["accepted"][0]["section"] == "LR"
        assert body["degraded"] is False

    def test_empty_source_text_is_422(self, client) -> None:
        resp = client.post("/api/lsat/intake/ocr", {"source_text": ""}, format="json")
        assert resp.status_code == 422

    def test_intake_writes_an_audit_event(
        self, client, tmp_path, settings, monkeypatch
    ) -> None:
        """BL-20260905-37: the record() call used to be a swallowed TypeError."""
        from law_ai.core import audit_jsonl as audit_store

        settings.LSAT_PROPOSALS_DIR = str(tmp_path)
        monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        with patch(
            "law_ai.core.llm.agenerate",
            new=AsyncMock(return_value=_llm_result(_extract_payload())),
        ):
            resp = client.post(
                "/api/lsat/intake/ocr",
                {
                    "source_text": PAGE_TEXT,
                    "hint": "question 15",
                    "provenance": {"tool": "ocrmd", "document": "lsat", "page": 15},
                },
                format="json",
            )
        assert resp.status_code == 202, resp.content
        events = [e for e in audit_store.tail(50) if e.get("type") == "lsat_intake_ocr"]
        assert len(events) == 1, audit_store.tail(50)
        assert events[0]["document"] == "lsat"
        assert events[0]["page"] == 15
        assert events[0]["accepted"] == 1
