"""Tests for LegalAnalyst, including the dev-time Claude Code IRAC path."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest


def _irac_payload(confidence: float = 0.85) -> str:
    return json.dumps(
        {
            "issue": "Whether a clickwrap arbitration clause is enforceable.",
            "rule": "Clickwrap terms bind a user given reasonable notice and assent.",
            "application": "Here, the terms were linked beside the sign-up button…",
            "conclusion": "Likely enforceable if notice was reasonably conspicuous.",
            "key_authorities": ["Specht v. Netscape", "Meyer v. Uber"],
            "confidence": confidence,
        }
    )


class TestDefaultPath:
    @pytest.mark.asyncio
    async def test_returns_mock_without_calling_claude(self) -> None:
        from lawgraph.agents_runtime.crews import legal_analyst as mod

        agent = mod.LegalAnalyst()
        with (
            patch.object(mod.claude_code, "is_active", return_value=False),
            patch.object(mod.claude_code, "generate", new=AsyncMock()) as gen,
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            out = await agent.run({"question": "x"})
        assert gen.await_count == 0  # default path must not touch Claude Code
        assert out.issue  # static mock IRAC still populated


class TestViaClaudeCode:
    @pytest.mark.asyncio
    async def test_routes_to_claude_code_when_active(self) -> None:
        from lawgraph.agents_runtime.crews import legal_analyst as mod

        agent = mod.LegalAnalyst()
        with (
            patch.object(mod.claude_code, "is_active", return_value=True),
            patch.object(mod.claude_code, "model", return_value="claude-opus-4-8"),
            patch.object(
                mod.claude_code, "generate", new=AsyncMock(return_value=_irac_payload())
            ),
            patch.object(
                mod.provenance, "log_agent_call", return_value="trace-cc"
            ) as log,
        ):
            out = await agent.run({"question": "Is a clickwrap clause enforceable?"})
        assert "clickwrap" in out.issue.lower()
        assert [s["title"] for s in out.sources] == [
            "Specht v. Netscape",
            "Meyer v. Uber",
        ]
        assert out.confidence == 0.85
        assert out.trace_id == "trace-cc"
        assert log.call_args.kwargs["model"] == "claude_code/claude-opus-4-8"

    @pytest.mark.asyncio
    async def test_clamps_out_of_range_confidence(self) -> None:
        from lawgraph.agents_runtime.crews import legal_analyst as mod

        agent = mod.LegalAnalyst()
        with (
            patch.object(mod.claude_code, "is_active", return_value=True),
            patch.object(mod.claude_code, "model", return_value="claude-opus-4-8"),
            patch.object(
                mod.claude_code,
                "generate",
                new=AsyncMock(return_value=_irac_payload(confidence=9.0)),
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            out = await agent.run({"question": "x"})
        assert out.confidence == 1.0

    @pytest.mark.asyncio
    async def test_degrades_to_offline_on_provider_error(self) -> None:
        import httpx

        from lawgraph.agents_runtime.crews import legal_analyst as mod

        agent = mod.LegalAnalyst()
        boom = AsyncMock(side_effect=httpx.ConnectError("overloaded"))
        with (
            patch.object(mod.claude_code, "is_active", return_value=True),
            patch.object(mod.claude_code, "generate", new=boom),
            patch.object(mod.provenance, "log_agent_call", return_value="t") as log,
        ):
            out = await agent.run({"question": "Is X liable?"})
        assert out.confidence == 0.0
        assert "OFFLINE FALLBACK" in out.rule
        assert log.call_args.kwargs["model"] == "fallback/offline"
