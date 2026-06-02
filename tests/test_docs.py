"""Documentation presence + minimal-content checks.

AGENTS.md lists the canonical doc set. We assert each exists and is
non-trivial so silent deletions / empties trip CI.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke


REQUIRED_DOCS = [
    "docs/architecture.md",
    "docs/agent-roles.md",
    "docs/constitution.md",
    "docs/ao-sdlc.md",
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


def test_agents_md_mentions_orchestration_policy(repo_root: Path) -> None:
    text = (repo_root / "AGENTS.md").read_text().lower()
    assert "github copilot" in text
    assert "claude code" in text, "AGENTS.md must name Claude Code as a sanctioned surface"
    assert "forbidden" in text, "AGENTS.md must spell out the forbidden agents list"


# Directories that never contain authored Markdown we control (deps, build
# artifacts, VCS, tool caches). Mirrors the spec_validator / backlog_lint skip
# philosophy so the scan stays fast and false-positive-free.
_LINK_SCAN_SKIP_DIRS = {
    ".git", "node_modules", ".next", ".venv", "htmlcov", "coverage",
    ".ruff_cache", ".pytest_cache", "__pycache__", ".mypy_cache", "staticfiles",
}
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _exists_case_exact(path: Path) -> bool:
    """True only if every path component matches on-disk casing.

    ``Path.exists()`` is case-insensitive on macOS/Windows, so it would hide the
    very bug we guard against. Walk each component against its parent's real
    directory listing to enforce exact case (Linux/CI semantics).
    """
    path = path.resolve()
    if not path.exists():
        return False
    cur = Path(path.anchor)
    for part in path.relative_to(path.anchor).parts:
        try:
            entries = os.listdir(cur)
        except OSError:
            return False
        if part not in entries:
            return False
        cur = cur / part
    return True


def _case_insensitive_variant_exists(path: Path) -> bool:
    """True if a file exists at ``path`` ignoring case (right file, wrong case)."""
    path = path.resolve()
    cur = Path(path.anchor)
    for part in path.relative_to(path.anchor).parts:
        try:
            entries = os.listdir(cur)
        except OSError:
            return False
        match = next((e for e in entries if e.lower() == part.lower()), None)
        if match is None:
            return False
        cur = cur / match
    return True


def test_no_case_mismatched_doc_links(repo_root: Path) -> None:
    """Markdown links must resolve case-exactly on case-sensitive filesystems.

    Flags only *case-only* mismatches — a link whose target does not exist with
    the referenced casing but does exist under a different case. Genuinely
    missing / moved targets (e.g. historical ``backend/app/*`` references) have
    no case variant on disk and are intentionally ignored, so this guard
    isolates the case-mismatch bug class fixed by specs/020.
    """
    offenders: list[str] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in _LINK_SCAN_SKIP_DIRS]
        for filename in filenames:
            if not filename.endswith(".md"):
                continue
            md = Path(dirpath) / filename
            text = md.read_text(encoding="utf-8", errors="ignore")
            for match in _MD_LINK_RE.finditer(text):
                raw = match.group(1).strip()
                if not raw:
                    continue
                href = raw.split()[0].split("#")[0].split("?")[0]
                if not href or href.startswith(
                    ("http://", "https://", "mailto:", "tel:", "#")
                ):
                    continue
                target = md.parent / href
                if _exists_case_exact(target):
                    continue
                if _case_insensitive_variant_exists(target):
                    offenders.append(f"{md.relative_to(repo_root)} -> {href}")
    assert not offenders, (
        "Markdown links reference files that exist only under a different case "
        "(broken on Linux/CI). Fix the link casing:\n  " + "\n  ".join(sorted(offenders))
    )
