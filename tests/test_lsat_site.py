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
