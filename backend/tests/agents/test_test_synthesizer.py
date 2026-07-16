"""Tests for law_ai.agents_runtime.crews.test_synthesizer (spec 018 T-004)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_LLM_RESPONSE = '''```python
import pytest
from law_ai.eval.scoring import score_response


@pytest.mark.skip("autonomy-proposed")
def test_autonomy_score_empty() -> None:
    """Empty response should never match."""
    ok, _ = score_response("", "True", "core_reasoning")
    assert ok is False
```'''


# ---------------------------------------------------------------------------
# ProposedTestInput / ProposedTest models
# ---------------------------------------------------------------------------


class TestProposedTestInput:
    def test_defaults_are_empty(self) -> None:
        from law_ai.agents_runtime.crews.test_synthesizer import ProposedTestInput

        inp = ProposedTestInput(module_path="law_ai.eval.scoring")
        assert inp.missing_lines == []
        assert inp.context_snippet == ""

    def test_fields_stored(self) -> None:
        from law_ai.agents_runtime.crews.test_synthesizer import ProposedTestInput

        inp = ProposedTestInput(
            module_path="law_ai.eval.loaders",
            missing_lines=[10, 20],
            context_snippet="def load_task(subset):\n    ...",
        )
        assert inp.module_path == "law_ai.eval.loaders"
        assert inp.missing_lines == [10, 20]


# ---------------------------------------------------------------------------
# _extract_code_block
# ---------------------------------------------------------------------------


class TestExtractCodeBlock:
    def test_extracts_fenced_block(self) -> None:
        from law_ai.agents_runtime.crews.test_synthesizer import _extract_code_block

        raw = "Some preamble\n```python\nprint('hello')\n```\nsome trailing text"
        assert _extract_code_block(raw) == "print('hello')"

    def test_falls_back_to_raw_when_no_fence(self) -> None:
        from law_ai.agents_runtime.crews.test_synthesizer import _extract_code_block

        raw = "print('hello')"
        assert _extract_code_block(raw) == "print('hello')"


# ---------------------------------------------------------------------------
# _ensure_skip_decorator
# ---------------------------------------------------------------------------


class TestEnsureSkipDecorator:
    def test_adds_decorator_when_missing(self) -> None:
        from law_ai.agents_runtime.crews.test_synthesizer import (
            _ensure_skip_decorator,
        )

        src = "def test_something() -> None:\n    assert True"
        result = _ensure_skip_decorator(src)
        assert '@pytest.mark.skip("autonomy-proposed")' in result
        lines = result.splitlines()
        skip_idx = next(i for i, line in enumerate(lines) if "mark.skip" in line)
        assert lines[skip_idx + 1].startswith("def test_something")

    def test_does_not_double_add(self) -> None:
        from law_ai.agents_runtime.crews.test_synthesizer import (
            _ensure_skip_decorator,
        )

        src = '@pytest.mark.skip("autonomy-proposed")\ndef test_something() -> None:\n    assert True'
        result = _ensure_skip_decorator(src)
        assert result.count("mark.skip") == 1


# ---------------------------------------------------------------------------
# run() — end-to-end with Ollama mocked
# ---------------------------------------------------------------------------


class TestTestSynthesizerRun:
    def test_run_creates_proposed_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run() writes a .proposed.py file with the skip decorator."""
        from law_ai.agents_runtime.crews import test_synthesizer as ts_module
        from law_ai.agents_runtime.crews.test_synthesizer import (
            ProposedTestInput,
            TestSynthesizer,
        )

        # Redirect proposed output dir to tmp_path
        monkeypatch.setattr(ts_module, "_PROPOSED_DIR", tmp_path)

        with patch.object(ts_module, "_call_ollama", return_value=_FAKE_LLM_RESPONSE):
            synth = TestSynthesizer()
            result = synth.run(
                ProposedTestInput(
                    module_path="law_ai.eval.scoring",
                    missing_lines=[42],
                    context_snippet="def score_response(...):\n    ...",
                )
            )

        assert result.proposed_file.exists()
        content = result.proposed_file.read_text(encoding="utf-8")
        assert '@pytest.mark.skip("autonomy-proposed")' in content
        assert result.skipped is True

    def test_run_file_name_matches_module(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.agents_runtime.crews import test_synthesizer as ts_module
        from law_ai.agents_runtime.crews.test_synthesizer import (
            ProposedTestInput,
            TestSynthesizer,
        )

        monkeypatch.setattr(ts_module, "_PROPOSED_DIR", tmp_path)

        with patch.object(ts_module, "_call_ollama", return_value=_FAKE_LLM_RESPONSE):
            result = TestSynthesizer().run(
                ProposedTestInput(module_path="law_ai.eval.loaders")
            )

        assert "law_ai_eval_loaders" in result.proposed_file.name
        assert result.proposed_file.name.endswith("__autonomy.proposed.py")

    def test_run_logs_provenance(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run() calls audit_jsonl.record() with the required provenance fields."""
        from law_ai.agents_runtime.crews import test_synthesizer as ts_module
        from law_ai.agents_runtime.crews.test_synthesizer import (
            ProposedTestInput,
            TestSynthesizer,
        )
        from law_ai.core import audit_jsonl

        monkeypatch.setattr(ts_module, "_PROPOSED_DIR", tmp_path)

        recorded: list[dict] = []
        monkeypatch.setattr(audit_jsonl, "record", recorded.append)

        with patch.object(ts_module, "_call_ollama", return_value=_FAKE_LLM_RESPONSE):
            TestSynthesizer().run(
                ProposedTestInput(module_path="law_ai.eval.scoring")
            )

        assert len(recorded) == 1
        ev = recorded[0]
        assert ev["type"] == "test_synthesizer.proposed"
        assert "trace_id" in ev
        assert ev["source"] == "autonomy"
        assert ev["confidence"] == 1.0
        assert "agent_version" in ev

    def test_run_raises_on_ollama_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.agents_runtime.crews import test_synthesizer as ts_module
        from law_ai.agents_runtime.crews.test_synthesizer import (
            ProposedTestInput,
            TestSynthesizer,
        )

        monkeypatch.setattr(ts_module, "_PROPOSED_DIR", tmp_path)

        with (
            patch.object(
                ts_module,
                "_call_ollama",
                side_effect=RuntimeError("connection refused"),
            ),
            pytest.raises(RuntimeError, match="connection refused"),
        ):
            TestSynthesizer().run(
                ProposedTestInput(module_path="law_ai.eval.scoring")
            )

    def test_human_approval_required_is_true(self) -> None:
        from law_ai.agents_runtime.crews.test_synthesizer import TestSynthesizer

        assert TestSynthesizer.human_approval_required is True
