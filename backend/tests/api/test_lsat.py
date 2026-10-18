"""Tests for /api/lsat/* (spec 005)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from django.conf import settings
from law_ai.lsat.services.bank import (
    load_bank,
    load_concepts,
    load_passages,
    load_sections,
)
from law_ai.lsat.services.library import load_library
from law_ai.asgi import application as app


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    # Spec 041 FR-13: tutor responses are cached; isolate per test.
    monkeypatch.setattr(
        settings,
        "LSAT_RESPONSE_CACHE_DIR",
        str(tmp_path / "response_cache"),
        raising=False,
    )


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def test_bank_loads_and_every_item_well_formed() -> None:
    # AC-5
    bank = load_bank()
    assert len(bank) >= 5
    for q in bank.values():
        labels = [c.label for c in q.choices]
        assert labels == ["A", "B", "C", "D", "E"]
        assert q.correct in {"A", "B", "C", "D", "E"}
        assert q.explanation


@pytest.mark.asyncio
async def test_questions_returns_n_without_answers(client: AsyncClient) -> None:
    # AC-1
    res = await client.get("/api/lsat/questions", params={"limit": 3})
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 3
    for q in body["questions"]:
        assert "correct" not in q
        assert "explanation" not in q
        assert len(q["choices"]) == 5


@pytest.mark.asyncio
async def test_grade_correct_returns_true_with_explanation(client: AsyncClient) -> None:
    # AC-2
    bank = load_bank()
    qid, q = next(iter(bank.items()))
    res = await client.post(
        "/api/lsat/grade", json={"question_id": qid, "choice": q.correct}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["correct"] is True
    assert body["correct_choice"] == q.correct
    assert body["explanation"]


@pytest.mark.asyncio
async def test_grade_unknown_question_returns_404(client: AsyncClient) -> None:
    # AC-3
    res = await client.post(
        "/api/lsat/grade", json={"question_id": "nope", "choice": "A"}
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_grade_invalid_choice_returns_422(client: AsyncClient) -> None:
    # AC-3
    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post("/api/lsat/grade", json={"question_id": qid, "choice": "Z"})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_stats_aggregates_audit_events(client: AsyncClient) -> None:
    # AC-4
    bank = load_bank()
    items = list(bank.values())
    q1, q2 = items[0], items[1]
    wrong_choice = next(c for c in ["A", "B", "C", "D", "E"] if c != q2.correct)
    await client.post(
        "/api/lsat/grade", json={"question_id": q1.id, "choice": q1.correct}
    )
    await client.post(
        "/api/lsat/grade", json={"question_id": q2.id, "choice": wrong_choice}
    )
    res = await client.get("/api/lsat/stats")
    assert res.status_code == 200
    body = res.json()
    assert body["attempts"] == 2
    assert body["correct"] == 1
    assert body["accuracy"] == 0.5
    # Per-section breakdown surfaces under by_section (refactor 2026-05-03).
    assert "by_section" in body
    assert sum(b["attempts"] for b in body["by_section"].values()) == 2


# --- Refactor 2026-05-03: multi-section + tutor coverage ---


def test_bank_includes_all_sections() -> None:
    bank = load_bank()
    sections = {q.section for q in bank.values()}
    assert {"LR", "RC", "LG"}.issubset(sections)


def test_concepts_and_sections_load() -> None:
    sections = load_sections()
    concepts = load_concepts()
    passages = load_passages()
    assert {"LR", "RC", "LG"}.issubset(sections.keys())
    # Every concept referenced from sections.json exists in the catalog.
    for s in sections.values():
        for cid in s.concepts:
            assert cid in concepts, f"section {s.code} references unknown concept {cid}"
    # Every passage_id referenced from a question exists.
    for q in load_bank().values():
        if q.passage_id is not None:
            assert q.passage_id in passages


#: Floor for RC passages and LG games, each with a question set attached
#: (BL-20260503-02). A section that drops below this cannot give a learner a
#: full practice section without repeating a passage, so the count is a gate
#: rather than a target: raise it when the bank grows, never lower it.
MIN_PASSAGE_SETS = 10


def test_rc_and_lg_each_have_ten_usable_sets() -> None:
    passages = load_passages()
    bank = load_bank()
    for section in ("RC", "LG"):
        sets = {p.id for p in passages.values() if p.section == section}
        used = {q.passage_id for q in bank.values() if q.section == section}
        assert (
            len(sets) >= MIN_PASSAGE_SETS
        ), f"{section} has {len(sets)} passage sets, floor is {MIN_PASSAGE_SETS}"
        # A set nothing points at is not a usable set.
        orphans = sorted(sets - used)
        assert not orphans, f"{section} sets with no questions: {orphans}"


def test_every_passage_set_carries_source_attribution() -> None:
    """Original (CC0) provenance is stated on the set, not just the items."""
    for passage in load_passages().values():
        assert passage.source.strip(), f"{passage.id} has no source"
    for q in load_bank().values():
        assert q.source.strip(), f"{q.id} has no source"


@pytest.mark.asyncio
async def test_sections_endpoint_lists_all_three(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/sections")
    assert res.status_code == 200
    body = res.json()
    codes = {s["code"] for s in body["sections"]}
    assert {"LR", "RC", "LG"}.issubset(codes)
    for s in body["sections"]:
        assert "question_count" in s
        assert s["concepts"], f"section {s['code']} should ship at least one concept"


@pytest.mark.asyncio
async def test_section_detail_404_unknown(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/sections/XX")
    # XX is not a valid Section literal — Pydantic returns 422 at the path level.
    assert res.status_code in (404, 422)


@pytest.mark.asyncio
async def test_section_filter_on_questions(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/questions", params={"limit": 25, "section": "RC"})
    assert res.status_code == 200
    body = res.json()
    assert body["count"] >= 1
    for q in body["questions"]:
        assert q["section"] == "RC"


@pytest.mark.asyncio
async def test_concept_filter_on_questions(client: AsyncClient) -> None:
    """BL-20260905-01: the library's concept links have to reach practice.

    The catalog says "drill them in the lab", and without this filter the lab
    could only open on Overview and leave the learner to re-find the section
    and re-filter by hand.
    """
    bank = load_bank()
    concept = next(c for q in bank.values() for c in q.concepts)
    expected = {q.id for q in bank.values() if concept in q.concepts}

    res = await client.get(
        "/api/lsat/questions", params={"limit": 25, "concept": concept}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == len(expected)
    assert {q["id"] for q in body["questions"]} == expected
    for q in body["questions"]:
        assert concept in q["concepts"]


@pytest.mark.asyncio
async def test_concept_filter_composes_with_section(client: AsyncClient) -> None:
    bank = load_bank()
    concept, section = next(
        (c, q.section) for q in bank.values() for c in q.concepts if q.section == "LR"
    )
    res = await client.get(
        "/api/lsat/questions",
        params={"limit": 25, "concept": concept, "section": section},
    )
    assert res.status_code == 200
    for q in res.json()["questions"]:
        assert q["section"] == section
        assert concept in q["concepts"]


@pytest.mark.asyncio
async def test_unknown_concept_filter_is_an_empty_pool_not_a_random_item(
    client: AsyncClient,
) -> None:
    """The panel must be able to say "nothing here" rather than show a stray."""
    res = await client.get(
        "/api/lsat/questions", params={"limit": 1, "concept": "no-such-concept"}
    )
    assert res.status_code == 200
    assert res.json() == {"questions": [], "count": 0}


@pytest.mark.asyncio
async def test_passage_returns_questions_in_stable_order(client: AsyncClient) -> None:
    # Pull the first passage and confirm its questions come back sorted by id.
    list_res = await client.get("/api/lsat/passages", params={"section": "LG"})
    assert list_res.status_code == 200
    passage_id = list_res.json()["passages"][0]["id"]

    detail = await client.get(f"/api/lsat/passages/{passage_id}")
    assert detail.status_code == 200
    body = detail.json()
    qids = [q["id"] for q in body["questions"]]
    assert qids == sorted(qids)
    assert body["passage"]["id"] == passage_id


@pytest.mark.asyncio
async def test_question_id_lookup(client: AsyncClient) -> None:
    bank = load_bank()
    qid = next(iter(bank))
    res = await client.get(f"/api/lsat/questions/{qid}")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == qid
    assert "correct" not in body


@pytest.mark.asyncio
async def test_concepts_list_and_detail(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/concepts", params={"section": "LR"})
    assert res.status_code == 200
    items = res.json()["concepts"]
    assert items
    cid = items[0]["id"]

    detail = await client.get(f"/api/lsat/concepts/{cid}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["concept"]["id"] == cid
    assert isinstance(body["used_in_questions"], list)


@pytest.mark.asyncio
async def test_concept_detail_reports_the_true_use_count(client: AsyncClient) -> None:
    """BL-20260905-06: the id list is capped at ten, the count is not.

    A concept entry could only say "10+ questions" once a concept was popular,
    while an article's action beside it named the exact number from
    ``drill_question_count``. Both entry types now name the same fact the same
    way.
    """
    bank = load_bank()
    # The most-used concept in the bank, so the cap is exercised where it can be.
    counts: dict[str, int] = {}
    for q in bank.values():
        for c in q.concepts:
            counts[c] = counts.get(c, 0) + 1
    cid, expected = max(counts.items(), key=lambda kv: kv[1])

    res = await client.get(f"/api/lsat/concepts/{cid}")
    assert res.status_code == 200
    body = res.json()
    assert body["used_in_count"] == expected
    assert len(body["used_in_questions"]) == min(expected, 10)
    assert body["used_in_count"] >= len(body["used_in_questions"])
    assert set(body["used_in_questions"]) <= {
        q.id for q in bank.values() if cid in q.concepts
    }


@pytest.mark.asyncio
async def test_concepts_unknown_returns_404(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/concepts/does-not-exist")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_tutor_falls_back_when_no_provider_is_reachable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tutor never hard-fails when the whole provider chain is down."""
    from law_ai.core import llm as llm_mod
    from law_ai.lsat.services import tutor as tutor_mod

    async def boom(*args: object, **kwargs: object) -> object:
        raise llm_mod.LLMUnavailableError("every provider failed")

    monkeypatch.setattr(tutor_mod.llm, "agenerate", boom)

    bank = load_bank()
    qid, q = next(iter(bank.items()))
    res = await client.post(
        "/api/lsat/tutor",
        json={"question_id": qid, "user_choice": q.correct},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["used_llm"] is False
    assert body["coaching"]
    assert body["next_steps"]
    assert body["correct_choice"] == q.correct
    assert body["is_correct"] is True


@pytest.mark.asyncio
async def test_tutor_uses_llm_when_available(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A parseable payload from the chain surfaces in the response."""
    from law_ai.core.llm.base import LLMResult
    from law_ai.lsat.services import tutor as tutor_mod

    async def fake_generate(*args: object, **kwargs: object) -> LLMResult:
        return LLMResult(
            text=(
                '{"coaching": "Walkthrough: think contrapositive then re-check.", '
                '"next_steps": ["Diagram conditionals", "Review modus tollens"]}'
            ),
            provider="claude_code",
            model="claude-opus-5",
            latency_ms=1.0,
        )

    monkeypatch.setattr(tutor_mod.llm, "agenerate", fake_generate)

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post(
        "/api/lsat/tutor",
        json={"question_id": qid, "user_question": "Why is C wrong?"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["used_llm"] is True
    assert "Walkthrough" in body["coaching"]
    assert len(body["next_steps"]) == 2
    assert body["model"] == "claude_code/claude-opus-5"


@pytest.mark.asyncio
async def test_tutor_reports_the_serving_provider(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The response reports the tier the chain actually used."""
    from law_ai.core.llm.base import LLMResult
    from law_ai.lsat.services import tutor as tutor_mod

    async def fake_generate(*args: object, **kwargs: object) -> LLMResult:
        return LLMResult(
            text=(
                '{"coaching": "Claude Code walkthrough of the contrapositive.", '
                '"next_steps": ["Diagram conditionals", "Recheck modus tollens"]}'
            ),
            provider="claude_code",
            model="claude-opus-5",
            latency_ms=1.0,
        )

    monkeypatch.setattr(tutor_mod.llm, "agenerate", fake_generate)

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post(
        "/api/lsat/tutor", json={"question_id": qid, "user_question": "Why is C wrong?"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["used_llm"] is True
    assert body["model"] == "claude_code/claude-opus-5"
    assert "Claude Code walkthrough" in body["coaching"]
    assert len(body["next_steps"]) == 2


@pytest.mark.asyncio
async def test_tutor_strips_markdown_fence(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fenced ```json block still parses into structured coaching."""
    from law_ai.core.llm.base import LLMResult
    from law_ai.lsat.services import tutor as tutor_mod

    async def fenced(*args: object, **kwargs: object) -> LLMResult:
        return LLMResult(
            text=(
                "```json\n"
                '{"coaching": "Fenced but valid.", "next_steps": ["Step one"]}\n'
                "```"
            ),
            provider="claude_code",
            model="claude-opus-5",
            latency_ms=1.0,
        )

    monkeypatch.setattr(tutor_mod.llm, "agenerate", fenced)

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post("/api/lsat/tutor", json={"question_id": qid})
    assert res.status_code == 200
    body = res.json()
    assert body["used_llm"] is True
    assert body["coaching"] == "Fenced but valid."
    assert body["next_steps"] == ["Step one"]


@pytest.mark.asyncio
async def test_tutor_falls_back_when_the_provider_errors(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transport failure degrades to the offline path, never 500s."""
    import httpx

    from law_ai.lsat.services import tutor as tutor_mod

    async def boom(*args: object, **kwargs: object) -> object:
        raise httpx.ConnectError("provider unreachable")

    monkeypatch.setattr(tutor_mod.llm, "agenerate", boom)

    bank = load_bank()
    qid, q = next(iter(bank.items()))
    res = await client.post(
        "/api/lsat/tutor", json={"question_id": qid, "user_choice": q.correct}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["used_llm"] is False
    assert body["coaching"]
    assert body["model"] == "fallback/offline"


@pytest.mark.asyncio
async def test_tutor_reasons_about_the_board_the_learner_saw(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BL-20260905-61 — under a shuffle the tutor speaks in displayed labels.

    It used to reason in the stored ones, so it could name a letter that was
    somewhere else on the learner's screen.
    """
    from law_ai.lsat.services import tutor as tutor_mod
    from law_ai.lsat.services.shuffle import (
        LABELS,
        permute,
        to_display,
    )

    bank = load_bank()
    qid, q = next(
        (i, x) for i, x in bank.items() if x.correct != "A" and not x.passage_id
    )
    # An order that moves the key: display position 0 shows the stored key.
    stored_index = LABELS.index(q.correct)
    order = (stored_index, *[i for i in range(len(q.choices)) if i != stored_index])
    shown, token, _ = permute(q.choices, qid, order)
    assert to_display(q.correct, order) == "A" != q.correct

    seen: dict[str, str] = {}

    async def capture(prompt: str, *args: object, **kwargs: object) -> object:
        from law_ai.core.llm.base import LLMResult

        seen["prompt"] = prompt
        return LLMResult(
            text='{"coaching": "Board-aware.", "next_steps": []}',
            provider="claude_code",
            model="claude-opus-5",
            latency_ms=1.0,
        )

    monkeypatch.setattr(tutor_mod.llm, "agenerate", capture)

    res = await client.post(
        "/api/lsat/tutor",
        json={"question_id": qid, "user_choice": "A", "remap": token},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # The key the learner is looking at, and their pick graded against it.
    assert body["correct_choice"] == "A"
    assert body["is_correct"] is True
    # The prompt carries the displayed board, in display order.
    prompt = seen["prompt"]
    assert f"A. {shown[0].text}" in prompt
    assert "Authoritative correct choice: A" in prompt
    assert f"Authoritative correct choice: {q.correct}" not in prompt


@pytest.mark.asyncio
async def test_tutor_rejects_a_token_minted_for_another_question(
    client: AsyncClient,
) -> None:
    from law_ai.lsat.services.shuffle import permute

    bank = load_bank()
    ids = list(bank)
    _shown, token, _order = permute(bank[ids[0]].choices, ids[0])
    res = await client.post(
        "/api/lsat/tutor",
        json={"question_id": ids[1], "user_choice": "A", "remap": token},
    )
    assert res.status_code == 400
    assert "signed" in res.json()["detail"]


@pytest.mark.asyncio
async def test_tutor_unknown_question_returns_404(client: AsyncClient) -> None:
    res = await client.post(
        "/api/lsat/tutor", json={"question_id": "nope", "user_choice": "A"}
    )
    assert res.status_code == 404


# --- Spec 009: per-router auth gating ---


@pytest.mark.asyncio
async def test_lsat_open_when_no_keys_set(client: AsyncClient) -> None:
    """AC-1 — default-open posture preserved."""
    res = await client.get("/api/lsat/questions", params={"limit": 1})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_lsat_falls_back_to_agent_api_key(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-2/AC-3/AC-4 — fallback to AGENT_API_KEY when LSAT_API_KEY unset."""
    monkeypatch.setattr(settings, "AGENT_API_KEY", "shared")
    res = await client.get("/api/lsat/questions", params={"limit": 1})
    assert res.status_code == 401
    assert res.json()["detail"] == "missing api key"

    res = await client.get(
        "/api/lsat/questions",
        params={"limit": 1},
        headers={"X-API-Key": "wrong"},
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid api key"

    res = await client.get(
        "/api/lsat/questions",
        params={"limit": 1},
        headers={"X-API-Key": "shared"},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_lsat_per_router_key_isolation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-5 — LSAT_API_KEY override gates only /api/lsat/*; others stay open."""
    monkeypatch.setattr(settings, "LSAT_API_KEY", "lsat-key")
    # /api/lsat requires lsat-key
    res = await client.get("/api/lsat/questions", params={"limit": 1})
    assert res.status_code == 401
    res = await client.get(
        "/api/lsat/questions",
        params={"limit": 1},
        headers={"X-API-Key": "lsat-key"},
    )
    assert res.status_code == 200
    # /api/graph still open (no key configured for it)
    res = await client.get("/api/graph/stats")
    assert res.status_code in (200, 503)  # 503 if neo4j not running locally


@pytest.mark.asyncio
async def test_lsat_override_wins_over_fallback(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-6 — when both LSAT_API_KEY and AGENT_API_KEY are set, override wins."""
    monkeypatch.setattr(settings, "AGENT_API_KEY", "shared")
    monkeypatch.setattr(settings, "LSAT_API_KEY", "lsat-key")
    res = await client.get(
        "/api/lsat/questions",
        params={"limit": 1},
        headers={"X-API-Key": "shared"},
    )
    assert res.status_code == 401
    res = await client.get(
        "/api/lsat/questions",
        params={"limit": 1},
        headers={"X-API-Key": "lsat-key"},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_health_open_under_full_lockdown(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-7 — /health stays open even when every key is configured."""
    for name in ("AGENT_API_KEY", "ANALYSIS_API_KEY", "GRAPH_API_KEY", "LSAT_API_KEY"):
        monkeypatch.setattr(settings, name, "x")
    res = await client.get("/health")
    assert res.status_code in (200, 307)
    if res.status_code == 307:
        res = await client.get(res.headers["location"])
        assert res.status_code == 200


# ---------------------------------------------------------------------------
# Per-attempt answer shuffling (BL-20260606-01)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_questions_can_be_served_shuffled(client: AsyncClient) -> None:
    bank = load_bank()
    qid = next(iter(bank))
    res = await client.get(f"/api/lsat/questions/{qid}", params={"shuffle": "1"})
    assert res.status_code == 200
    body = res.json()
    assert body["remap"]
    assert [c["label"] for c in body["choices"]] == ["A", "B", "C", "D", "E"]
    # Same five choices, possibly in a different order — nothing is invented.
    assert sorted(c["text"] for c in body["choices"]) == sorted(
        c.text for c in bank[qid].choices
    )
    assert "correct" not in body


@pytest.mark.asyncio
async def test_an_unshuffled_serve_carries_no_token(client: AsyncClient) -> None:
    bank = load_bank()
    qid = next(iter(bank))
    res = await client.get(f"/api/lsat/questions/{qid}")
    assert res.status_code == 200
    assert "remap" not in res.json()


@pytest.mark.asyncio
async def test_the_key_moves_across_attempts(client: AsyncClient) -> None:
    """The defect this closes: the credited answer used to sit still forever."""
    from law_ai.lsat.services.shuffle import order_from_token, to_display

    bank = load_bank()
    qid, question = next(iter(bank.items()))
    seen = set()
    for _ in range(25):
        res = await client.get(f"/api/lsat/questions/{qid}", params={"shuffle": "1"})
        order = order_from_token(qid, res.json()["remap"])
        seen.add(to_display(question.correct, order))
    assert len(seen) > 1


@pytest.mark.asyncio
async def test_grading_reads_the_answer_in_the_order_it_was_served(
    client: AsyncClient,
) -> None:
    from law_ai.lsat.services.shuffle import order_from_token, to_display

    bank = load_bank()
    qid, question = next(iter(bank.items()))
    served = await client.get(f"/api/lsat/questions/{qid}", params={"shuffle": "1"})
    token = served.json()["remap"]
    displayed_key = to_display(question.correct, order_from_token(qid, token))

    right = await client.post(
        "/api/lsat/grade",
        json={"question_id": qid, "choice": displayed_key, "remap": token},
    )
    assert right.status_code == 200
    assert right.json()["correct"] is True
    # The key comes back where the learner saw it, not where it is stored.
    assert right.json()["correct_choice"] == displayed_key

    wrong_label = next(c for c in "ABCDE" if c != displayed_key)
    wrong = await client.post(
        "/api/lsat/grade",
        json={"question_id": qid, "choice": wrong_label, "remap": token},
    )
    assert wrong.json()["correct"] is False
    assert wrong.json()["correct_choice"] == displayed_key


@pytest.mark.asyncio
async def test_the_explanation_speaks_in_displayed_labels(
    client: AsyncClient,
) -> None:
    from law_ai.lsat.services.shuffle import (
        display_mapping,
        label_references,
        order_from_token,
        remap_labels,
    )

    bank = load_bank()
    bound = [q for q in bank.values() if label_references(q.explanation)]
    assert bound, "no label-bound explanation in the bank to check"
    question = bound[0]
    served = await client.get(
        f"/api/lsat/questions/{question.id}", params={"shuffle": "1"}
    )
    token = served.json()["remap"]
    mapping = display_mapping(order_from_token(question.id, token))
    graded = await client.post(
        "/api/lsat/grade",
        json={"question_id": question.id, "choice": "A", "remap": token},
    )
    assert graded.json()["explanation"] == remap_labels(question.explanation, mapping)


@pytest.mark.asyncio
async def test_a_tampered_token_is_refused(client: AsyncClient) -> None:
    """A token whose order was edited must not grade against the stored order."""
    bank = load_bank()
    qid = next(iter(bank))
    served = await client.get(f"/api/lsat/questions/{qid}", params={"shuffle": "1"})
    digits, _, signature = served.json()["remap"].partition(".")
    forged = "".join(reversed(digits))
    res = await client.post(
        "/api/lsat/grade",
        json={"question_id": qid, "choice": "A", "remap": f"{forged}.{signature}"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_a_token_from_another_question_is_refused(
    client: AsyncClient,
) -> None:
    bank = load_bank()
    first, second = list(bank)[:2]
    served = await client.get(f"/api/lsat/questions/{first}", params={"shuffle": "1"})
    res = await client.post(
        "/api/lsat/grade",
        json={
            "question_id": second,
            "choice": "A",
            "remap": served.json()["remap"],
        },
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_passage_questions_can_be_served_shuffled(client: AsyncClient) -> None:
    """RC and LG come through the passage endpoint, not /questions/<id>.

    They are the majority of the shipped bank, and they used to be the half of
    it where the key never moved — the defect BL-20260606-01 names, surviving
    on the surface that serves most of the items.
    """
    from law_ai.lsat.services.shuffle import order_from_token, to_display

    bank = load_bank()
    passage_id = next(q.passage_id for q in bank.values() if q.passage_id)
    attached = {q.id: q for q in bank.values() if q.passage_id == passage_id}

    res = await client.get(f"/api/lsat/passages/{passage_id}", params={"shuffle": "1"})
    assert res.status_code == 200
    served = res.json()["questions"]
    assert served
    for row in served:
        assert row["remap"], f"{row['id']} served without a remap token"
        assert [c["label"] for c in row["choices"]] == ["A", "B", "C", "D", "E"]
        # Same five choices, reordered — nothing invented, nothing dropped.
        assert sorted(c["text"] for c in row["choices"]) == sorted(
            c.text for c in attached[row["id"]].choices
        )
        assert "correct" not in row

    # And the key actually moves across attempts.
    qid = served[0]["id"]
    seen = set()
    for _ in range(25):
        again = await client.get(
            f"/api/lsat/passages/{passage_id}", params={"shuffle": "1"}
        )
        row = next(r for r in again.json()["questions"] if r["id"] == qid)
        order = order_from_token(qid, row["remap"])
        seen.add(to_display(attached[qid].correct, order))
    assert len(seen) > 1


@pytest.mark.asyncio
async def test_passage_serve_without_shuffle_carries_no_token(
    client: AsyncClient,
) -> None:
    bank = load_bank()
    passage_id = next(q.passage_id for q in bank.values() if q.passage_id)
    res = await client.get(f"/api/lsat/passages/{passage_id}")
    assert res.status_code == 200
    assert all("remap" not in row for row in res.json()["questions"])


@pytest.mark.asyncio
async def test_a_passage_token_grades_in_the_order_it_was_served(
    client: AsyncClient,
) -> None:
    from law_ai.lsat.services.shuffle import order_from_token, to_display

    bank = load_bank()
    passage_id = next(q.passage_id for q in bank.values() if q.passage_id)
    res = await client.get(f"/api/lsat/passages/{passage_id}", params={"shuffle": "1"})
    row = res.json()["questions"][0]
    question = bank[row["id"]]
    displayed_key = to_display(
        question.correct, order_from_token(question.id, row["remap"])
    )
    graded = await client.post(
        "/api/lsat/grade",
        json={
            "question_id": question.id,
            "choice": displayed_key,
            "remap": row["remap"],
        },
    )
    assert graded.status_code == 200
    assert graded.json()["correct"] is True
    assert graded.json()["correct_choice"] == displayed_key


@pytest.mark.asyncio
async def test_grading_without_a_token_still_uses_the_stored_order(
    client: AsyncClient,
) -> None:
    """Shuffling is opt-in per serve; an old client keeps working."""
    bank = load_bank()
    qid, question = next(iter(bank.items()))
    res = await client.post(
        "/api/lsat/grade", json={"question_id": qid, "choice": question.correct}
    )
    assert res.json()["correct"] is True
    assert res.json()["correct_choice"] == question.correct


# ---------------------------------------------------------------------------
# Tutor progress streaming (BL-20260811-15)
# ---------------------------------------------------------------------------


class _CapturingLayer:
    """A channel layer double recording every group_send."""

    def __init__(self) -> None:
        self.sends: list[tuple[str, dict]] = []

    async def group_send(self, group: str, message: dict) -> None:
        self.sends.append((group, message))


@pytest.fixture()
def ws_capture(monkeypatch: pytest.MonkeyPatch) -> _CapturingLayer:
    from law_ai.agentsapi import streaming

    layer = _CapturingLayer()
    monkeypatch.setattr(streaming, "get_channel_layer", lambda: layer)
    return layer


def _events(layer: _CapturingLayer) -> list[dict]:
    return [message["payload"] for _group, message in layer.sends]


@pytest.mark.asyncio
async def test_tutor_streams_progress_to_the_clients_stream_id(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, ws_capture: _CapturingLayer
) -> None:
    """The learner sees which tier is thinking instead of a bare spinner."""
    from law_ai.core.llm.base import LLMResult
    from law_ai.lsat.services import tutor as tutor_mod

    async def fake_generate(*args: object, **kwargs: object) -> LLMResult:
        return LLMResult(
            text='{"coaching": "Contrapositive first.", "next_steps": ["Diagram"]}',
            provider="claude_code",
            model="claude-opus-5",
            latency_ms=1.0,
        )

    monkeypatch.setattr(tutor_mod.llm, "agenerate", fake_generate)

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post(
        "/api/lsat/tutor",
        json={"question_id": qid, "stream_id": "run-abc.1"},
    )

    assert res.status_code == 200
    groups = {group for group, _message in ws_capture.sends}
    assert groups == {"agent-run-run-abc.1"}
    stages = [e.get("stage") for e in _events(ws_capture) if e["type"] == "tutor_step"]
    assert stages == ["generating", "generated"]
    terminal = _events(ws_capture)[-1]
    assert terminal["type"] == "complete"
    assert terminal["model"] == "claude_code/claude-opus-5"


@pytest.mark.asyncio
async def test_tutor_streams_a_fallback_stage_when_the_chain_is_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, ws_capture: _CapturingLayer
) -> None:
    from law_ai.core.llm.base import LLMUnavailableError
    from law_ai.lsat.services import tutor as tutor_mod

    async def boom(*args: object, **kwargs: object) -> object:
        raise LLMUnavailableError("all tiers down")

    monkeypatch.setattr(tutor_mod.llm, "agenerate", boom)

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post(
        "/api/lsat/tutor",
        json={"question_id": qid, "stream_id": "run-fallback"},
    )

    assert res.status_code == 200
    assert res.json()["used_llm"] is False
    stages = [e.get("stage") for e in _events(ws_capture) if e["type"] == "tutor_step"]
    assert stages == ["generating", "fallback"]


@pytest.mark.asyncio
async def test_tutor_without_a_stream_id_emits_nothing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, ws_capture: _CapturingLayer
) -> None:
    """The REST contract is unchanged for every existing client."""
    from law_ai.core.llm.base import LLMUnavailableError
    from law_ai.lsat.services import tutor as tutor_mod

    async def boom(*args: object, **kwargs: object) -> object:
        raise LLMUnavailableError("down")

    monkeypatch.setattr(tutor_mod.llm, "agenerate", boom)

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post("/api/lsat/tutor", json={"question_id": qid})

    assert res.status_code == 200
    assert ws_capture.sends == []


@pytest.mark.asyncio
async def test_tutor_rejects_a_malformed_stream_id(client: AsyncClient) -> None:
    """A group name is never sanitised into existence — the request is refused."""
    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post(
        "/api/lsat/tutor",
        json={"question_id": qid, "stream_id": "../other-run"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_a_dead_channel_layer_never_costs_the_learner_a_walkthrough(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec 021 AC-2: the stream is fire-and-forget, not a dependency."""
    from law_ai.agentsapi import streaming
    from law_ai.core.llm.base import LLMUnavailableError
    from law_ai.lsat.services import tutor as tutor_mod

    def _explode() -> object:
        raise RuntimeError("redis is gone")

    monkeypatch.setattr(streaming, "get_channel_layer", _explode)

    async def boom(*args: object, **kwargs: object) -> object:
        raise LLMUnavailableError("down")

    monkeypatch.setattr(tutor_mod.llm, "agenerate", boom)

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post(
        "/api/lsat/tutor",
        json={"question_id": qid, "stream_id": "run-redis-down"},
    )
    assert res.status_code == 200
    assert res.json()["coaching"]


# ---------------------------------------------------------------------------
# Library reading progress (BL-20260903-05)
#
# Read state was per-browser localStorage on both products: no cross-device
# sync, and "articles read" invisible next to drill accuracy.
# ---------------------------------------------------------------------------


def _sectioned_article() -> Any:
    """An article that names at least one section, so the fold is observable."""
    return next(a for a in load_library().values() if a.sections)


@pytest.mark.asyncio
async def test_library_read_round_trips_through_the_audit_store(
    client: AsyncClient,
) -> None:
    article = _sectioned_article()
    empty = await client.get("/api/lsat/library/read")
    assert empty.status_code == 200
    assert empty.json() == {"read": [], "count": 0}

    marked = await client.post(
        "/api/lsat/library/read", json={"article_id": article.id}
    )
    assert marked.status_code == 200
    assert marked.json()["read"] == [article.id]

    # A fresh browser hydrates from the server rather than starting over.
    fresh = await client.get("/api/lsat/library/read")
    assert fresh.json() == {"read": [article.id], "count": 1}


@pytest.mark.asyncio
async def test_library_unread_is_a_later_event_not_a_deletion(
    client: AsyncClient,
) -> None:
    article = _sectioned_article()
    await client.post("/api/lsat/library/read", json={"article_id": article.id})
    unmarked = await client.post(
        "/api/lsat/library/read", json={"article_id": article.id, "read": False}
    )
    assert unmarked.status_code == 200
    assert unmarked.json() == {"read": [], "count": 0}
    # …and marking it again brings it back, newest event winning.
    again = await client.post(
        "/api/lsat/library/read", json={"article_id": article.id, "read": True}
    )
    assert again.json()["read"] == [article.id]


@pytest.mark.asyncio
async def test_library_read_rejects_an_unknown_article(client: AsyncClient) -> None:
    res = await client.post(
        "/api/lsat/library/read", json={"article_id": "no-such-article"}
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_library_read_requires_an_article_id(client: AsyncClient) -> None:
    res = await client.post("/api/lsat/library/read", json={})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_stats_folds_in_articles_read(client: AsyncClient) -> None:
    article = _sectioned_article()
    before = await client.get("/api/lsat/stats")
    assert before.status_code == 200
    assert before.json()["articles_read"] == 0
    assert before.json()["articles_total"] == len(load_library())

    await client.post("/api/lsat/library/read", json={"article_id": article.id})
    after = await client.get("/api/lsat/stats")
    body = after.json()
    assert body["articles_read"] == 1
    for sec in article.sections:
        assert body["by_section"][str(sec)]["articles_read"] == 1


@pytest.mark.asyncio
async def test_stats_section_filter_applies_to_reading_too(
    client: AsyncClient,
) -> None:
    article = _sectioned_article()
    section = str(article.sections[0])
    other = next(s for s in ("LR", "RC", "LG") if s != section)

    await client.post("/api/lsat/library/read", json={"article_id": article.id})
    same = await client.get("/api/lsat/stats", params={"section": section})
    assert same.json()["articles_read"] == 1
    # An article that does not serve the section is not counted under it.
    if other not in [str(s) for s in article.sections]:
        off = await client.get("/api/lsat/stats", params={"section": other})
        assert off.json()["articles_read"] == 0


# ---------------------------------------------------------------------------
# Per-reveal hint events (BL-20260830-13)
#
# Only grade-time ``hints_used`` was recorded, which can say "assisted" and
# nothing else — and says nothing at all about a question never submitted.
# ---------------------------------------------------------------------------


def _question_with_a_guide() -> str:
    from law_ai.lsat.services.guides import load_guides

    return next(iter(load_guides()))


@pytest.mark.asyncio
async def test_hint_reveal_records_one_event_per_post(client: AsyncClient) -> None:
    qid = _question_with_a_guide()
    for i in range(3):
        res = await client.post(
            f"/api/lsat/questions/{qid}/hint",
            json={"step_index": i, "revealed_count": i + 1},
        )
        assert res.status_code == 202, res.text

    stats = await client.get("/api/lsat/stats")
    hints = stats.json()["hints"]
    assert hints["reveals"] == 3
    assert hints["questions_hinted"] == 1
    # The number that tells a one-hint nudge from a walkthrough.
    assert hints["max_depth"] == 3
    assert hints["spoiler_reveals"] == 0


@pytest.mark.asyncio
async def test_hint_reveal_counts_even_without_a_grade(client: AsyncClient) -> None:
    """Hints on a question the learner never submits are the blind spot."""
    qid = _question_with_a_guide()
    await client.post(
        f"/api/lsat/questions/{qid}/hint",
        json={"step_index": 0, "revealed_count": 1},
    )
    body = (await client.get("/api/lsat/stats")).json()
    assert body["attempts"] == 0
    assert body["hints"]["reveals"] == 1


@pytest.mark.asyncio
async def test_hint_reveal_marks_a_spoiler_unlock(client: AsyncClient) -> None:
    from law_ai.lsat.services.guides import load_guides

    qid, guide = next(iter(load_guides().items()))
    last = len(guide.steps) - 1
    res = await client.post(
        f"/api/lsat/questions/{qid}/hint",
        json={"step_index": last, "revealed_count": last + 1, "spoiler": True},
    )
    assert res.status_code == 202
    assert (await client.get("/api/lsat/stats")).json()["hints"]["spoiler_reveals"] == 1


@pytest.mark.asyncio
async def test_hint_reveal_404s_for_a_guideless_question(client: AsyncClient) -> None:
    from law_ai.lsat.services.guides import load_guides

    guides = load_guides()
    qid = next(q for q in load_bank() if q not in guides)
    res = await client.post(
        f"/api/lsat/questions/{qid}/hint",
        json={"step_index": 0, "revealed_count": 1},
    )
    assert res.status_code == 404
    assert res.json()["has_tutor"] is True


@pytest.mark.asyncio
async def test_hint_reveal_rejects_a_step_past_the_end(client: AsyncClient) -> None:
    qid = _question_with_a_guide()
    res = await client.post(
        f"/api/lsat/questions/{qid}/hint",
        json={"step_index": 49, "revealed_count": 50},
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Tutor token streaming (BL-20260503-03)
# ---------------------------------------------------------------------------


def _fake_astream(*deltas: str):
    """Patch the chain's astream with a fixed sequence of coaching deltas."""
    from law_ai.core.llm.base import LLMChunk

    def _stream(prompt: str, **kwargs: object):
        async def _gen():
            for index, text in enumerate(deltas):
                yield LLMChunk(
                    text=text,
                    provider="claude_code",
                    model="claude-opus-5",
                    first=index == 0,
                )

        return _gen()

    return _stream


@pytest.mark.asyncio
async def test_tutor_streams_coaching_tokens(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, ws_capture: _CapturingLayer
) -> None:
    """The learner reads the walkthrough as it is written, not after."""
    from law_ai.lsat.services import tutor as tutor_mod

    monkeypatch.setattr(
        tutor_mod.llm,
        "astream",
        _fake_astream("Contrapositive ", "first.\n", "NEXT STEPS: Diagram | Drill"),
    )

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post(
        "/api/lsat/tutor",
        json={
            "question_id": qid,
            "stream_id": "run-tokens",
            "stream_tokens": True,
        },
    )

    assert res.status_code == 200
    body = res.json()
    assert body["used_llm"] is True
    # The prose is the coaching; the marker line becomes structure.
    assert body["coaching"] == "Contrapositive first."
    assert body["next_steps"] == ["Diagram", "Drill"]

    tokens = [e for e in _events(ws_capture) if e["type"] == "tutor_token"]
    assert "".join(t["text"] for t in tokens).startswith("Contrapositive first.")
    assert tokens[0]["model"] == "claude_code/claude-opus-5"


@pytest.mark.asyncio
async def test_the_streamed_variant_asks_for_prose_not_json(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, ws_capture: _CapturingLayer
) -> None:
    """A partial JSON object is not a document, so the contract changes."""
    from law_ai.lsat.services import tutor as tutor_mod

    seen: dict[str, object] = {}

    def _stream(prompt: str, **kwargs: object):
        seen["prompt"] = prompt
        seen["system"] = kwargs.get("system")

        async def _gen():
            from law_ai.core.llm.base import LLMChunk

            yield LLMChunk(text="Prose.", provider="ollama", model="m", first=True)

        return _gen()

    monkeypatch.setattr(tutor_mod.llm, "astream", _stream)

    bank = load_bank()
    qid = next(iter(bank))
    await client.post(
        "/api/lsat/tutor",
        json={"question_id": qid, "stream_id": "run-prose", "stream_tokens": True},
    )

    assert "plain prose" in str(seen["system"])
    assert "NEXT STEPS:" in str(seen["prompt"])
    # The buffered contract's "Respond as JSON only" must not survive here.
    assert "Respond as JSON only" not in str(seen["prompt"])


@pytest.mark.asyncio
async def test_a_broken_stream_falls_back_instead_of_half_an_answer(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, ws_capture: _CapturingLayer
) -> None:
    """Constitution §13: a partial walkthrough must not be served as one."""
    from law_ai.core.llm.base import LLMChunk, LLMStreamInterrupted
    from law_ai.lsat.services import tutor as tutor_mod

    def _stream(prompt: str, **kwargs: object):
        async def _gen():
            yield LLMChunk(text="half an ", provider="xai", model="grok", first=True)
            raise LLMStreamInterrupted("tier died", partial="half an ")

        return _gen()

    monkeypatch.setattr(tutor_mod.llm, "astream", _stream)

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post(
        "/api/lsat/tutor",
        json={"question_id": qid, "stream_id": "run-broken", "stream_tokens": True},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["used_llm"] is False
    assert "half an " not in body["coaching"]
    stages = [e.get("stage") for e in _events(ws_capture) if e["type"] == "tutor_step"]
    # The client is told to clear what it already rendered.
    assert "interrupted" in stages


@pytest.mark.asyncio
async def test_stream_tokens_without_a_stream_id_stays_buffered(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, ws_capture: _CapturingLayer
) -> None:
    """There is nowhere to send deltas, so the JSON contract is kept."""
    from law_ai.core.llm.base import LLMResult
    from law_ai.lsat.services import tutor as tutor_mod

    async def fake_generate(*args: object, **kwargs: object) -> LLMResult:
        return LLMResult(
            text='{"coaching": "Buffered.", "next_steps": ["Go"]}',
            provider="claude_code",
            model="claude-opus-5",
            latency_ms=1.0,
        )

    monkeypatch.setattr(tutor_mod.llm, "agenerate", fake_generate)

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post(
        "/api/lsat/tutor", json={"question_id": qid, "stream_tokens": True}
    )

    assert res.status_code == 200
    assert res.json()["coaching"] == "Buffered."
    assert ws_capture.sends == []


@pytest.mark.asyncio
async def test_streamed_and_buffered_walkthroughs_do_not_share_a_cache_entry(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, ws_capture: _CapturingLayer
) -> None:
    """One key per contract: the two produce different documents."""
    from law_ai.core.llm.base import LLMResult
    from law_ai.lsat.services import tutor as tutor_mod

    async def fake_generate(*args: object, **kwargs: object) -> LLMResult:
        return LLMResult(
            text='{"coaching": "Buffered answer.", "next_steps": ["Go"]}',
            provider="claude_code",
            model="claude-opus-5",
            latency_ms=1.0,
        )

    monkeypatch.setattr(tutor_mod.llm, "agenerate", fake_generate)
    monkeypatch.setattr(tutor_mod.llm, "astream", _fake_astream("Streamed answer."))

    bank = load_bank()
    qid = next(iter(bank))
    buffered = await client.post("/api/lsat/tutor", json={"question_id": qid})
    streamed = await client.post(
        "/api/lsat/tutor",
        json={"question_id": qid, "stream_id": "run-cache", "stream_tokens": True},
    )

    assert buffered.json()["coaching"] == "Buffered answer."
    assert streamed.json()["coaching"] == "Streamed answer."
    assert streamed.json()["cached"] is False


# ---------------------------------------------------------------------------
# Writing practice in the stats surface (BL-20260831-27)
#
# `LSATWritingEvaluator` always persisted — every evaluation is an
# `lsat_writing_evaluate` event in the same store `lsat_grade` uses. Nothing
# read them back, so writing progress across attempts was invisible.
# ---------------------------------------------------------------------------


def _record_evaluation(**over: Any) -> None:
    from law_ai.core import audit_jsonl as audit_store

    event: dict[str, Any] = {
        "type": "lsat_writing_evaluate",
        "prompt_id": "ws-001",
        "section": "WS",
        "response_chars": 1200,
        "weighted_band": 2.5,
        "model": "claude_code/claude-opus-5",
        "degraded": False,
        "prompt_version": "lsat_writing_evaluator.v1",
        "rubric_id": "ws-rubric-standard",
        "criteria": {"position": 3, "counterargument": 2},
    }
    event.update(over)
    audit_store.record(event)


@pytest.mark.asyncio
async def test_stats_reports_no_writing_until_there_is_some(
    client: AsyncClient,
) -> None:
    body = (await client.get("/api/lsat/stats")).json()
    assert body["writing"] == {
        "attempts": 0,
        "by_prompt": {},
        "latest_band": None,
        "best_band": None,
        "band_trend": [],
        "degraded": 0,
        "model": None,
        "prompt_version": None,
    }


@pytest.mark.asyncio
async def test_stats_folds_writing_evaluations_in_order(client: AsyncClient) -> None:
    _record_evaluation(weighted_band=2.0)
    _record_evaluation(weighted_band=3.5)
    _record_evaluation(prompt_id="ws-002", weighted_band=3.0, degraded=True)

    writing = (await client.get("/api/lsat/stats")).json()["writing"]
    assert writing["attempts"] == 3
    assert writing["by_prompt"] == {"ws-001": 2, "ws-002": 1}
    # Oldest first: a trend that read backwards would show improvement as decay.
    assert writing["band_trend"] == [2.0, 3.5, 3.0]
    assert writing["latest_band"] == 3.0
    assert writing["best_band"] == 3.5
    assert writing["degraded"] == 1
    # NFR-PROV-1: bands are machine-derived and say whose machine.
    assert writing["model"] == "claude_code/claude-opus-5"
    assert writing["prompt_version"] == "lsat_writing_evaluator.v1"


@pytest.mark.asyncio
async def test_stats_writing_survives_the_ws_section_filter(
    client: AsyncClient,
) -> None:
    _record_evaluation()
    ws = (await client.get("/api/lsat/stats", params={"section": "WS"})).json()
    assert ws["writing"]["attempts"] == 1
    # …and asking about a keyed section is not asking about the essay.
    lr = (await client.get("/api/lsat/stats", params={"section": "LR"})).json()
    assert "writing" not in lr


@pytest.mark.asyncio
async def test_stats_reads_the_audit_tail_once(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BL-20260905-38: grades + three folds used to be four full JSONL reads."""
    from law_ai.core import audit_jsonl

    _record_evaluation()
    calls: list[int] = []
    real = audit_jsonl.tail

    def counting_tail(limit: int = 50) -> Any:
        calls.append(limit)
        return real(limit)

    monkeypatch.setattr(audit_jsonl, "tail", counting_tail)
    res = await client.get("/api/lsat/stats")
    assert res.status_code == 200
    assert res.json()["writing"]["attempts"] == 1
    assert len(calls) == 1, calls


# ---------------------------------------------------------------------------
# Versioned tutor prompt (BL-20260503-01)
# ---------------------------------------------------------------------------


def test_the_tutor_prompt_lives_in_a_versioned_file() -> None:
    """Wording in a file, not in Python, is what makes drift reviewable."""
    from law_ai.lsat.services import tutor as tutor_mod

    assert tutor_mod.PROMPT_PATH.is_file()
    assert tutor_mod.PROMPT_PATH.name == "lsat_tutor.v1.md"
    # The version string and the file name have to move together, or a cache
    # key would outlive the wording it was built from.
    assert tutor_mod.PROMPT_VERSION == "lsat_tutor/1"

    sections = tutor_mod._prompt_sections()
    assert {
        "system.buffered",
        "system.streamed",
        "contract.buffered",
        "contract.streamed",
        "user",
    } <= set(sections)


def test_the_rendered_prompt_carries_the_question_and_the_key() -> None:
    from law_ai.lsat.services import tutor as tutor_mod

    bank = load_bank()
    q = next(iter(bank.values()))
    rendered = tutor_mod._build_prompt(
        tutor_mod._PromptCtx(q, None, []), "A", "Why is C wrong?"
    )

    assert q.stem in rendered
    assert f"Authoritative correct choice: {q.correct}" in rendered
    assert "Learner picked: A" in rendered
    assert "Learner asks: Why is C wrong?" in rendered
    assert "Respond as JSON only" in rendered
    # No unsubstituted placeholders survived the render.
    assert "{" not in rendered.replace("{}", "")


@pytest.mark.asyncio
async def test_the_llm_call_event_names_the_prompt_version(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Constitution §5: the audit row says which prompt produced the call."""
    from unittest.mock import patch

    from law_ai.core.llm.base import LLMResult
    from law_ai.lsat.services import tutor as tutor_mod

    seen: dict[str, object] = {}

    async def fake_agenerate(prompt: str, **kwargs: object) -> LLMResult:
        seen.update(kwargs)
        return LLMResult(
            text='{"coaching": "Ok.", "next_steps": []}',
            provider="claude_code",
            model="claude-opus-5",
            latency_ms=1.0,
        )

    monkeypatch.setattr(tutor_mod.llm, "agenerate", fake_agenerate)

    bank = load_bank()
    qid = next(iter(bank))
    await client.post("/api/lsat/tutor", json={"question_id": qid})
    assert seen["prompt_id"] == "lsat_tutor"
    assert seen["prompt_version"] == "lsat_tutor/1"

    # And the router actually puts them on the event (the tutor only supplies
    # them; provenance is the router's job).
    from law_ai.core.llm import router

    with (
        patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log,
        patch(
            "law_ai.core.llm.router.build_chain",
            return_value=(_PromptEchoProvider(),),
        ),
    ):
        await router.agenerate(
            "q", agent="lsat_tutor", prompt_id="lsat_tutor", prompt_version="v9"
        )

    payload = log.call_args[0][1]
    assert payload["prompt_id"] == "lsat_tutor"
    assert payload["prompt_version"] == "v9"


class _PromptEchoProvider:
    """Minimal provider double for the provenance assertion above."""

    name = "claude_code"

    def configured(self) -> bool:
        return True

    def unconfigured_reason(self) -> str | None:
        return None

    def model_for(self, request: object) -> str:
        return "test-model"

    async def agenerate(self, request: object) -> str:
        return "ok"

    async def probe(self) -> dict[str, object]:
        return {"reachable": True}


# ---------------------------------------------------------------------------
# LR Tutor attempt trace (BL-20260429-18)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_trace_reaches_the_prompt(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The distinguishing clause: coaching addressed to *this* reasoning."""
    from law_ai.core.llm.base import LLMResult
    from law_ai.lsat.services import tutor as tutor_mod

    seen: dict[str, str] = {}

    async def fake_generate(prompt: str, **kwargs: object) -> LLMResult:
        seen["prompt"] = prompt
        return LLMResult(
            text='{"coaching": "Your split was right.", "next_steps": []}',
            provider="claude_code",
            model="claude-opus-5",
            latency_ms=1.0,
        )

    monkeypatch.setattr(tutor_mod.llm, "agenerate", fake_generate)

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post(
        "/api/lsat/tutor",
        json={
            "question_id": qid,
            "user_choice": "A",
            "trace": {
                "eliminated": ["B", "D"],
                "hints_used": 2,
                "seconds_on_question": 95,
                "prior_choices": ["E"],
            },
        },
    )

    assert res.status_code == 200
    prompt = seen["prompt"]
    assert "Ruled out: B, D" in prompt
    assert "Previously answered: E" in prompt
    assert "Revealed 2 solve-assist step(s)" in prompt
    assert "Spent about 95s on it" in prompt


@pytest.mark.asyncio
async def test_no_trace_renders_no_trace_block(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A client that captures nothing gets exactly the old prompt."""
    from law_ai.core.llm.base import LLMResult
    from law_ai.lsat.services import tutor as tutor_mod

    seen: dict[str, str] = {}

    async def fake_generate(prompt: str, **kwargs: object) -> LLMResult:
        seen["prompt"] = prompt
        return LLMResult(
            text='{"coaching": "Ok.", "next_steps": []}',
            provider="claude_code",
            model="claude-opus-5",
            latency_ms=1.0,
        )

    monkeypatch.setattr(tutor_mod.llm, "agenerate", fake_generate)

    bank = load_bank()
    qid = next(iter(bank))
    await client.post("/api/lsat/tutor", json={"question_id": qid})
    assert "What the learner did on this attempt" not in seen["prompt"]


@pytest.mark.asyncio
async def test_the_offline_fallback_answers_the_trace_too(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fallback has no model, but it does have the learner's reasoning."""
    from law_ai.core.llm.base import LLMUnavailableError
    from law_ai.lsat.services import tutor as tutor_mod

    async def boom(*args: object, **kwargs: object) -> object:
        raise LLMUnavailableError("all tiers down")

    monkeypatch.setattr(tutor_mod.llm, "agenerate", boom)

    bank = load_bank()
    q = next(iter(load_bank().values()))
    wrong = next(c.label for c in q.choices if c.label != q.correct)
    res = await client.post(
        "/api/lsat/tutor",
        json={
            "question_id": q.id,
            "user_choice": wrong,
            "trace": {"eliminated": [q.correct], "hints_used": 1},
        },
    )

    assert res.status_code == 200
    coaching = res.json()["coaching"]
    # Eliminating the key is the single most useful thing to name back.
    assert f"You ruled out {q.correct}" in coaching
    assert "re-examine" in coaching
    assert bank  # the bank fixture is what supplied the question


@pytest.mark.asyncio
async def test_two_different_attempts_do_not_share_a_walkthrough(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per-attempt is the promise; a shared cache entry would break it."""
    from law_ai.core.llm.base import LLMResult
    from law_ai.lsat.services import tutor as tutor_mod

    calls: list[str] = []

    async def fake_generate(prompt: str, **kwargs: object) -> LLMResult:
        calls.append(prompt)
        return LLMResult(
            text=f'{{"coaching": "Answer {len(calls)}.", "next_steps": []}}',
            provider="claude_code",
            model="claude-opus-5",
            latency_ms=1.0,
        )

    monkeypatch.setattr(tutor_mod.llm, "agenerate", fake_generate)

    bank = load_bank()
    qid = next(iter(bank))
    first = await client.post(
        "/api/lsat/tutor",
        json={"question_id": qid, "user_choice": "A", "trace": {"eliminated": ["B"]}},
    )
    second = await client.post(
        "/api/lsat/tutor",
        json={
            "question_id": qid,
            "user_choice": "A",
            "trace": {"eliminated": ["B", "C"]},
        },
    )
    repeat = await client.post(
        "/api/lsat/tutor",
        json={"question_id": qid, "user_choice": "A", "trace": {"eliminated": ["B"]}},
    )

    assert first.json()["coaching"] != second.json()["coaching"]
    # The same attempt shape still hits the cache — the key is coarse, not absent.
    assert repeat.json()["cached"] is True
    assert repeat.json()["coaching"] == first.json()["coaching"]
    assert len(calls) == 2


def test_the_trace_signature_buckets_time_but_not_eliminations() -> None:
    from law_ai.lsat.services.tutor import TutorTrace

    a = TutorTrace(eliminated=["B"], seconds_on_question=61)
    b = TutorTrace(eliminated=["B"], seconds_on_question=95)
    c = TutorTrace(eliminated=["B", "C"], seconds_on_question=61)

    # A few seconds apart is the same attempt; a different split is not.
    assert a.signature() == b.signature()
    assert a.signature() != c.signature()
    assert TutorTrace().is_empty() is True


# ---------------------------------------------------------------------------
# Tutor trace deep link (BL-20260503-06)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tutor_reports_no_trace_when_telemetry_is_disabled(
    client: AsyncClient, settings: Any
) -> None:
    """Telemetry off: no collector, no trace link, and no broken link.

    The disabled state is set here rather than assumed (bamr87/bamr87#253).
    The ``backend`` compose service the nightly runs this suite in sets
    ``PHOENIX_COLLECTOR_ENDPOINT`` and ``OBSERVABILITY_BACKEND=phoenix``, so a
    test that relied on the ambient default measured the developer's
    environment instead of the gate: green on a laptop, red in CI. The
    companion test below pins the *enabled* half against the same settings.
    """
    settings.OBSERVABILITY_BACKEND = "phoenix"
    settings.PHOENIX_COLLECTOR_ENDPOINT = None
    settings.OTEL_EXPORTER_OTLP_ENDPOINT = ""
    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post("/api/lsat/tutor", json={"question_id": qid})
    assert res.status_code == 200
    body = res.json()
    # The fields exist either way — a client should not have to branch on
    # whether telemetry happened to be configured.
    assert "trace_id" in body
    assert body["phoenix_trace_url"] is None
    # BL-20260503-06 asked for both fields the analysis contract carries, so
    # the tutor contract mirrors it field for field. The tutor runs no
    # LangGraph graph, so the thread id is present and null — the same thing
    # the analysis response says when no graph ran — rather than absent, which
    # would force a client to branch on which endpoint answered.
    assert "langgraph_thread_id" in body
    assert body["langgraph_thread_id"] is None


@pytest.mark.asyncio
async def test_tutor_links_a_well_formed_trace_url_when_telemetry_is_enabled(
    client: AsyncClient, settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the gate above, driven by the same settings.

    Telemetry configured (a collector endpoint and a UI) must produce a link
    built from those settings and this request's trace id — through the real
    ``trace_url``, not a stub — so the disabled test cannot pass merely
    because the link is never produced.
    """
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.trace import TracerProvider

    # A real SDK provider so the span has a valid context; no exporter, so
    # nothing leaves the process.
    monkeypatch.setattr(
        otel_trace, "get_tracer", lambda *a, **k: TracerProvider().get_tracer("test")
    )
    settings.OBSERVABILITY_BACKEND = "phoenix"
    settings.PHOENIX_COLLECTOR_ENDPOINT = "http://collector.invalid:6006/v1/traces"
    settings.OTEL_EXPORTER_OTLP_ENDPOINT = ""
    settings.PHOENIX_UI_URL = "http://ui.invalid:6006/"
    settings.PHOENIX_PROJECT_NAME = "law_ai_test"

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post("/api/lsat/tutor", json={"question_id": qid})
    assert res.status_code == 200
    body = res.json()
    trace_id = body["trace_id"]
    assert isinstance(trace_id, str) and len(trace_id) == 32
    assert body["phoenix_trace_url"] == (
        f"http://ui.invalid:6006/projects/law_ai_test/traces/{trace_id}"
    )


@pytest.mark.asyncio
async def test_tutor_links_its_trace_when_a_viewer_is_configured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.trace import TracerProvider

    from law_ai.core import telemetry

    # A real SDK provider, so the span this asks for has a valid context; no
    # exporter, so nothing leaves the process.
    monkeypatch.setattr(
        otel_trace, "get_tracer", lambda *a, **k: TracerProvider().get_tracer("test")
    )
    monkeypatch.setattr(telemetry, "trace_url", lambda tid: f"https://ui/t/{tid}")
    from law_ai.lsat.services import tutor as tutor_mod

    monkeypatch.setattr(
        tutor_mod, "_phoenix_trace_url", lambda tid: f"https://ui/t/{tid}"
    )

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post("/api/lsat/tutor", json={"question_id": qid})
    body = res.json()
    assert body["trace_id"] is not None
    assert len(body["trace_id"]) == 32
    assert body["phoenix_trace_url"] == f"https://ui/t/{body['trace_id']}"


@pytest.mark.asyncio
async def test_tutor_audit_event_carries_the_trace_id(
    client: AsyncClient,
) -> None:
    from law_ai.core import audit_jsonl as audit_store

    bank = load_bank()
    qid = next(iter(bank))
    await client.post("/api/lsat/tutor", json={"question_id": qid})
    event = next(e for e in audit_store.tail(50) if e.get("type") == "lsat_tutor")
    # Present as a key whether or not telemetry produced one, so the ops
    # dashboard can join on it without guessing.
    assert "trace_id" in event


@pytest.mark.asyncio
async def test_passages_filter_by_concept_without_a_sample_cap(
    client: AsyncClient,
) -> None:
    """BL-20260906-74: "which sets carry this concept?" answered in full.

    The panel used to read passage_ids off ``/questions?concept=…&limit=25``.
    That endpoint caps at 25 and — with no ``passage_id`` — samples the pool
    at random above it, so a concept tagged on more questions than the cap
    would drop sets from the filter, and drop different ones each call. This
    projection is passage-shaped, so there is nothing to cap: every passage
    with a tagged question is returned, and nothing else.
    """
    bank = load_bank()
    tagged = {
        concept: {
            q.passage_id
            for q in bank.values()
            if q.passage_id and concept in q.concepts
        }
        for concept in load_concepts()
    }
    concept, expected = max(tagged.items(), key=lambda kv: len(kv[1]))
    assert expected, "no concept is tagged on a passage-backed question"

    res = await client.get("/api/lsat/passages", params={"concept": concept})
    assert res.status_code == 200
    body = res.json()
    assert {p["id"] for p in body["passages"]} == expected
    assert body["count"] == len(expected)

    # Still composable with the section filter, and never widened by it.
    section = next(iter({p["section"] for p in body["passages"]}))
    scoped = await client.get(
        "/api/lsat/passages", params={"concept": concept, "section": section}
    )
    assert {p["id"] for p in scoped.json()["passages"]} <= expected

    # An unknown concept is an empty answer, not the whole section.
    none = await client.get("/api/lsat/passages", params={"concept": "no-such-concept"})
    assert none.json() == {"passages": [], "count": 0}
