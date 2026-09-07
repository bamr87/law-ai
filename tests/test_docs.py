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


def test_solve_guides_have_their_own_runbook(repo_root: Path) -> None:
    """BL-20260905-55 — guide operations are not the library's runbook.

    The library doc is about prose articles and explicitly distinguishes them
    from guides, so the guide runbook lives on its own page with a
    cross-reference left behind.
    """
    guides = repo_root / "docs/lsat-solve-guides.md"
    assert guides.is_file(), "docs/lsat-solve-guides.md must exist"
    text = guides.read_text()
    for token in ("lsat_guide_backfill", "guides.json", "judge"):
        assert token in text, f"the guide runbook must cover {token}"

    library = (repo_root / "docs/lsat-library.md").read_text()
    assert "lsat-solve-guides.md" in library, (
        "docs/lsat-library.md must cross-reference the guide runbook it no "
        "longer carries"
    )
    assert "make lsat-guide-backfill" not in library, (
        "the guide runbook moved out of the library doc; keep one home for it"
    )


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


def test_autonomy_invariant_i4_matches_the_implementation(repo_root: Path) -> None:
    """BL-20260906-27: I4 drifted behind `run_cycle`.

    Two behaviours the invariant text did not name: `--cycle-id` makes a cycle
    idempotent (a replay, not a re-run), and every cycle is projected into
    `audit.AutonomyRun`. An invariant that omits half of what the entry point
    guarantees cannot be the thing review checks against.
    """
    constitution = (repo_root / "docs" / "constitution.md").read_text()
    i4 = next(
        line for line in constitution.splitlines() if line.startswith("- **I4 —")
    )
    assert "AutonomyRun" in i4, "I4 must name the queryable projection"
    assert "--cycle-id" in i4 and "replay" in i4.lower(), (
        "I4 must state that --cycle-id makes run_cycle idempotent"
    )


def test_ao_sdlc_guide_stays_a_redirect_stub(repo_root: Path) -> None:
    """BL-20260906-38: the stub kept attracting documentation.

    `docs/ao-sdlc-guide.md` exists only so old `specs/` links resolve. It must
    say so in as many words, and name both places real prose goes, or the next
    agent writes a CI section into a file nobody reads.
    """
    stub = (repo_root / "docs" / "ao-sdlc-guide.md").read_text()
    assert "not a documentation target" in stub.lower()
    assert "ao-sdlc.md" in stub and "AO-SDLC_Outline_Guide.md" in stub


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


def _link_problem(target: Path) -> str | None:
    """Classify one link target: ``"case"``, ``"missing"``, or None when fine.

    BL-20260906-50 folded the old ``test_no_case_mismatched_doc_links`` walk in
    here. A case-only mismatch is worth naming separately because it passes on
    macOS and fails only on Linux/CI, so the fix ("change the casing") is a
    different instruction from the fix for a genuinely dead path.
    """
    if _exists_case_exact(target):
        return None
    return "case" if _case_insensitive_variant_exists(target) else "missing"


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


def test_layout_preferences_are_documented_as_user_scoped(repo_root: Path) -> None:
    """BL-20260906-75 — the layout paragraph must not still say instance-only.

    BL-20260905-10 moved the ``ui.*`` / ``lsat.timer.*`` / ``lsat.library.*``
    keys to the user scope with the instance value as the inherited default,
    and ``SettingsForm`` grew a scope chooser. The spec-050 paragraph still
    described the store as instance-scoped, which is the one sentence a reader
    would take at face value.
    """
    text = (repo_root / "docs" / "ui-ux.md").read_text(encoding="utf-8")
    assert "instance-scoped store" not in text, (
        "docs/ui-ux.md calls the layout-preference store instance-scoped; "
        "since BL-20260905-10 those keys are settable at user scope."
    )
    for token in ("USER_SETTABLE", "scope chooser", "BL-20260905-10"):
        assert token in text, (
            f"docs/ui-ux.md no longer names {token} — the layout-preference "
            "scope story (BL-20260905-10) has to survive doc edits."
        )


def test_proposed_tests_endpoint_is_documented(repo_root: Path) -> None:
    """BL-20260906-56 — the autonomy review route must be findable in the docs.

    ``GET /api/agents/proposed-tests`` shipped with BL-20260511-17 but was
    listed nowhere alongside the other ``/api/agents`` reads, so a reviewer
    looking for what the loop has drafted had to read ``urls.py``. Pin both
    the curl reference and the architecture note.
    """
    docs = repo_root / "docs"
    for relpath in ("api-examples.md", "architecture.md"):
        text = (docs / relpath).read_text(encoding="utf-8")
        assert "/api/agents/proposed-tests" in text, (
            f"docs/{relpath} no longer documents GET /api/agents/proposed-tests "
            "(AgentProposedTestsView in backend/law_ai/agentsapi/urls.py)."
        )
    examples = (docs / "api-examples.md").read_text(encoding="utf-8")
    assert "backend/tests/autonomy/proposed/" in examples, (
        "docs/api-examples.md must name the fixed directory the endpoint "
        "globs — that the path is not a request parameter is the point."
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

    The promoted form of the old ``test_no_case_mismatched_doc_links``
    (BL-20260602-04, surfaced by specs/021): that guard only caught links whose
    target existed under a different case, so the ~114 dead ``backend/app/*``
    hrefs left over from the pre-Django layout sailed through. Paths that
    describe deleted code are inline code spans now; anything still written as
    a link must resolve.

    BL-20260906-50: the case-only walk is folded in here rather than run twice.
    Existence subsumes case-exactness, so the second scan only ever added a
    second traversal — but its *message* said something this one did not, and
    that half is kept: a case-only mismatch is reported as a casing fix, and it
    is never allowlisted, because "wrong case" is never a deliberate reference
    to something deleted.
    """
    missing: list[str] = []
    case_only: list[str] = []
    for md in _tracked_markdown(repo_root):
        text = md.read_text(encoding="utf-8", errors="ignore")
        for lineno, href in _link_targets(text):
            problem = _link_problem(md.parent / href)
            if problem is None:
                continue
            rel = f"{md.relative_to(repo_root)}:{lineno} -> {href}"
            if problem == "case":
                case_only.append(rel)
            elif rel.split(" ->")[0].split(":")[0] not in _BROKEN_LINK_ALLOWLIST:
                missing.append(rel)

    assert not case_only, (
        "Markdown links reference files that exist only under a different case "
        "(fine on macOS, broken on Linux/CI). Fix the link casing:\n  "
        + "\n  ".join(sorted(case_only))
    )
    assert not missing, (
        "Markdown links point at files that do not exist. Fix the href, or "
        "render the path as an inline code span if it names deleted code:\n  "
        + "\n  ".join(sorted(missing))
    )


def test_link_problem_separates_wrong_case_from_missing(tmp_path: Path) -> None:
    """BL-20260906-50: folding the two scanners kept both verdicts.

    The strict existence check alone would call a wrong-case link "missing",
    which sends the reader looking for a file that is right there.
    """
    (tmp_path / "Docs").mkdir()
    (tmp_path / "Docs" / "Guide.md").write_text("# Guide\n", encoding="utf-8")

    assert _link_problem(tmp_path / "Docs" / "Guide.md") is None
    assert _link_problem(tmp_path / "docs" / "guide.md") == "case"
    assert _link_problem(tmp_path / "Docs" / "Missing.md") == "missing"
