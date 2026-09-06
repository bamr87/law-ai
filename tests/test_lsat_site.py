"""Static LSAT practice site — structure + drift gate (spec 025 FR-8/AC-4).

Stdlib-only, like the rest of the root suite. The committed site artifact
(`lsat-static/content.json`, imported at build time by the Next.js static
export) must stay in lockstep with the source bank under
`backend/law_ai/lsat/services/data/`, so the published GitHub Pages app can
never silently lag the approved content.

Who fixes the drift changed with BL-20260702-11. It used to be a person: the
gate failed and the message said "run `make lsat-export`". Now
`.github/workflows/refresh-lsat-content.yml` does the export — on pushes to
main, and on same-repo pull requests, where it pushes the refreshed artifact
onto the PR branch. Where that job is guaranteed to fix the same thing in the
same run, ci.yml sets `LSAT_CONTENT_AUTOEXPORT=1` and the drift classes defer
to it rather than red-building a PR over work a robot is already doing.

Deferral is narrow on purpose. `LSAT_CONTENT_AUTOEXPORT` is set only for a
same-repo pull request whose diff touches the bank. A fork PR (where the
refresh job has no write token and skips), a push to main, and every local run
enforce the gate exactly as before — which is why the assertions below still
name `make lsat-export` as the fix.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

#: Set by ci.yml's repo-structural job when — and only when —
#: refresh-lsat-content.yml is re-exporting content.json onto this same branch
#: (BL-20260702-11). See the module docstring.
AUTOEXPORTED = os.getenv("LSAT_CONTENT_AUTOEXPORT") == "1"

_DEFERRED = (
    "refresh-lsat-content.yml re-exports content.json onto this branch in "
    "this same run (BL-20260702-11); failing here too would put the manual "
    "`make lsat-export` back in the developer's hands"
)

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

    def test_the_site_says_what_it_lacks(self) -> None:
        """BL-20260831-25: the gap from the full lab is stated on the site.

        It used to live only in this repo's README and in a code comment —
        neither of which a learner on the published site can read — so the
        three server-backed features were discovered by going looking for them
        and failing.
        """
        overview = (APP / "components" / "Overview.tsx").read_text(encoding="utf-8")
        assert "What this site does not have" in overview
        for missing in ("AI tutor", "blind answer cross-check", "server-side stats"):
            assert missing in overview, f"the note must name the missing {missing}"
        # And again where the absence is actually felt.
        solve = (APP / "components" / "solve" / "SolveAssist.tsx").read_text(
            encoding="utf-8"
        )
        assert "no AI tutor" in solve, (
            "the no-guide empty state must explain the missing tutor fallback"
        )

    def test_progress_can_leave_the_device(self) -> None:
        """BL-20260702-10: localStorage is device-bound and silently lost.

        Private browsing discards it, a new phone never had it, and this site
        has no account to sync to — so the export file is the only way a
        month of drilling survives. Behaviour is covered by
        lsat-static/__tests__/backup.test.ts and Stats.test.tsx.
        """
        backup = (APP / "lib" / "backup.ts").read_text(encoding="utf-8")
        for fn in ("exportSnapshot", "importSnapshot", "parseSnapshot"):
            assert f"export function {fn}" in backup, f"backup.ts must export {fn}"
        assert "SNAPSHOT_SCHEMA" in backup, (
            "the file format must be versioned so an old export can be migrated"
        )
        # Everything per-device, not only the attempts.
        for key in ("attempts", "library_read", "writing"):
            assert f"{key}:" in backup, f"the snapshot must carry {key}"
        stats = (APP / "components" / "Stats.tsx").read_text(encoding="utf-8")
        assert "Export progress (JSON)" in stats
        assert "Import and merge" in stats and "Import and replace" in stats

    def test_vanilla_site_retired(self) -> None:
        # The buildless vanilla app was replaced by the Next.js export; make
        # sure it doesn't creep back and fight over the single GitHub Pages site.
        assert not (REPO / "frontend" / "public" / "lsat-practice").exists(), (
            "the retired vanilla lsat-practice/ app should be gone"
        )


# ---------------------------------------------------------------------------
# Keyboard contract
# ---------------------------------------------------------------------------


class TestLintGate:
    """BL-20260905-15: the static site is held to the platform's React rules.

    `lsat-static/` had no eslint config, so `npx eslint` refused to start and
    `npm run lint` was an unconfigured `next lint` — the CI job for this
    package gated on `tsc --noEmit` and vitest alone, while the platform app
    next to it was linted on every PR. The two share components by hand; a
    rule that holds for one and not the other is how a hand mirror rots.
    """

    def test_flat_config_mirrors_the_platform_app(self) -> None:
        config = APP / "eslint.config.mjs"
        assert config.is_file(), "lsat-static needs an eslint flat config"
        body = config.read_text(encoding="utf-8")
        assert "eslint-config-next" in body, (
            "the static site must lint against the same Next preset as frontend/"
        )

    def test_lint_script_and_devdeps_are_wired(self) -> None:
        pkg = json.loads((APP / "package.json").read_text(encoding="utf-8"))
        assert pkg["scripts"]["lint"] == "eslint .", (
            "`npm run lint` must run eslint, not the unconfigured `next lint`"
        )
        for dep in ("eslint", "eslint-config-next"):
            assert dep in pkg["devDependencies"], f"lsat-static must depend on {dep}"

    def test_ci_runs_the_linter(self) -> None:
        import yaml

        ci = yaml.safe_load(
            (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        )
        runs = [str(s.get("run", "")) for s in ci["jobs"]["lsat-static"]["steps"]]
        assert any("npm run lint" in r for r in runs), (
            "the lsat-static CI job must run the linter alongside tsc + vitest"
        )


class TestKeyboardContract:
    """The published drill has to be runnable end to end without a mouse.

    This used to be four `.read_text()` source assertions, because
    `lsat-static/` had no component-test harness: they checked that the code
    *said* the right thing, not that focus *went* the right place. The harness
    landed with BL-20260831-18, so the four focus rules moved to
    `lsat-static/__tests__/focus-contract.test.tsx`, which presses the keys
    (BL-20260901-11), and the key bindings themselves — including the two
    defects a browser pass caught — to `__tests__/keyboard.test.tsx` and the
    per-view suites (BL-20260901-07).

    What is left here is what the root suite is actually for: the help sheet
    (documentation drift, not behaviour) and a pin that the behavioural suites
    still exist, so deleting one cannot quietly un-cover the contract.
    """

    def _read(self, name: str) -> str:
        return (APP / name).read_text(encoding="utf-8")

    def test_focus_and_binding_behaviour_is_covered_by_component_tests(self) -> None:
        # One pointer per rule, so a deleted suite fails here rather than
        # silently taking its coverage with it.
        suites = {
            "__tests__/focus-contract.test.tsx": (
                "aria-disabled",  # graded choices stay in the focus order
                "restores the choice you gave and the time you took",
                "reads the position into the live region",
                "puts the caret in the textarea",
            ),
            "__tests__/keyboard.test.tsx": (
                "skips an event another handler already claimed",
                "lets an explicitly allowed key out of a text field",
            ),
            "__tests__/pageShortcuts.test.tsx": (
                "steps forward and back through the nav",
                "closes with Escape",
                "leaves Escape alone while it is closed",
            ),
            "__tests__/Drill.test.tsx": ("advances with Enter again",),
            "__tests__/Writing.test.tsx": ("Escape blurs the editor first",),
            "__tests__/SolveAssist.test.tsx": ("walks forward one step per press",),
        }
        for name, needles in suites.items():
            path = APP / name
            assert path.is_file(), f"{name} is the behavioural cover for these rules"
            body = path.read_text(encoding="utf-8")
            for needle in needles:
                assert needle in body, f"{name} must still cover: {needle}"

    def test_the_header_can_be_pinned(self) -> None:
        """BL-20260901-05: hide-on-scroll is a default, not a decision.

        The header condenses and hides on scroll direction, which answers
        "should the chrome get out of the way?" implicitly. This is the
        explicit control, remembered per device next to the attempts and
        drafts. Behaviour lives in lsat-static/__tests__/headerPin.test.tsx.
        """
        page = self._read("app/page.tsx")
        # The key and its accessors live with everything else this site stores
        # (BL-20260905-16), which is also where it is written down that a
        # preference is not progress and stays out of the export snapshot.
        device_state = self._read("lib/deviceState.ts")
        assert "lsat-practice.header-pinned.v1" in device_state, (
            "the pin preference must be remembered on this device"
        )
        assert "readHeaderPinned" in page and "writeHeaderPinned" in page, (
            "the page reads and writes the pin through the shared accessors"
        )
        assert 'className="header-pin"' in page and "aria-pressed={pinned}" in page, (
            "the pin needs a real toggle control, not just a shortcut"
        )
        css = (APP / "app" / "globals.css").read_text(encoding="utf-8")
        assert ".site-header-pinned" in css
        # The control is display:none by default and shown again only under the
        # narrow-viewport media query. A media query adds no specificity, so
        # with equal selectors source order decides: the rule that shows it has
        # to come AFTER the one that hides it, or the toggle is invisible at
        # every width (which is exactly how it first shipped). jsdom loads no
        # stylesheet, so the component test cannot catch this — assert order.
        hide = css.index(".header-pin {\n  display: none;")
        show = css.index("  .header-pin {\n    display: inline-flex;")
        assert hide < show, (
            "the media query that reveals .header-pin must come after the "
            "display:none default, or the control never renders"
        )
        help_sheet = self._read("components/ShortcutHelp.tsx")
        assert "['.'," in help_sheet, "? sheet must document the pin shortcut"

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


class TestSharedSolveAssistContract:
    """BL-20260831-22: one hint carousel, two products, one set of assertions.

    ux_audit R13 checks only that both `SolveAssist.tsx` files exist, and
    `TestRendererParity` below compares source structurally — neither says the
    two behave alike. The behavioural contract is a mirrored test module both
    vitest projects run against their own harness; this pins that neither side
    can quietly stop running it.
    """

    SOURCE = REPO / "frontend" / "__tests__" / "contracts" / "solveAssist.contract.ts"
    MIRROR = APP / "__tests__" / "contracts" / "solveAssist.contract.ts"
    SUITES = (
        REPO / "frontend" / "__tests__" / "components" / "lsat" / "SolveAssist.test.tsx",
        APP / "__tests__" / "SolveAssist.test.tsx",
    )

    def test_mirror_is_byte_identical(self) -> None:
        assert self.MIRROR.is_file(), "the static site's contract mirror is missing"
        assert self.SOURCE.read_bytes() == self.MIRROR.read_bytes(), (
            "solveAssist.contract.ts drifted — run `make ui-sync`"
        )

    def test_both_suites_run_the_contract(self) -> None:
        for suite in self.SUITES:
            body = suite.read_text(encoding="utf-8")
            assert "describeSolveAssistContract(" in body, (
                f"{suite.name} must run the shared carousel contract"
            )
            assert "solveAssist.contract" in body

    def test_ui_sync_refreshes_the_contract(self) -> None:
        makefile = (REPO / "Makefile").read_text(encoding="utf-8")
        assert "solveAssist.contract.ts" in makefile.split("ui-sync:", 1)[1], (
            "`make ui-sync` must copy the contract alongside the other mirrors"
        )


class TestStickyStack:
    """BL-20260831-19: a long passage has to stay beside its questions.

    Top-stickiness alone does nothing for an element taller than the viewport —
    a browser pins such a thing only once its bottom scrolls into view — so the
    longest RC passages were exactly the ones that scrolled away. The fix is
    the `.lib-rail` pattern: a height cap keyed off the same tokens as the
    sticky offset, plus its own scroll region.
    """

    def test_the_offsets_measure_themselves(self) -> None:
        """BL-20260831-20: the tokens follow the elements, not a memory of them."""
        css = (APP / "app" / "globals.css").read_text(encoding="utf-8")
        # The rem constants stay — a static export has no JS before hydration —
        # but they are documented as the fallback, not the source of truth.
        assert "--site-header-h: 3.75rem" in css
        assert "First-paint fallback, not the source of truth" in css
        page = (APP / "app" / "page.tsx").read_text(encoding="utf-8")
        drill = (APP / "components" / "Drill.tsx").read_text(encoding="utf-8")
        assert "useMeasuredCssVar(headerRef, '--site-header-h'" in page
        assert "useMeasuredCssVar(headRef, '--drill-head-h'" in drill
        hook = (APP / "lib" / "useMeasuredCssVar.ts").read_text(encoding="utf-8")
        assert "ResizeObserver" in hook and "setProperty" in hook

    def test_passage_column_is_its_own_scroll_region(self) -> None:
        css = (APP / "app" / "globals.css").read_text(encoding="utf-8")
        block = css.split(".drill-grid > .passage {", 1)
        assert len(block) == 2, "the passage column has no wide-viewport rule"
        rule = block[1].split("}", 1)[0]
        assert "overflow-y: auto" in rule, (
            "a passage taller than the viewport needs its own scroll region"
        )
        assert "overscroll-behavior: contain" in rule, (
            "a wheel that reaches the end of the passage must not scroll the "
            "page behind it"
        )
        # Same tokens as the sticky offset, so the two cannot disagree.
        for token in ("--site-header-h", "--drill-head-h"):
            assert token in rule, f"the height cap must be keyed off {token}"


# ---------------------------------------------------------------------------
# Drift gate: committed artifact ↔ source bank
# ---------------------------------------------------------------------------


@pytest.mark.skipif(AUTOEXPORTED, reason=_DEFERRED)
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

#: The point at which "it keeps growing" stops being a judgement call
#: (BL-20260831-24). Sharding costs the site its one genuinely unusual
#: property — zero network calls for content — so it is not done early; but
#: "we will split it if it keeps growing" is a promise nobody is holding
#: unless something measures the growth. Two thirds of the budget is the
#: point at which the next export could plausibly breach it, which is early
#: enough to act deliberately rather than in a hurry.
BUNDLE_WARN_BYTES = BUNDLE_BUDGET_BYTES * 2 // 3


def _library_source_ids() -> set[str]:
    return {
        p.stem for p in LIBRARY_DIR.glob("*.md") if not p.name.startswith("_")
    }


@pytest.mark.skipif(AUTOEXPORTED, reason=_DEFERRED)
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

    def test_the_shard_trigger_names_what_actually_grew(self, artifact: dict) -> None:
        """BL-20260831-24: measure the growth before deciding what to split.

        The item was filed when guides doubled the bundle, and proposed
        splitting guides. They are no longer what is large: the library is.
        Splitting the wrong key would cost the offline-first property and
        recover almost nothing, so the trigger reports the actual breakdown
        and names the biggest key, rather than repeating an assumption that
        has already gone stale once.
        """
        size = CONTENT.stat().st_size
        if size <= BUNDLE_WARN_BYTES:
            return
        by_key = sorted(
            (
                (len(json.dumps(value, separators=(",", ":"))), key)
                for key, value in artifact.items()
            ),
            reverse=True,
        )
        breakdown = ", ".join(
            f"{key} {n:,}B ({n * 100 // size}%)" for n, key in by_key[:4]
        )
        pytest.fail(
            f"content.json is {size:,} bytes, past {BUNDLE_WARN_BYTES:,} "
            f"({size * 100 // BUNDLE_BUDGET_BYTES}% of the "
            f"{BUNDLE_BUDGET_BYTES:,} budget). Shard the largest key first — "
            f"emit it per id under lsat-static/public/content/ and fetch on "
            f"demand, leaving the index in content.json. Breakdown: "
            f"{breakdown}."
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

    def test_a_single_concept_can_be_linked_to(self) -> None:
        """BL-20260905-04: capability parity with the platform catalog.

        The static catalog is a flat card list where the platform's is a rail
        plus a reader — a deliberate layout divergence, recorded in
        lsat-static/README.md. What could not stay divergent is the ability to
        link to one concept: the cards carried `catalog-<id>` anchors, but
        nothing read the fragment, so such a URL opened cold landed on the
        article reader instead.
        """
        library = (APP / "components" / "Library.tsx").read_text(encoding="utf-8")
        assert "hashTarget" in library, "Library must read the URL fragment"
        for prefix in ("article-", "catalog-"):
            assert f"'{prefix}'" in library, (
                f"#{prefix}<id> must route, matching the platform's hashTarget()"
            )
        assert "hashchange" in library, (
            "a permalink followed from inside the catalog changes only the "
            "fragment — nothing remounts"
        )
        concepts = (APP / "components" / "Concepts.tsx").read_text(encoding="utf-8")
        assert "concept-permalink" in concepts, (
            "every concept card needs a copyable link to itself"
        )
        readme = (APP / "README.md").read_text(encoding="utf-8")
        assert "Capability is the contract; layout is not" in readme, (
            "the layout divergence has to be recorded as deliberate"
        )

    def test_library_shortcuts_are_documented(self) -> None:
        help_text = (APP / "components" / "ShortcutHelp.tsx").read_text(
            encoding="utf-8"
        )
        assert "Knowledge library" in help_text, (
            "the library's bindings are undiscoverable in the ? sheet"
        )


class TestContentRefreshAutomation:
    """BL-20260702-11: the export should not depend on someone remembering.

    The drift gate above turns a forgotten `make lsat-export` into a red build
    on an unrelated PR. `.github/workflows/refresh-lsat-content.yml` closes the
    loop by re-exporting whenever the source data lands on main; these tests
    pin the three properties that make that safe.
    """

    WORKFLOW = REPO / ".github" / "workflows" / "refresh-lsat-content.yml"

    def _workflow(self) -> dict:
        import yaml

        return yaml.safe_load(self.WORKFLOW.read_text(encoding="utf-8"))

    def test_workflow_watches_the_source_bank(self) -> None:
        data = self._workflow()
        # `on` is parsed as the boolean True by YAML 1.1 — hence the lookup.
        triggers = data.get("on") or data.get(True)
        paths = triggers["push"]["paths"]
        assert any("lsat/services/data" in p for p in paths), (
            "the refresh must trigger on the source bank, not on lsat-static/ "
            f"(which is the output); got {paths}"
        )

    def test_workflow_ignores_a_generated_at_only_diff(self) -> None:
        """Every export stamps a new timestamp; committing that would churn."""
        body = self.WORKFLOW.read_text(encoding="utf-8")
        assert 'pop("generated_at"' in body, (
            "content.json is byte-stable except generated_at — comparing raw "
            "bytes would commit on every single run"
        )
        job = self._workflow()["jobs"]["refresh"]
        commit = [s for s in job["steps"] if "Commit" in (s.get("name") or "")]
        assert commit and "changed == 'true'" in commit[0]["if"], (
            "the commit step must be gated on a real content change"
        )

    def test_workflow_kicks_the_pages_build(self) -> None:
        """A GITHUB_TOKEN push raises no `push` event for other workflows."""
        job = self._workflow()["jobs"]["refresh"]
        steps = " ".join(str(s.get("run", "")) for s in job["steps"])
        assert "gh workflow run deploy-lsat-pages.yml" in steps, (
            "without an explicit dispatch the commit lands and the published "
            "site stays stale — the exact failure this item is about"
        )
        assert self._workflow()["permissions"].get("actions") == "write", (
            "dispatching another workflow needs actions: write"
        )

    def test_the_pull_request_leg_removes_the_manual_export(self) -> None:
        """BL-20260702-11's second clause: the manual step must actually go.

        While the refresh only ran on pushes to main, the drift gate above
        still red-built any PR that edited the bank without `make lsat-export`,
        so a developer had to run it anyway — and by the time the change
        reached main the payload comparison was a guaranteed no-op. The PR leg
        is what makes the automation load-bearing rather than decorative.
        """
        triggers = self._workflow().get("on") or self._workflow().get(True)
        assert "pull_request" in triggers, (
            "a push-to-main-only refresh cannot remove a step the PR gate "
            "enforces"
        )
        paths = triggers["pull_request"]["paths"]
        assert any("lsat/services/data" in p for p in paths)

        job = self._workflow()["jobs"]["refresh"]
        # A fork PR's token is read-only, so the job must stand aside rather
        # than fail — and the gate is not deferred for forks either.
        assert "head.repo.full_name == github.repository" in job["if"]

        checkout = next(
            step for step in job["steps"] if "checkout" in str(step.get("uses", ""))
        )
        assert "head.ref" in str(checkout["with"]["ref"]), (
            "a pull_request checkout is the detached merge ref; the PR's own "
            "branch has to be checked out for the push to have anywhere to go"
        )

        pages = [
            step
            for step in job["steps"]
            if "deploy-lsat-pages" in str(step.get("run", ""))
        ]
        assert pages and "github.event_name != 'pull_request'" in pages[0]["if"], (
            "a PR branch's refresh must never publish the site"
        )

    def test_the_drift_gate_defers_only_where_the_job_will_fix_it(self) -> None:
        """The deferral and the refresh job must fire on the same conditions.

        If the gate deferred more widely than the job runs, drift would land
        unnoticed; if it deferred less, the manual step would still be
        enforced. Both halves are pinned here so they cannot drift apart.
        """
        import yaml

        ci = yaml.safe_load(
            (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        )
        changes = ci["jobs"]["changes"]
        assert "lsat-content" in changes["outputs"], (
            "the deferral needs a paths filter for the bank"
        )

        structural = ci["jobs"]["repo-structural"]
        assert "changes" in structural["needs"]
        step = next(
            s for s in structural["steps"] if "pytest tests/" in str(s.get("run", ""))
        )
        guard = str(step["env"]["LSAT_CONTENT_AUTOEXPORT"])
        for condition in (
            "pull_request",
            "lsat-content",
            "head.repo.full_name",
        ):
            assert condition in guard, (
                f"the deferral guard must be scoped by {condition} — it is "
                "narrower than 'always skip the drift gate'"
            )

        # And the module honours it.
        assert AUTOEXPORTED is (os.getenv("LSAT_CONTENT_AUTOEXPORT") == "1")
