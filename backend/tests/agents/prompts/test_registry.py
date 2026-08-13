"""Spec 036 FR-1/FR-2 — local prompt discovery.

Exercises the real prompt files shipped in the repo (they are part of the
package, not fixtures) plus tmp-dir cases for the AO-SDLC family.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from law_ai.agents_runtime.prompts.registry import (
    IDENTIFIER_RE,
    LocalPrompt,
    iter_local_prompts,
)


def _by_name(prompts: list[LocalPrompt]) -> dict[str, list[LocalPrompt]]:
    grouped: dict[str, list[LocalPrompt]] = {}
    for p in prompts:
        grouped.setdefault(p.name, []).append(p)
    return grouped


def test_discovers_versioned_runtime_prompts() -> None:
    grouped = _by_name(iter_local_prompts())
    versions = {p.version for p in grouped["lsat_content_author"]}
    assert versions == {1, 2}
    tags = {p.tag for p in grouped["lsat_content_author"]}
    assert tags == {"v1", "v2"}


def test_discovers_legal_workflow_node_prompts_unversioned() -> None:
    grouped = _by_name(iter_local_prompts())
    for node in ("analyze", "cite_check", "retrieve"):
        entries = grouped[f"legal_workflow_{node}"]
        assert len(entries) == 1
        assert entries[0].version is None
        assert entries[0].tag is None


def test_every_name_is_a_valid_phoenix_identifier() -> None:
    prompts = iter_local_prompts()
    assert prompts, "registry must never be empty"
    for p in prompts:
        assert IDENTIFIER_RE.match(p.name), p.name
        assert p.family in {"runtime", "sdlc"}


def test_sha256_matches_file_content() -> None:
    prompt = next(p for p in iter_local_prompts() if p.family == "runtime")
    raw = prompt.path.read_text(encoding="utf-8")
    assert prompt.text == raw
    assert prompt.sha256 == hashlib.sha256(raw.encode("utf-8")).hexdigest()


def test_sdlc_family_from_override_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "clarify.md").write_text("# clarify\n", encoding="utf-8")
    (tmp_path / "implement-feature.md").write_text("# impl\n", encoding="utf-8")
    monkeypatch.setenv("LAW_AI_SDLC_PROMPTS_DIR", str(tmp_path))

    sdlc = [p for p in iter_local_prompts() if p.family == "sdlc"]
    names = {p.name for p in sdlc}
    assert names == {"sdlc_clarify", "sdlc_implement_feature"}
    assert all(p.version is None for p in sdlc)


def test_missing_sdlc_dir_is_tolerated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LAW_AI_SDLC_PROMPTS_DIR", str(tmp_path / "nope"))
    prompts = iter_local_prompts()
    assert [p for p in prompts if p.family == "sdlc"] == []
    # runtime family is unaffected
    assert any(p.family == "runtime" for p in prompts)
