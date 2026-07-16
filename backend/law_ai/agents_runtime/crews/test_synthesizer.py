"""TestSynthesizer crew — autonomous propose-only test generator (spec 018 T-004).

Reads low-coverage modules from ``law_ai.eval.coverage_audit``, uses Ollama to
generate a pytest skeleton, and writes an ``<module>__autonomy.proposed.py``
file decorated with ``@pytest.mark.skip("autonomy-proposed")`` so it never runs
automatically.

Constitution §12 invariants
-----------------------------
- I1 (no auto-merge): proposed files are decoration-skipped; they NEVER run in CI
  without explicit human review.
- I2 (allow-list): ``AUTONOMY_ENABLED`` and ``AUTONOMY_ALLOWED_SOURCES`` are
  checked by the caller (``run_autonomy`` mgmt cmd); this class does not bypass them.
- I4 (one entry point): all calls come through ``run()``.
- I5 (propose-only): output is ``.proposed.py``; no existing tests are modified.
- I6 (provenance): every LLM call logged via ``law_ai.core.audit_jsonl``.
"""

from __future__ import annotations

import logging
import re
import textwrap
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from law_ai.core import audit_jsonl

logger = logging.getLogger("law_ai.agents_runtime.crews.test_synthesizer")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGENT_VERSION = "law_ai.agents_runtime.crews.test_synthesizer.v1"
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "test_synthesizer.v1.md"
_PROPOSED_DIR = Path("backend/tests/autonomy/proposed")
_SKIP_DECORATOR = '@pytest.mark.skip("autonomy-proposed")'
_SKIP_MARKER = "autonomy-proposed"


# ---------------------------------------------------------------------------
# Pydantic I/O models
# ---------------------------------------------------------------------------


class ProposedTestInput(BaseModel):
    """Input to TestSynthesizer.run()."""

    module_path: str = Field(
        ..., description="Dotted Python path of the module under test."
    )
    missing_lines: list[int] = Field(
        default_factory=list, description="Uncovered line numbers."
    )
    context_snippet: str = Field(
        default="",
        description="Up to 20 lines of source code around the first uncovered line.",
    )


class ProposedTest(BaseModel):
    """Output from TestSynthesizer.run()."""

    proposed_file: Path = Field(
        ..., description="Absolute path to the emitted .proposed.py file."
    )
    test_source: str = Field(..., description="Full content of the proposed test file.")
    trace_id: str = Field(..., description="Provenance trace_id for the LLM call.")
    model: str = Field(..., description="Ollama model used for synthesis.")
    skipped: bool = Field(
        True,
        description="Always True — proposed tests carry @pytest.mark.skip.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_prompt_template() -> str:
    """Read the versioned prompt template from disk."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _call_ollama(prompt: str, *, model: str, base_url: str, timeout: int = 120) -> str:
    """POST to Ollama /api/generate and return the response text."""
    import json

    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return str(data.get("response", ""))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama call failed: {exc}") from exc


def _extract_code_block(llm_output: str) -> str:
    """Extract the first fenced Python code block from the LLM output."""
    pattern = re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL)
    match = pattern.search(llm_output)
    if match:
        return match.group(1).strip()
    # Fallback: return raw output stripped
    return llm_output.strip()


def _ensure_skip_decorator(source: str) -> str:
    """Guarantee the skip decorator is present on every test_ function."""
    lines = source.splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("def test_") and (
            i == 0 or not lines[i - 1].lstrip().startswith("@pytest.mark.skip")
        ):
            indent = line[: len(line) - len(stripped)]
            out.append(f"{indent}{_SKIP_DECORATOR}")
        out.append(line)
    return "\n".join(out)


def _module_to_file_stem(module_path: str) -> str:
    """Convert ``law_ai.eval.scoring`` → ``law_ai_eval_scoring``."""
    return module_path.replace(".", "_")


# ---------------------------------------------------------------------------
# Main crew class
# ---------------------------------------------------------------------------


class TestSynthesizer:
    """Crew member that proposes new pytest skeletons for under-tested modules.

    Usage::

        synth = TestSynthesizer()
        result = synth.run(ProposedTestInput(
            module_path="law_ai.eval.scoring",
            missing_lines=[42, 55, 60],
        ))
        print(result.proposed_file)
    """

    name = "TestSynthesizer"
    human_approval_required: bool = True  # Constitution §12 I1: human reviews proposals

    def run(self, input: ProposedTestInput) -> ProposedTest:
        """Generate a propose-only test file for the given module.

        Args:
            input: :class:`ProposedTestInput` with module path + coverage info.

        Returns:
            :class:`ProposedTest` pointing to the written ``.proposed.py`` file.

        Raises:
            RuntimeError: If the Ollama call fails.
        """
        from django.conf import settings

        base_url: str = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        model: str = getattr(
            settings, "OLLAMA_DEFAULT_MODEL", "llama3.1:8b-instruct-q4_K_M"
        )

        prompt_template = _load_prompt_template()
        prompt = textwrap.dedent(f"""
            {prompt_template}

            ## Current task

            - **module_path**: `{input.module_path}`
            - **missing_lines**: {input.missing_lines}
            - **context_snippet**:
            ```python
            {input.context_snippet or "(not provided)"}
            ```
        """).strip()

        trace_id = str(uuid4())
        started_at = datetime.now(UTC).isoformat()

        raw_output = _call_ollama(prompt, model=model, base_url=base_url)
        finished_at = datetime.now(UTC).isoformat()

        code = _extract_code_block(raw_output)
        code = _ensure_skip_decorator(code)

        # Build proposed file
        stem = _module_to_file_stem(input.module_path)
        proposed_dir = Path(_PROPOSED_DIR)
        proposed_dir.mkdir(parents=True, exist_ok=True)

        proposed_file = proposed_dir / f"{stem}__autonomy.proposed.py"
        header = (
            f"# autonomy-proposed — generated by {AGENT_VERSION}\n"
            f"# trace_id: {trace_id}\n"
            f"# DO NOT MERGE without human review.\n"
            f"# Run:  pytest {proposed_file} -m 'not autonomy-proposed'  (dry-run)\n"
            f"#       pytest --co {proposed_file}  (collect only)\n"
            "import pytest\n\n"
        )
        full_source = header + code + "\n"
        proposed_file.write_text(full_source, encoding="utf-8")

        # Provenance — constitution §12 I6
        audit_jsonl.record(
            {
                "type": "test_synthesizer.proposed",
                "trace_id": trace_id,
                "agent_version": AGENT_VERSION,
                "source": "autonomy",
                "confidence": 1.0,
                "module_path": input.module_path,
                "missing_lines_count": len(input.missing_lines),
                "proposed_file": str(proposed_file),
                "model": model,
                "started_at": started_at,
                "finished_at": finished_at,
            }
        )

        logger.info(
            "TestSynthesizer: proposed %s (trace_id=%s)",
            proposed_file,
            trace_id,
        )

        return ProposedTest(
            proposed_file=proposed_file,
            test_source=full_source,
            trace_id=trace_id,
            model=model,
            skipped=True,
        )
