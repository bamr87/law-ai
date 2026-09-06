"""Static LSAT practice site — structure + drift gate (spec 025 FR-8/AC-4).

Stdlib-only, like the rest of the root suite. The committed site artifact
(`lsat-static/content.json`, imported at build time by the Next.js static
export) must stay in lockstep with the source bank under
`backend/law_ai/lsat/services/data/`: when a bank file changes without
`make lsat-export`, these tests fail CI so the published GitHub Pages app can
never silently lag the approved content.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "lsat-static"
CONTENT = APP / "content.json"
BANK_DIR = REPO / "backend" / "law_ai" / "lsat" / "services" / "data"

_BANK_FILES = ("lr_bank.json", "rc_bank.json", "lg_bank.json")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _bank_questions() -> dict[str, dict]:
    items: dict[str, dict] = {}
    for name in _BANK_FILES:
        for item in _load(BANK_DIR / name).get("items", []):
            items[item["id"]] = item
    return items


def _bank_question_count() -> int:
    """Raw item count across bank files (catches duplicate-id shadowing)."""
    return sum(len(_load(BANK_DIR / name).get("items", [])) for name in _BANK_FILES)


def _norm_refs(refs: list | None) -> list[dict]:
    """Drop None-valued keys: model_dump emits note=None where bank JSON omits it."""
    return [{k: v for k, v in r.items() if v is not None} for r in (refs or [])]


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


class TestSiteStructure:
    def test_required_app_files_exist(self) -> None:
        for name in (
            "content.json",
            "package.json",
            "next.config.mjs",
            "app/page.tsx",
            "app/layout.tsx",
            # spec 047 FR-3: the writing view is part of the published site.
            "components/Writing.tsx",
            # spec 048 FR-10: so is the knowledge library, at parity with the
            # platform reader.
            "components/Library.tsx",
            "components/library/BlockRenderer.tsx",
            "lib/search.ts",
        ):
            assert (APP / name).is_file(), f"missing lsat-static file: {name}"

    def test_static_export_configured(self) -> None:
        # The GitHub Pages deploy relies on a static export served under a base
        # path (spec 025 AC-5, carried over to the Next.js rebuild). Guard both
        # so a config regression can't ship a broken Pages build.
        cfg = (APP / "next.config.mjs").read_text(encoding="utf-8")
        assert "output: 'export'" in cfg, "next.config must set output:'export'"
        assert "basePath" in cfg and "PAGES_BASE_PATH" in cfg, (
            "next.config must apply a Pages base path"
        )

    def test_vanilla_site_retired(self) -> None:
        # The buildless vanilla app was replaced by the Next.js export; make
        # sure it doesn't creep back and fight over the single GitHub Pages site.
        assert not (REPO / "frontend" / "public" / "lsat-practice").exists(), (
            "the retired vanilla lsat-practice/ app should be gone"
        )


# ---------------------------------------------------------------------------
# Keyboard contract
# ---------------------------------------------------------------------------


class TestKeyboardContract:
    """The published drill has to be runnable end to end without a mouse.

    `lsat-static/` ships no component-test harness, so these are source
    assertions rather than behavioural ones: crude, but they pin the four
    properties that a browser pass found broken and that nothing else in CI
    would notice going missing again. Each is a rule about *focus*, which is
    what actually failed — the key bindings themselves were fine.
    """

    def _read(self, name: str) -> str:
        return (APP / name).read_text(encoding="utf-8")

    def test_graded_choices_stay_focusable(self) -> None:
        # `disabled` drops the element out of the focus order, so checking an
        # answer while the chosen choice had focus threw focus to <body>: no
        # ring to see, no position for a screen reader, and Tab restarting at
        # the skip link.
        card = self._read("components/QuestionCard.tsx")
        assert "aria-disabled={submitted}" in card, (
            "graded choices must use aria-disabled, not disabled"
        )
        # Every occurrence has to be the aria- one: a bare `disabled={submitted}`
        # anywhere in this card is the regression.
        assert card.count("disabled={submitted}") == card.count(
            "aria-disabled={submitted}"
        ), "a disabled choice leaves the focus order — use aria-disabled"

    def test_answers_survive_paging_back(self) -> None:
        # The card is keyed on the question id, so anything the drill does not
        # hold is destroyed on the way out and rebuilt blank on the way back —
        # which made `P` a way to lose your work rather than review it.
        drill = self._read("components/Drill.tsx")
        card = self._read("components/QuestionCard.tsx")
        assert "savedChoice" in drill and "savedChoice" in card, (
            "Drill must hand the recorded choice back to a revisited question"
        )
        assert "savedSeconds" in drill and "savedSeconds" in card, (
            "a revisited question must show the time it was answered in"
        )

    def test_question_changes_move_focus_and_announce(self) -> None:
        drill = self._read("components/Drill.tsx")
        assert "cardRef.current?.focus()" in drill, (
            "N/P must land focus on the new question, not <body>"
        )
        assert "Question ${i + 1} of ${questions.length}" in drill, (
            "N/P must announce the new position into the live region"
        )

    def test_opening_a_writing_prompt_reaches_the_editor(self) -> None:
        # O is the only key into the section; opening a prompt but leaving
        # focus six Tab stops from the textarea made it useless on its own.
        writing = self._read("components/Writing.tsx")
        assert "getElementById('writing-draft')?.focus()" in writing, (
            "O must put the caret in the essay editor"
        )

    def test_help_sheet_documents_the_drill_keys(self) -> None:
        # A shortcut nobody can discover is a shortcut nobody uses.
        help_sheet = self._read("components/ShortcutHelp.tsx")
        for keys in ("A – E", "N  /  P", "H", "J  /  K", "R", "O", "T", "M"):
            assert f"['{keys}'," in help_sheet, f"? sheet must document {keys}"


class TestSharedRovingFocus:
    """BL-20260831-08: one keyboard contract for composite widgets, two products.

    `frontend/lib/shell/rovingFocus.ts` is pure TS, so the static export carries
    a byte-identical mirror (refreshed by `make ui-sync`, drift-gated by
    ux_audit R12) instead of hand-rolling the arrow-key pattern a second time.
    The behavioural half lives in lsat-static/__tests__/QuestionCard.test.tsx.
    """

    SOURCE = REPO / "frontend" / "lib" / "shell" / "rovingFocus.ts"
    MIRROR = APP / "lib" / "rovingFocus.ts"

    def test_mirror_is_byte_identical(self) -> None:
        assert self.MIRROR.is_file(), "lsat-static/lib/rovingFocus.ts is missing"
        assert self.SOURCE.read_bytes() == self.MIRROR.read_bytes(), (
            "lsat-static/lib/rovingFocus.ts drifted — run `make ui-sync`"
        )

    def test_question_card_consumes_the_shared_helper(self) -> None:
        card = (APP / "components" / "QuestionCard.tsx").read_text(encoding="utf-8")
        assert "from '@/lib/rovingFocus'" in card, (
            "QuestionCard must import nextRovingIndex, not hand-roll arrows"
        )
        assert "nextRovingIndex(" in card
        # The old modulo-wrap helper is the thing the port retires.
        assert "function move(" not in card

    def test_ui_sync_refreshes_the_mirror(self) -> None:
        makefile = (REPO / "Makefile").read_text(encoding="utf-8")
        assert "lsat-static/lib/rovingFocus.ts" in makefile.split("ui-sync:", 1)[1], (
            "`make ui-sync` must copy rovingFocus.ts alongside base.css"
        )


# ---------------------------------------------------------------------------
# Drift gate: committed artifact ↔ source bank
# ---------------------------------------------------------------------------


class TestContentDrift:
    @pytest.fixture()
    def artifact(self) -> dict:
        return _load(CONTENT)

    def test_no_duplicate_ids_in_bank_sources(self) -> None:
        # Both the exporter's loader and this gate key by id; a duplicate id
        # would be silently shadowed on both sides, so ban it at the source.
        assert _bank_question_count() == len(_bank_questions()), (
            "duplicate question id across bank files"
        )

    def test_question_ids_match_bank(self, artifact: dict) -> None:
        bank = _bank_questions()
        site_ids = {q["id"] for q in artifact["questions"]}
        assert site_ids == set(bank), (
            "site content.json is out of sync with the bank — run `make lsat-export` "
            f"(missing: {sorted(set(bank) - site_ids)}, stale: {sorted(site_ids - set(bank))})"
        )

    def test_every_consumed_question_field_matches_bank(self, artifact: dict) -> None:
        # The app renders/filters on ALL of these — any drift means the
        # published site disagrees with the approved bank (spec 025 FR-8).
        bank = _bank_questions()
        for q in artifact["questions"]:
            src = bank[q["id"]]
            for field in ("section", "difficulty", "stem", "correct", "explanation"):
                assert q[field] == src[field], (
                    f"{q['id']}: {field} drift — run `make lsat-export`"
                )
            assert q["choices"] == src["choices"], (
                f"{q['id']}: choices drift — run `make lsat-export`"
            )
            assert (q.get("concepts") or []) == (src.get("concepts") or []), (
                f"{q['id']}: concepts drift — run `make lsat-export`"
            )
            assert _norm_refs(q.get("references")) == _norm_refs(src.get("references")), (
                f"{q['id']}: references drift — run `make lsat-export`"
            )
            assert q.get("passage_id") == src.get("passage_id"), (
                f"{q['id']}: passage_id drift — run `make lsat-export`"
            )

    def test_counts_match(self, artifact: dict) -> None:
        bank = _bank_questions()
        assert artifact["counts"]["total"] == len(bank)
        for section in ("LR", "RC", "LG"):
            expected = sum(1 for q in bank.values() if q["section"] == section)
            assert artifact["counts"][section] == expected

    def test_passages_fully_synced(self, artifact: dict) -> None:
        src = {p["id"]: p for p in _load(BANK_DIR / "passages.json")["items"]}
        site = {p["id"]: p for p in artifact["passages"]}
        assert set(site) == set(src)
        # The app renders every one of these fields (viewPassage).
        for pid, sp in site.items():
            # passage_b / title_a / title_b carry comparative RC sets (spec 047
            # FR-9); a set whose second half failed to export would render as a
            # single passage and make every comparative question unanswerable.
            for field in (
                "section",
                "title",
                "summary",
                "passage",
                "passage_b",
                "title_a",
                "title_b",
                "setup",
            ):
                assert sp.get(field) == src[pid].get(field), (
                    f"passage {pid}: {field} drift — run `make lsat-export`"
                )
            assert (sp.get("rules") or []) == (src[pid].get("rules") or []), (
                f"passage {pid}: rules drift — run `make lsat-export`"
            )

    def test_concepts_fully_synced(self, artifact: dict) -> None:
        src = {c["id"]: c for c in _load(BANK_DIR / "concepts.json")["items"]}
        site = {c["id"]: c for c in artifact["concepts"]}
        assert set(site) == set(src)
        # The app renders/searches name, summary, detail, examples, see_also.
        for cid, sc in site.items():
            for field in ("name", "summary", "detail"):
                assert sc.get(field) == src[cid].get(field), (
                    f"concept {cid}: {field} drift — run `make lsat-export`"
                )
            for field in ("examples", "see_also", "sections"):
                assert (sc.get(field) or []) == (src[cid].get(field) or []), (
                    f"concept {cid}: {field} drift — run `make lsat-export`"
                )

    def test_writing_prompts_fully_synced(self, artifact: dict) -> None:
        # Spec 047 AC-5: a writing data-file edit that skips `make lsat-export`
        # must fail CI, exactly as a bank edit does.
        path = BANK_DIR / "writing_prompts.json"
        src = {p["id"]: p for p in _load(path)["items"]} if path.is_file() else {}
        site = {p["id"]: p for p in artifact.get("writing_prompts", [])}
        assert set(site) == set(src), (
            "site content.json is out of sync with the writing prompts — run "
            f"`make lsat-export` (missing: {sorted(set(src) - set(site))}, "
            f"stale: {sorted(set(site) - set(src))})"
        )
        assert artifact["counts"]["writing_prompts"] == len(src)
        for pid, sp in site.items():
            for field in ("title", "rubric_id", "difficulty", "issue", "context"):
                assert sp.get(field) == src[pid].get(field), (
                    f"writing prompt {pid}: {field} drift — run `make lsat-export`"
                )
            for field in ("task", "positions", "perspectives", "self_check"):
                assert sp.get(field) == src[pid].get(field), (
                    f"writing prompt {pid}: {field} drift — run `make lsat-export`"
                )
            # The annotated model response is the offline feedback loop; it
            # must ship whole, not summarized.
            assert sp["model_response"] == src[pid]["model_response"], (
                f"writing prompt {pid}: model_response drift — run `make lsat-export`"
            )

    def test_writing_rubrics_fully_synced(self, artifact: dict) -> None:
        path = BANK_DIR / "writing_rubrics.json"
        src = {r["id"]: r for r in _load(path)["items"]} if path.is_file() else {}
        site = {r["id"]: r for r in artifact.get("writing_rubrics", [])}
        assert set(site) == set(src), (
            "site content.json is out of sync with the writing rubrics — run "
            "`make lsat-export`"
        )
        for rid, sr in site.items():
            assert sr["bands"] == src[rid]["bands"], f"rubric {rid}: bands drift"
            assert sr["criteria"] == src[rid]["criteria"], (
                f"rubric {rid}: criteria drift — run `make lsat-export`"
            )

    def test_sections_fully_synced(self, artifact: dict) -> None:
        src = {s["code"]: s for s in _load(BANK_DIR / "sections.json")["items"]}
        site = {s["code"]: s for s in artifact["sections"]}
        assert set(site) == set(src)
        # viewHome builds the landing cards from these fields.
        for code, ss in site.items():
            for field in ("name", "description", "format", "timing"):
                assert ss.get(field) == src[code].get(field), (
                    f"section {code}: {field} drift — run `make lsat-export`"
                )


# ---------------------------------------------------------------------------
# Integrity of the artifact itself
# ---------------------------------------------------------------------------


class TestContentIntegrity:
    @pytest.fixture()
    def artifact(self) -> dict:
        return _load(CONTENT)

    def test_every_key_is_a_choice_label(self, artifact: dict) -> None:
        for q in artifact["questions"]:
            labels = [c["label"] for c in q["choices"]]
            assert labels == ["A", "B", "C", "D", "E"], q["id"]
            assert q["correct"] in labels, q["id"]

    def test_every_passage_id_resolves(self, artifact: dict) -> None:
        passage_ids = {p["id"] for p in artifact["passages"]}
        for q in artifact["questions"]:
            if q.get("passage_id"):
                assert q["passage_id"] in passage_ids, q["id"]

    def test_no_writing_item_carries_an_answer_key(self, artifact: dict) -> None:
        # Spec 047 AC-2: WS has no keyed-choice form. The exporter loads
        # through the bank model that rejects it; this pins the contract at
        # the artifact boundary too.
        assert not [q for q in artifact["questions"] if q["section"] == "WS"]

    def test_every_writing_prompt_resolves_its_rubric(self, artifact: dict) -> None:
        rubric_ids = {r["id"] for r in artifact.get("writing_rubrics", [])}
        for prompt in artifact.get("writing_prompts", []):
            assert prompt["rubric_id"] in rubric_ids, prompt["id"]

    def test_writing_self_checks_name_real_criteria(self, artifact: dict) -> None:
        rubrics = {r["id"]: r for r in artifact.get("writing_rubrics", [])}
        for prompt in artifact.get("writing_prompts", []):
            known = {c["id"] for c in rubrics[prompt["rubric_id"]]["criteria"]}
            for item in prompt["self_check"]:
                assert item["criterion_id"] in known, prompt["id"]
            for note in prompt["model_response"]["annotations"]:
                assert note["criterion_id"] in known, prompt["id"]

    def test_comparative_sets_ship_both_halves(self, artifact: dict) -> None:
        # Spec 047 FR-9: a set with Passage B must name both halves, or a
        # reader cannot tell which text a question is asking about.
        comparative = [p for p in artifact["passages"] if p.get("passage_b")]
        assert comparative, "no comparative RC set in the published artifact"
        for p in comparative:
            assert p["section"] == "RC", p["id"]
            assert p.get("passage"), f"{p['id']} has Passage B but no Passage A"
            assert p.get("title_a") and p.get("title_b"), p["id"]
            linked = [
                q for q in artifact["questions"] if q.get("passage_id") == p["id"]
            ]
            assert linked, f"{p['id']} is a comparative set with no questions"

    def test_rc_lg_questions_have_context(self, artifact: dict) -> None:
        for q in artifact["questions"]:
            if q["section"] in ("RC", "LG"):
                assert q.get("passage_id"), (
                    f"{q['id']} has no passage_id — it would render context-free "
                    "in the static app"
                )


# ---------------------------------------------------------------------------
# Knowledge library (spec 048: FR-10, FR-11, FR-13, NFR-SAFETY-1, AC-5, AC-7)
# ---------------------------------------------------------------------------

LIBRARY_DIR = BANK_DIR / "library"
PLATFORM_RENDERER = (
    REPO / "frontend" / "components" / "lsat" / "library" / "BlockRenderer.tsx"
)
STATIC_RENDERER = APP / "components" / "library" / "BlockRenderer.tsx"

#: NFR-PERF-1. The whole bundle, library included, has to stay small enough
#: that the published site is usable on a phone connection.
BUNDLE_BUDGET_BYTES = 1_500_000


def _library_source_ids() -> set[str]:
    return {
        p.stem for p in LIBRARY_DIR.glob("*.md") if not p.name.startswith("_")
    }


class TestLibraryDrift:
    """The exported library must stay in lockstep with `data/library/`."""

    @pytest.fixture()
    def artifact(self) -> dict:
        return _load(CONTENT)

    def test_every_source_article_shipped(self, artifact: dict) -> None:
        shipped = {a["id"] for a in artifact.get("library", [])}
        missing = sorted(_library_source_ids() - shipped)
        assert missing == [], f"not exported — run `make lsat-export`: {missing}"

    def test_no_article_shipped_that_is_not_in_source(self, artifact: dict) -> None:
        shipped = {a["id"] for a in artifact.get("library", [])}
        extra = sorted(shipped - _library_source_ids())
        assert extra == [], f"stale artifact — run `make lsat-export`: {extra}"

    def test_counts_agree_with_the_payload(self, artifact: dict) -> None:
        counts = artifact["counts"]
        assert counts["library_articles"] == len(artifact["library"])
        assert counts["library_tracks"] == len(artifact["library_tracks"])

    def test_titles_have_not_drifted(self, artifact: dict) -> None:
        """A retitled article without a re-export ships the old name."""
        for shipped in artifact.get("library", []):
            source = (LIBRARY_DIR / f"{shipped['id']}.md").read_text(encoding="utf-8")
            for line in source.splitlines():
                if line.startswith("title:"):
                    assert shipped["title"] == line.split(":", 1)[1].strip(), (
                        f"{shipped['id']}: title drift — run `make lsat-export`"
                    )
                    break

    def test_track_members_all_shipped(self, artifact: dict) -> None:
        shipped = {a["id"] for a in artifact.get("library", [])}
        for track in artifact.get("library_tracks", []):
            missing = [a for a in track["article_ids"] if a not in shipped]
            assert missing == [], f"track {track['id']} references {missing}"

    def test_bundle_stays_within_budget(self) -> None:
        size = CONTENT.stat().st_size
        assert size <= BUNDLE_BUDGET_BYTES, (
            f"content.json is {size:,} bytes, over the "
            f"{BUNDLE_BUDGET_BYTES:,} budget — shard the library (spec 048 R1)"
        )


class TestLibraryArtifactIntegrity:
    @pytest.fixture()
    def artifact(self) -> dict:
        return _load(CONTENT)

    def test_articles_ship_as_typed_blocks(self, artifact: dict) -> None:
        for article in artifact.get("library", []):
            assert article["blocks"], article["id"]
            assert "markdown" not in article, (
                f"{article['id']} shipped raw Markdown — clients render blocks"
            )

    def test_every_cross_reference_resolves_inside_the_bundle(
        self, artifact: dict
    ) -> None:
        """The offline site cannot fetch a missing target, so nothing may dangle."""
        article_ids = {a["id"] for a in artifact.get("library", [])}
        concept_ids = {c["id"] for c in artifact["concepts"]}
        question_ids = {q["id"] for q in artifact["questions"]}

        def _spans(block: dict) -> list:
            if block["block_type"] == "paragraph":
                return block["spans"]
            if block["block_type"] == "list":
                return [s for item in block["items"] for s in item]
            if block["block_type"] == "table":
                cells = list(block["headers"]) + [c for r in block["rows"] for c in r]
                return [s for cell in cells for s in cell]
            if block["block_type"] == "callout":
                return [s for child in block["blocks"] for s in _spans(child)]
            return []

        targets = {"article": article_ids, "concept": concept_ids,
                   "question": question_ids}
        for article in artifact.get("library", []):
            for block in article["blocks"]:
                for span in _spans(block):
                    known = targets.get(span["kind"])
                    if known is None:
                        continue
                    assert span["ref_id"] in known, (
                        f"{article['id']}: dangling {span['kind']} reference "
                        f"{span['ref_id']!r} in the offline bundle"
                    )

    def test_every_article_carries_an_outline_and_takeaways(
        self, artifact: dict
    ) -> None:
        for article in artifact.get("library", []):
            anchors = {e["anchor"] for e in article["outline"]}
            assert "key-takeaways" in anchors, article["id"]


class TestRendererParity:
    """FR-11: a block type must ship to both products or to neither.

    `lsat-static/` still has no component-test harness (BL-20260831-18), so
    this is a source assertion — crude, but it is what stops a block type from
    rendering in the platform app and silently vanishing offline.
    """

    def _declared_types(self, path: Path) -> set[str]:
        text = path.read_text(encoding="utf-8")
        marker = "export const SUPPORTED_BLOCK_TYPES = ["
        assert marker in text, f"{path.name} must declare SUPPORTED_BLOCK_TYPES"
        body = text.split(marker, 1)[1].split("]", 1)[0]
        return set(re.findall(r"'([a-z_]+)'", body))

    def test_both_renderers_exist(self) -> None:
        assert PLATFORM_RENDERER.is_file()
        assert STATIC_RENDERER.is_file()

    def test_the_two_renderers_cover_the_same_block_types(self) -> None:
        platform = self._declared_types(PLATFORM_RENDERER)
        static = self._declared_types(STATIC_RENDERER)
        assert platform == static, (
            "block-type drift between the platform and static renderers: "
            f"platform-only={sorted(platform - static)}, "
            f"static-only={sorted(static - platform)}"
        )

    def test_declared_types_match_the_exported_artifact(self) -> None:
        artifact = _load(CONTENT)
        used = {
            b["block_type"]
            for a in artifact.get("library", [])
            for b in a["blocks"]
        }
        assert used <= self._declared_types(PLATFORM_RENDERER)

    def test_no_library_surface_anywhere_injects_html(self) -> None:
        """AC-7 / NFR-SAFETY-1: article content is never injected as markup.

        Matches the JSX *attribute* (`dangerouslySetInnerHTML=`) rather than
        the bare identifier, so a comment explaining why the escape hatch is
        not used does not read as a use of it.
        """
        surfaces = [
            REPO / "frontend" / "components" / "LsatLibrary.tsx",
            APP / "components" / "Library.tsx",
            PLATFORM_RENDERER,
            STATIC_RENDERER,
        ]
        for path in surfaces:
            assert "dangerouslySetInnerHTML=" not in path.read_text(encoding="utf-8"), (
                f"{path.name} injects HTML — article content must render as "
                "typed blocks only"
            )


class TestLibraryNavigation:
    """The offline site must actually expose the library."""

    def test_library_is_a_destination(self) -> None:
        page = (APP / "app" / "page.tsx").read_text(encoding="utf-8")
        assert "id: 'library'" in page, "no Library entry in the static site NAV"
        assert "<Library" in page, "the Library view is never rendered"

    def test_search_runs_offline(self) -> None:
        """NFR-OFFLINE-1: the offline search index must not call the network."""
        text = (APP / "lib" / "search.ts").read_text(encoding="utf-8")
        assert "fetch(" not in text
        assert "XMLHttpRequest" not in text

    def test_library_shortcuts_are_documented(self) -> None:
        help_text = (APP / "components" / "ShortcutHelp.tsx").read_text(
            encoding="utf-8"
        )
        assert "Knowledge library" in help_text, (
            "the library's bindings are undiscoverable in the ? sheet"
        )
