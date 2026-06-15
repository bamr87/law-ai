"""``run_lsat_author`` — run the LSATContentAuthor agent live.

Drafts an LSAT question end-to-end (prompt → LLM → parse → Pydantic validate →
provenance) and prints the result. When the dev-time Claude Code OAuth provider
is opted in (``LSAT_LLM_PROVIDER=claude_code`` + token, in development) the agent
runs against your Claude Code subscription; otherwise it uses Ollama, and falls
back to a deterministic offline draft if neither is reachable.

    make lsat-author-demo
    # or: make manage CMD='run_lsat_author --section RC --difficulty hard'
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand

from lawgraph.core import claude_code


class Command(BaseCommand):
    help = "Run the LSATContentAuthor agent once and print the drafted question(s)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--section", default="LR", help="LR | RC | LG")
        parser.add_argument("--difficulty", default="med", help="easy | med | hard")
        parser.add_argument("--count", type=int, default=1, help="how many to draft")
        parser.add_argument(
            "--concepts",
            default="",
            help="comma-separated concept ids to target (optional).",
        )
        parser.add_argument("--passage-id", default=None, help="optional passage id")

    def handle(self, *args: Any, **opts: Any) -> None:
        from lawgraph.agents_runtime.crews.lsat_content_author import (
            GenerateQuestionsInput,
            LSATContentAuthor,
        )

        self._print_gate()

        concepts = [c.strip() for c in str(opts["concepts"]).split(",") if c.strip()]
        payload = GenerateQuestionsInput(
            section=opts["section"],
            difficulty=opts["difficulty"],
            count=opts["count"],
            concepts=concepts,
            passage_id=opts["passage_id"],
        )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nRunning LSATContentAuthor "
                f"(section={payload.section}, difficulty={payload.difficulty}, "
                f"count={payload.count})…"
            )
        )
        agent = LSATContentAuthor()
        output = async_to_sync(agent.run)(payload.model_dump())

        ran_on_claude = output.model.startswith(claude_code.PROVIDER_NAME)
        banner = (
            self.style.SUCCESS("via Claude Code")
            if ran_on_claude
            else self.style.WARNING(f"via {output.model}")
        )
        self.stdout.write(f"\nResult ({banner}):")
        self.stdout.write(f"  model      : {output.model}")
        self.stdout.write(f"  degraded   : {output.degraded}")
        self.stdout.write(f"  confidence : {output.confidence}")
        self.stdout.write(f"  latency_ms : {output.latency_ms}")
        self.stdout.write(f"  trace_id   : {output.trace_id}")

        for i, draft in enumerate(output.drafts, 1):
            self.stdout.write(self.style.MIGRATE_HEADING(f"\nDraft {i}"))
            self.stdout.write(f"  stem        : {draft.stem}")
            for choice in draft.choices:
                marker = "✓" if choice.label == draft.correct else " "
                self.stdout.write(f"    {marker} {choice.label}. {choice.text}")
            self.stdout.write(f"  correct     : {draft.correct}")
            self.stdout.write(f"  explanation : {draft.explanation}")
            self.stdout.write(f"  concepts    : {', '.join(draft.concepts) or '—'}")
            self.stdout.write(f"  confidence  : {draft.confidence}")

        if output.degraded:
            self.stdout.write(
                self.style.WARNING(
                    "\nAgent ran in DEGRADED mode (no LLM reachable) — drafts are "
                    "deterministic placeholders. Check the provider gate above."
                )
            )
        elif ran_on_claude:
            self.stdout.write(
                self.style.SUCCESS(
                    "\nLive agent run via Claude Code completed (provenance logged)."
                )
            )

    def _print_gate(self) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("Claude Code OAuth gate"))
        rows = {
            "provider selected": claude_code.is_selected(),
            "development env": claude_code.is_development(),
            "token present": claude_code.oauth_token() is not None,
            "agent active": claude_code.is_active(),
            "model": claude_code.model(),
        }
        for key, value in rows.items():
            self.stdout.write(f"  {key:<18}: {value}")
        reason = claude_code.inactive_reason()
        if reason:
            self.stdout.write(self.style.WARNING(f"  (inactive: {reason})"))
