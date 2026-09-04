"""LSATLibrarian (spec 048 T-041: FR-15, FR-16, AC-9, AC-10)."""

from __future__ import annotations

import json

import pytest

from law_ai.agents_runtime.crews.lsat_librarian import (
    PROMPT_PATH,
    LibrarianOutput,
    LSATLibrarian,
)
from law_ai.core import llm
from law_ai.lsat.services.library import load_library


def _an_article_id() -> str:
    return sorted(load_library())[0]


class _Result:
    def __init__(self, text: str, model_label: str = "test/model") -> None:
        self.text = text
        self.model_label = model_label


@pytest.fixture()
def stub_llm(monkeypatch: pytest.MonkeyPatch):
    """Replace the provider chain with a canned response."""

    def _install(payload: dict) -> None:
        async def _agenerate(prompt, *, system=None, agent=None):
            _install.last_prompt = prompt  # type: ignore[attr-defined]
            return _Result(json.dumps(payload))

        monkeypatch.setattr(llm, "agenerate", _agenerate)

    return _install


@pytest.fixture()
def dead_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _agenerate(prompt, *, system=None, agent=None):
        raise llm.LLMUnavailableError("no provider")

    monkeypatch.setattr(llm, "agenerate", _agenerate)


class TestContract:
    def test_registered_with_the_hitl_gate(self) -> None:
        assert LSATLibrarian.human_approval_required is True
        assert LSATLibrarian.name == "LSATLibrarian"

    def test_prompt_ships_with_the_code(self) -> None:
        assert PROMPT_PATH.is_file()
        text = PROMPT_PATH.read_text(encoding="utf-8")
        assert "LSATLibrarian" in text
        # The closed dialect is the contract the model must not violate.
        assert "Never emit raw HTML" in text
        assert "[[concept:" in text


class TestReview:
    async def test_review_returns_validated_findings(self, stub_llm) -> None:
        stub_llm(
            {
                "action": "review",
                "summary": "Broadly accurate, two gaps.",
                "findings": [
                    {
                        "severity": "med",
                        "category": "gap",
                        "anchor": "first-section",
                        "quote": "a quoted phrase",
                        "problem": "does not mention the contrapositive",
                        "suggestion": "add a sentence",
                    }
                ],
                "proposed_markdown": None,
            }
        )
        out = await LSATLibrarian().run(
            {"action": "review", "article_id": _an_article_id()}
        )
        assert isinstance(out, LibrarianOutput)
        assert out.action == "review"
        assert len(out.findings) == 1
        assert out.findings[0].category == "gap"
        assert out.degraded is False
        assert out.confidence > 0
        assert out.trace_id

    async def test_empty_findings_are_a_valid_review(self, stub_llm) -> None:
        stub_llm({"summary": "No defects found.", "findings": []})
        out = await LSATLibrarian().run(
            {"action": "review", "article_id": _an_article_id()}
        )
        assert out.findings == []
        assert out.degraded is False

    async def test_known_ids_are_sent_so_the_model_cannot_invent_references(
        self, stub_llm
    ) -> None:
        stub_llm({"summary": "ok", "findings": []})
        await LSATLibrarian().run({"action": "review", "article_id": _an_article_id()})
        prompt = stub_llm.last_prompt  # type: ignore[attr-defined]
        assert "known_ids" in prompt
        assert _an_article_id() in prompt


class TestCorrectAndExpand:
    async def test_correct_requires_a_finding(self) -> None:
        with pytest.raises(ValueError, match="requires a finding"):
            await LSATLibrarian().run(
                {"action": "correct", "article_id": _an_article_id()}
            )

    async def test_correct_returns_replacement_markdown(self, stub_llm) -> None:
        stub_llm(
            {
                "summary": "Reworded the claim.",
                "findings": [],
                "proposed_markdown": "## Revised\n\nNew prose.\n",
            }
        )
        out = await LSATLibrarian().run(
            {
                "action": "correct",
                "article_id": _an_article_id(),
                "finding": {
                    "severity": "high",
                    "category": "accuracy",
                    "problem": "wrong section count",
                },
            }
        )
        assert out.proposed_markdown is not None
        assert "Revised" in out.proposed_markdown

    async def test_expand_requires_a_gap(self) -> None:
        with pytest.raises(ValueError, match="requires a gap"):
            await LSATLibrarian().run({"action": "expand"})

    async def test_correct_without_markdown_falls_back(self, stub_llm) -> None:
        """A model that returns no draft on a draft action is a failure, not a pass."""
        stub_llm({"summary": "nothing", "findings": []})
        out = await LSATLibrarian().run(
            {
                "action": "correct",
                "article_id": _an_article_id(),
                "finding": {
                    "severity": "low",
                    "category": "clarity",
                    "problem": "unclear",
                },
            }
        )
        assert out.degraded is True
        assert out.confidence == 0.0


class TestValidation:
    async def test_unknown_article_raises(self, stub_llm) -> None:
        stub_llm({"summary": "ok", "findings": []})
        with pytest.raises(KeyError):
            await LSATLibrarian().run(
                {"action": "review", "article_id": "no-such-article"}
            )

    async def test_review_without_an_article_raises(self) -> None:
        with pytest.raises(ValueError, match="requires an article_id"):
            await LSATLibrarian().run({"action": "review"})


class TestDegraded:
    async def test_offline_fallback_is_labelled_and_zero_confidence(
        self, dead_llm
    ) -> None:
        out = await LSATLibrarian().run(
            {"action": "review", "article_id": _an_article_id()}
        )
        assert out.degraded is True
        assert out.confidence == 0.0
        assert "OFFLINE FALLBACK" in out.summary
        # Still audited: a degraded run is a run, and the cycle stays traceable.
        assert out.trace_id

    async def test_agent_never_writes_to_the_library(self, dead_llm) -> None:
        """Spec 048 AC-10 — the agent proposes; promotion is a separate act."""
        from law_ai.lsat.services import library as lib

        before = {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(lib._library_dir().glob("*.md"))
        }
        await LSATLibrarian().run({"action": "review", "article_id": _an_article_id()})
        after = {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(lib._library_dir().glob("*.md"))
        }
        assert before == after
