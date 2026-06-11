"""Unit tests for the versioned prompt registry (spec 024 AC-5)."""

from __future__ import annotations

import pytest

from lawgraph.agents_runtime.prompts.loader import PromptTemplate, load_prompt


class TestLoadPrompt:
    def test_explicit_version_resolves_versioned_file(self) -> None:
        tpl = load_prompt("lsat_content_author", version="2")
        assert tpl.prompt_id == "lsat_content_author"
        assert tpl.version == "2"
        assert tpl.path.name == "lsat_content_author.v2.md"
        assert tpl.text
        assert len(tpl.sha256) == 64

    def test_no_version_picks_highest(self) -> None:
        tpl = load_prompt("lsat_content_author")
        assert tpl.version == "2"

    def test_nested_unversioned_file_resolves(self) -> None:
        tpl = load_prompt("legal_workflow/retrieve", version="1")
        assert tpl.path.name == "retrieve.md"
        assert tpl.version == "1"

    def test_metadata_comment_is_stripped(self) -> None:
        tpl = load_prompt("legal_workflow/retrieve", version="1")
        assert "<!--" not in tpl.text
        assert tpl.text.startswith("You are a legal research assistant.")

    def test_missing_prompt_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_prompt("does_not_exist", version="9")


class TestRender:
    def test_placeholders_substituted_and_json_braces_preserved(self) -> None:
        tpl = PromptTemplate(
            prompt_id="t",
            version="1",
            text='Return JSON: {"queries": [str]}\nQ: {{question}}',
            sha256="0" * 64,
            path=load_prompt("legal_workflow/retrieve", version="1").path,
        )
        rendered = tpl.render(question="What is mens rea?")
        assert 'Return JSON: {"queries": [str]}' in rendered
        assert "Q: What is mens rea?" in rendered
        assert "{{question}}" not in rendered

    def test_legal_workflow_templates_render_legacy_strings(self) -> None:
        retrieve = load_prompt("legal_workflow/retrieve", version="1").render(
            jurisdiction="any", question="Is parody fair use?"
        )
        assert "Jurisdiction: any" in retrieve
        assert "Question: Is parody fair use?" in retrieve
        assert 'Return ONLY JSON: {"queries": [str], "rationale": str}' in retrieve

        analyze = load_prompt("legal_workflow/analyze", version="1").render(
            question="Q", passages="[1] Title — snippet"
        )
        assert "using ONLY the passages below" in analyze
        assert "Passages:\n[1] Title — snippet" in analyze
