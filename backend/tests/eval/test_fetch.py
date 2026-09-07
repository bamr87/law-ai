"""Tests for the LegalBench dataset fetcher (BL-20260811-09).

Every test is offline: :func:`law_ai.eval.fetch.fetch_subsets` takes an
injected ``download`` callable, so the suite exercises the real conversion,
licence-review and checksum logic against in-memory fixtures and never
touches the network (or a model).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from law_ai.eval import fetch as fetch_mod
from law_ai.eval.fetch import (
    ALLOWED_LICENCES,
    SUBSET_TASKS,
    LegalBenchFetchError,
    fetch_subsets,
    fetch_task,
    interleave,
    load_manifest,
    parse_licence,
    parse_tsv,
    render_prompt,
    verify_digests,
)
from law_ai.eval.legalbench import ALLOWED_SUBSETS

CC_BY_README = "# hearsay\n\n**Source**: Neel Guha\n\n**License**: [CC By 4.0](https://creativecommons.org/licenses/by/4.0/)\n"
PROMPT = "Is there hearsay?\n\nQ: {{text}} Is there hearsay?\nA:"
TSV = "index\tanswer\ttext\tslice\n0\tNo\tDavid ran fast.\tNon-assertive\n1\tYes\tRebecca said so.\tStandard\n"


def _fixture_downloader(
    *,
    readme: str = CC_BY_README,
    prompt: str = PROMPT,
    tsv: str = TSV,
    missing: tuple[str, ...] = ("README.MD",),
) -> Any:
    """Return a downloader serving the fixtures, 404-ing anything in ``missing``."""

    def download(url: str) -> bytes:
        if any(url.endswith(name) for name in missing):
            raise LegalBenchFetchError(f"could not download {url}: 404")
        if url.endswith("README.md") or url.endswith("README.MD"):
            return readme.encode()
        if url.endswith("base_prompt.txt"):
            return prompt.encode()
        if url.endswith("test.tsv"):
            return tsv.encode()
        raise AssertionError(f"unexpected url {url}")

    return download


@pytest.fixture()
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the subset cache + manifest at a temp directory."""
    root = tmp_path / "legalbench"
    monkeypatch.setattr(
        fetch_mod, "subset_cache_path", lambda subset: root / subset / "items.jsonl"
    )
    monkeypatch.setattr(fetch_mod, "MANIFEST_PATH", root / "manifest.json")
    return root


class TestParsing:
    def test_parse_licence_normalises_casing_and_links(self) -> None:
        assert parse_licence(CC_BY_README) == "cc-by-4.0"
        assert (
            parse_licence("**License**: [CC BY-SA 4.0](https://x.test)")
            == "cc-by-sa-4.0"
        )

    def test_parse_licence_returns_none_when_absent(self) -> None:
        assert parse_licence("# task\n\nno licence line here\n") is None

    def test_parse_tsv_keeps_quoted_tabs_and_skips_blanks(self) -> None:
        rows = parse_tsv(TSV + "\n")
        assert len(rows) == 2
        assert rows[0] == {
            "index": "0",
            "answer": "No",
            "text": "David ran fast.",
            "slice": "Non-assertive",
        }

    def test_render_prompt_substitutes_every_column(self) -> None:
        rendered = render_prompt(
            "Text: {{text}}\nCitation: {{citation}}\nSupportive?",
            {"text": "t", "citation": "c"},
        )
        assert rendered == "Text: t\nCitation: c\nSupportive?"

    def test_render_prompt_rejects_unknown_placeholder(self) -> None:
        with pytest.raises(LegalBenchFetchError, match="unknown column"):
            render_prompt("{{circuit}}", {"text": "t"})

    def test_interleave_spreads_tasks_so_limit_samples_across_them(self) -> None:
        merged = interleave([[{"i": "a1"}, {"i": "a2"}], [{"i": "b1"}]])
        assert [row["i"] for row in merged] == ["a1", "b1", "a2"]


