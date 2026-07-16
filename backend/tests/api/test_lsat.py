"""Tests for /api/lsat/* (spec 005)."""

from __future__ import annotations

from pathlib import Path

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
from law_ai.asgi import application as app


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


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
async def test_concepts_unknown_returns_404(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/concepts/does-not-exist")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_tutor_falls_back_when_ollama_unreachable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tutor never hard-fails when Ollama is offline (constitution §1)."""
    import httpx

    from law_ai.lsat.services import tutor as tutor_mod

    async def boom(prompt: str, *, model: str) -> str:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(tutor_mod, "_ollama_generate", boom)

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
    """When Ollama returns a parseable payload, it surfaces in the response."""
    from law_ai.lsat.services import tutor as tutor_mod

    async def fake_generate(prompt: str, *, model: str) -> str:
        return (
            '{"coaching": "Walkthrough: think contrapositive then re-check.", '
            '"next_steps": ["Diagram conditionals", "Review modus tollens"]}'
        )

    monkeypatch.setattr(tutor_mod, "_ollama_generate", fake_generate)

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
    assert body["model"] == settings.OLLAMA_DEFAULT_MODEL


@pytest.mark.asyncio
async def test_tutor_routes_to_claude_code_when_active(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dev-time opt-in: when Claude Code is active the tutor uses it, not Ollama."""
    from law_ai.core import claude_code as cc_mod

    async def fake_generate(prompt: str, *, system: str | None = None) -> str:
        return (
            '{"coaching": "Claude Code walkthrough of the contrapositive.", '
            '"next_steps": ["Diagram conditionals", "Recheck modus tollens"]}'
        )

    # Force the dev-only gate on without depending on the test environment.
    monkeypatch.setattr(cc_mod, "is_active", lambda: True)
    monkeypatch.setattr(cc_mod, "generate", fake_generate)
    monkeypatch.setattr(cc_mod, "model", lambda: "claude-opus-4-8")

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post(
        "/api/lsat/tutor", json={"question_id": qid, "user_question": "Why is C wrong?"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["used_llm"] is True
    assert body["model"] == "claude_code/claude-opus-4-8"
    assert "Claude Code walkthrough" in body["coaching"]
    assert len(body["next_steps"]) == 2


@pytest.mark.asyncio
async def test_tutor_claude_code_strips_markdown_fence(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fenced ```json block from Claude still parses into structured coaching."""
    from law_ai.core import claude_code as cc_mod

    async def fenced(prompt: str, *, system: str | None = None) -> str:
        return (
            "```json\n"
            '{"coaching": "Fenced but valid.", "next_steps": ["Step one"]}\n'
            "```"
        )

    monkeypatch.setattr(cc_mod, "is_active", lambda: True)
    monkeypatch.setattr(cc_mod, "generate", fenced)

    bank = load_bank()
    qid = next(iter(bank))
    res = await client.post("/api/lsat/tutor", json={"question_id": qid})
    assert res.status_code == 200
    body = res.json()
    assert body["used_llm"] is True
    assert body["coaching"] == "Fenced but valid."
    assert body["next_steps"] == ["Step one"]


@pytest.mark.asyncio
async def test_tutor_falls_back_when_claude_code_errors(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Claude Code transport failure degrades to the offline path, never 500s."""
    import httpx

    from law_ai.core import claude_code as cc_mod

    async def boom(prompt: str, *, system: str | None = None) -> str:
        raise httpx.ConnectError("oauth endpoint unreachable")

    monkeypatch.setattr(cc_mod, "is_active", lambda: True)
    monkeypatch.setattr(cc_mod, "generate", boom)

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
