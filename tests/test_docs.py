"""Documentation presence + minimal-content checks.

AGENTS.md lists the canonical doc set. We assert each exists and is
non-trivial so silent deletions / empties trip CI.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke


REQUIRED_DOCS = [
    "docs/architecture.md",
    "docs/agent-roles.md",
    "docs/constitution.md",
    "docs/AO-SDLC.md",
    "docs/data-model.md",
    "docs/data-sources.md",
    "docs/related-github-repos.md",
]

REQUIRED_PROMPTS = [
    "prompts/specify.md",
    "prompts/clarify.md",
    "prompts/plan.md",
    "prompts/tasks.md",
    "prompts/implement.md",
    "prompts/evolve.md",
    "prompts/new-agent.md",
    "prompts/implement-feature.md",
]


@pytest.mark.parametrize("relpath", REQUIRED_DOCS + REQUIRED_PROMPTS)
def test_doc_exists_and_nontrivial(repo_root: Path, relpath: str) -> None:
    path = repo_root / relpath
    assert path.is_file(), f"missing documentation file: {relpath}"
    content = path.read_text().strip()
    assert len(content) > 200, f"{relpath} appears stub/empty (<200 chars)"


def test_agents_md_mentions_copilot_only_policy(repo_root: Path) -> None:
    text = (repo_root / "AGENTS.md").read_text().lower()
    assert "github copilot" in text
    assert "forbidden" in text, "AGENTS.md must spell out the forbidden agents list"