class TestFetchTask:
    def test_converts_tsv_rows_into_the_loader_contract(self) -> None:
        result = fetch_task("hearsay", download=_fixture_downloader())

        assert result.licence == "cc-by-4.0"
        assert [item["index"] for item in result.items] == ["hearsay-0", "hearsay-1"]
        assert result.items[0]["answer"] == "No"
        assert result.items[0]["text"].endswith(
            "Q: David ran fast. Is there hearsay?\nA:"
        )
        assert result.items[0]["metadata"] == {
            "task": "hearsay",
            "licence": "cc-by-4.0",
            "data_revision": fetch_mod.DATA_REVISION,
            "prompt_revision": fetch_mod.PROMPT_REVISION,
        }

    def test_max_items_caps_the_head_of_the_split(self) -> None:
        result = fetch_task("hearsay", max_items=1, download=_fixture_downloader())
        assert len(result.items) == 1

    def test_falls_back_to_the_uppercase_readme_spelling(self) -> None:
        """``tasks/abercrombie/README.MD`` really is spelled that way upstream."""
        result = fetch_task(
            "abercrombie", download=_fixture_downloader(missing=("README.md",))
        )
        assert result.licence == "cc-by-4.0"

    def test_unreviewable_licence_is_refused(self) -> None:
        download = _fixture_downloader(
            readme="**License**: [CC BY-NC 4.0](https://x.test)"
        )
        with pytest.raises(LegalBenchFetchError, match="not in"):
            fetch_task("hearsay", download=download)

    def test_missing_licence_is_refused(self) -> None:
        with pytest.raises(LegalBenchFetchError, match="declares no licence"):
            fetch_task("hearsay", download=_fixture_downloader(readme="# hearsay\n"))

    def test_empty_split_is_refused(self) -> None:
        download = _fixture_downloader(tsv="index\tanswer\ttext\n")
        with pytest.raises(LegalBenchFetchError, match="empty"):
            fetch_task("hearsay", download=download)


class TestManifest:
    def test_new_digests_are_recorded(self) -> None:
        manifest: dict[str, Any] = {"files": {}}
        verify_digests(manifest, {"hearsay/test.tsv": "abc"}, update=False)
        assert manifest["files"]["hearsay/test.tsv"] == "abc"

    def test_checksum_mismatch_raises(self) -> None:
        manifest: dict[str, Any] = {"files": {"hearsay/test.tsv": "abc"}}
        with pytest.raises(LegalBenchFetchError, match="checksum mismatch"):
            verify_digests(manifest, {"hearsay/test.tsv": "def"}, update=False)

    def test_update_manifest_accepts_drift(self) -> None:
        manifest: dict[str, Any] = {"files": {"hearsay/test.tsv": "abc"}}
        verify_digests(manifest, {"hearsay/test.tsv": "def"}, update=True)
        assert manifest["files"]["hearsay/test.tsv"] == "def"


class TestFetchSubsets:
    def test_writes_jsonl_and_manifest(self, isolated_cache: Path) -> None:
        written = fetch_subsets(
            ["causation"],
            download=_fixture_downloader(),
            manifest_path=isolated_cache / "manifest.json",
        )

        path = written["causation"]
        lines = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        ]
        assert len(lines) == 2
        assert {"index", "text", "answer", "metadata"} <= set(lines[0])

        manifest = json.loads((isolated_cache / "manifest.json").read_text())
        assert manifest["data_revision"] == fetch_mod.DATA_REVISION
        assert manifest["prompt_revision"] == fetch_mod.PROMPT_REVISION
        digest = hashlib.sha256(TSV.encode()).hexdigest()
        assert manifest["files"]["legal_reasoning_causality/test.tsv"] == digest

    def test_second_fetch_with_changed_source_fails(self, isolated_cache: Path) -> None:
        manifest_path = isolated_cache / "manifest.json"
        fetch_subsets(
            ["causation"], download=_fixture_downloader(), manifest_path=manifest_path
        )
        moved = _fixture_downloader(tsv=TSV + "2\tNo\tSomething new.\tSlice\n")
        with pytest.raises(LegalBenchFetchError, match="checksum mismatch"):
            fetch_subsets(["causation"], download=moved, manifest_path=manifest_path)

    def test_unknown_subset_is_refused(self, isolated_cache: Path) -> None:
        with pytest.raises(LegalBenchFetchError, match="no LegalBench task mapping"):
            fetch_subsets(["not_a_subset"], download=_fixture_downloader())

    def test_load_manifest_defaults_when_absent(self, tmp_path: Path) -> None:
        manifest = load_manifest(tmp_path / "nope.json")
        assert manifest["files"] == {}
        assert manifest["data_revision"] == fetch_mod.DATA_REVISION


class TestMapping:
    def test_every_allowed_subset_has_a_task_mapping(self) -> None:
        """A subset with no mapping can never leave synthetic-stub mode."""
        assert set(SUBSET_TASKS) == set(ALLOWED_SUBSETS)
        for subset, tasks in SUBSET_TASKS.items():
            assert tasks, f"{subset} maps to no LegalBench task"

    def test_revisions_are_pinned_commit_shas(self) -> None:
        for revision in (fetch_mod.DATA_REVISION, fetch_mod.PROMPT_REVISION):
            assert len(revision) == 40
            assert all(char in "0123456789abcdef" for char in revision)

    def test_allowed_licences_are_attribution_only(self) -> None:
        assert {"cc-by-4.0", "cc-by-sa-4.0"} == ALLOWED_LICENCES
