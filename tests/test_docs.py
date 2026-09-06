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
    "docs/philosophy.md",
    "docs/ao-sdlc.md",
    "docs/data-model.md",
    "docs/data-sources.md",
    "docs/related-github-repos.md",
    "docs/ui-ux.md",
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


def test_jurisprudential_stance_is_stated_and_enforced(repo_root: Path) -> None:
    """The philosophy must keep both halves, and stay wired to an enforcing clause.

    Recorded by docs/adr/0004-jurisprudential-stance.md. The stance is only
    coherent as a *descriptive* premise about the corpus paired with its
    *normative* rejection as a design goal — a future edit that keeps one half
    and drops the other flips the project's meaning, so both are asserted.
    """
    philosophy = (repo_root / "docs" / "philosophy.md").read_text().lower()
    assert "interest of the stronger" in philosophy, (
        "docs/philosophy.md must state the Thrasymachean premise it is built on"
    )
    assert "descriptiv" in philosophy and "normativ" in philosophy, (
        "docs/philosophy.md must keep the descriptive/normative split — the "
        "premise is adopted about the data and rejected as a design goal"
    )

    constitution = (repo_root / "docs" / "constitution.md").read_text().lower()
    assert "## 13." in constitution, "constitution must retain §13 (jurisprudential honesty)"
    assert "philosophy.md" in constitution, (
        "constitution §13 must link back to docs/philosophy.md"
    )

    agents = (repo_root / "AGENTS.md").read_text().lower()
    assert "philosophy.md" in agents, "AGENTS.md must point agents at the philosophy"


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


def test_architecture_documents_every_lsat_content_type(repo_root: Path) -> None:
    """docs/architecture.md must name all four LSAT section types + their loaders.

    BL-20260831-29: the architecture doc described the LSAT module as
    multiple-choice only, so the Argumentative Writing content type
    (`writing.py`, `writing_prompts.json`, `writing_rubrics.json`, spec 047)
    was invisible to anyone reading the architecture first. Pin the row so a
    fifth content type cannot ship without the doc noticing.
    """
    text = (repo_root / "docs" / "architecture.md").read_text(encoding="utf-8")
    missing = [
        token
        for token in (
            "bank.py",
            "guides.py",
            "writing.py",
            "writing_prompts.json",
            "writing_rubrics.json",
            "Argumentative Writing",
            "/api/lsat/writing/evaluate",
        )
        if token not in text
    ]
    assert not missing, (
        "docs/architecture.md no longer documents the LSAT content types "
        f"(missing: {', '.join(missing)}). Update the 'LSAT content types' row."
    )


_CODE_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
# Deliberately-broken links, if any ever have to exist. Keep this empty:
# a historical path belongs in an inline code span, not in a dead href
# (see specs/011-django-backend and docs/adr/0001, BL-20260602-04).
_BROKEN_LINK_ALLOWLIST: set[str] = set()


def _tracked_markdown(repo_root: Path) -> list[Path]:
    """Every ``*.md`` file git knows about, as absolute paths that still exist.

    Tracked plus not-ignored-untracked: a doc added in the working tree is
    checked immediately, while `.claude/worktrees/` and other ignored scratch
    copies — which carry stale links nobody can fix from this repo — stay out.
    """
    from tests.conftest import run_subprocess

    result = run_subprocess(
        # --others --exclude-standard so a doc added in this working tree is
        # checked before it is committed, while .gitignore'd copies stay out.
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.md"],
        cwd=repo_root,
    )
    assert result.returncode == 0, f"git ls-files failed: {result.stderr}"
    paths = [repo_root / rel for rel in result.stdout.split("\0") if rel]
    return [p for p in paths if p.is_file()]


def _link_targets(text: str):
    """Yield (line_number, href) for every markdown link outside code."""
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if _CODE_FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in _MD_LINK_RE.finditer(_INLINE_CODE_RE.sub("", line)):
            raw = match.group(1).strip()
            if not raw:
                continue
            href = raw.split()[0].split("#")[0].split("?")[0]
            if not href or href.startswith(
                ("http://", "https://", "mailto:", "tel:", "#", "<")
            ):
                continue
            yield lineno, href


def test_no_broken_relative_doc_links(repo_root: Path) -> None:
    """Every relative markdown link must point at a file that exists.

    The promoted form of ``test_no_case_mismatched_doc_links`` (BL-20260602-04,
    surfaced by specs/021): that guard only caught links whose target existed
    under a different case, so the ~114 dead ``backend/app/*`` hrefs left over
    from the pre-Django layout sailed through. Paths that describe deleted code
    are inline code spans now; anything still written as a link must resolve.
    """
    offenders: list[str] = []
    for md in _tracked_markdown(repo_root):
        for lineno, href in _link_targets(md.read_text(encoding="utf-8", errors="ignore")):
            target = md.parent / href
            if _exists_case_exact(target):
                continue
            rel = f"{md.relative_to(repo_root)}:{lineno} -> {href}"
            if rel.split(" ->")[0].split(":")[0] in _BROKEN_LINK_ALLOWLIST:
                continue
            offenders.append(rel)
    assert not offenders, (
        "Markdown links point at files that do not exist. Fix the href, or "
        "render the path as an inline code span if it names deleted code:\n  "
        + "\n  ".join(sorted(offenders))
    )
