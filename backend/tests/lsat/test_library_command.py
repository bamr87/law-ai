"""`lsat_library` management command (spec 048 T-042: FR-17, AC-10, AC-11)."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from django.conf import settings

from law_ai.lsat.services.library import _library_dir as cmd_library_dir
from law_ai.lsat.services.library import load_library


@pytest.fixture(autouse=True)
def _isolate_stores(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(
        settings, "LSAT_PROPOSALS_DIR", str(tmp_path / "proposals"), raising=False
    )


def _run(*args: str, **opts: object) -> str:
    out = StringIO()
    call_command("lsat_library", *args, stdout=out, **opts)
    return out.getvalue()


class TestAudit:
    def test_summary_reports_the_corpus(self) -> None:
        text = _run("audit")
        assert f"{len(load_library())} articles" in text
        assert "concept coverage" in text

    def test_json_output_is_the_audit_report(self) -> None:
        report = json.loads(_run("audit", "--json"))
        assert report["counts"]["articles"] == len(load_library())
        assert "freshness" in report


class TestReview:
    def test_dry_run_names_targets_and_calls_no_agent(self) -> None:
        text = _run("review", "--dry-run", "--limit", "2")
        assert "would review:" in text
        assert text.count("would review:") <= 2

    def test_explicit_target_is_honoured(self) -> None:
        target = sorted(load_library())[0]
        text = _run("review", "--dry-run", "--article", target)
        assert f"would review: {target}" in text

    def test_unknown_article_is_a_command_error(self) -> None:
        with pytest.raises(CommandError, match="unknown article"):
            _run("review", "--dry-run", "--article", "no-such-article")

    def test_review_writes_nothing_under_data_library(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spec 048 AC-10 — the loop proposes; promotion is a separate act."""
        from law_ai.agents_runtime.crews import lsat_librarian
        from law_ai.core import llm
        from law_ai.lsat.services import library as lib
        from law_ai.lsat.services import proposals as proposals_store

        class _Result:
            text = json.dumps(
                {
                    "summary": "One gap.",
                    "findings": [
                        {
                            "severity": "low",
                            "category": "gap",
                            "problem": "missing a worked case",
                        }
                    ],
                }
            )
            model_label = "test/model"

        async def _agenerate(prompt, *, system=None, agent=None):
            return _Result()

        monkeypatch.setattr(llm, "agenerate", _agenerate)
        assert lsat_librarian.LSATLibrarian.human_approval_required is True

        before = {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(lib._library_dir().glob("*.md"))
        }
        text = _run("review", "--limit", "1")
        after = {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(lib._library_dir().glob("*.md"))
        }

        assert before == after, "review must not modify library content"
        assert "Nothing under data/library/ was modified." in text
        pending = proposals_store.list_proposals("pending")
        assert [p["proposal_kind"] for p in pending] == ["library_finding"]

    def test_degraded_results_are_skipped_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.core import llm
        from law_ai.lsat.services import proposals as proposals_store

        async def _agenerate(prompt, *, system=None, agent=None):
            raise llm.LLMUnavailableError("no provider")

        monkeypatch.setattr(llm, "agenerate", _agenerate)
        text = _run("review", "--limit", "1")
        assert "degraded (no provider) — skipped" in text
        assert proposals_store.list_proposals("pending") == []


class TestPromote:
    def test_promote_requires_a_proposal_id(self) -> None:
        with pytest.raises(CommandError, match="requires --proposal"):
            _run("promote")

    def test_unknown_proposal_is_a_command_error(self) -> None:
        with pytest.raises(CommandError, match="unknown proposal"):
            _run("promote", "--proposal", "prop-doesnotexist")


class TestPickerDrivenReview:
    """BL-20260903-08 — review with no --article picks its own targets."""

    def test_dry_run_names_the_audit_signal_behind_each_target(self) -> None:
        text = _run("review", "--dry-run", "--limit", "1")
        assert "would review:" in text
        # The reason is what makes an unattended pick auditable.
        assert "(" in text.split("would review:")[1]

    def test_a_coverage_gap_is_filed_as_a_mergeable_article_draft(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.core import llm
        from law_ai.lsat.management.commands import lsat_library as cmd
        from law_ai.lsat.services import proposals as proposals_store
        from law_ai.lsat.services.bank import load_concepts
        from law_ai.lsat.services.library import library_audit, parse_article

        gap_concept = sorted(load_concepts())[0]
        report = library_audit()
        report["coverage"]["concepts_untaught"] = [gap_concept]
        monkeypatch.setattr(cmd, "library_audit", lambda: report)

        class _Result:
            text = json.dumps(
                {
                    "summary": "Drafted the missing section.",
                    "proposed_markdown": "## Newly Drafted\n\nOne paragraph.\n",
                }
            )
            model_label = "test/model"

        async def _agenerate(prompt, *, system=None, agent=None):
            return _Result()

        monkeypatch.setattr(llm, "agenerate", _agenerate)

        before = {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(cmd_library_dir().glob("*.md"))
        }
        text = _run("review", "--limit", "1")
        after = {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(cmd_library_dir().glob("*.md"))
        }

        assert before == after, "an expansion proposes; it never writes"
        assert "expand" in text
        pending = proposals_store.list_proposals("pending")
        assert [p["proposal_kind"] for p in pending] == ["library_article"]
        draft = pending[0]["draft"]
        assert gap_concept in draft["gap"]
        assert draft["reason"] == f"untaught concept {gap_concept}"
        # The merged draft is the whole file, so promotion writes what a
        # reviewer read — and it still parses.
        assert "Newly Drafted" in draft["markdown"]
        parse_article(draft["markdown"], article_id=draft["article_id"], where="draft")
