"""``validate_claude_code`` — verify the Claude OAuth tier of the runtime chain.

Proves the application can talk to Anthropic over a Claude subscription OAuth
token (tier 1 of ``LLM_PROVIDER_CHAIN``, constitution §1 as amended) and that
the LSAT tutor actually routes through it end-to-end. Run inside the backend
container::

    make validate-claude-code
    # or: make manage CMD='validate_claude_code'
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError

from law_ai.core import claude_code


class Command(BaseCommand):
    help = "Validate the Claude OAuth tier of the LLM provider chain end-to-end."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--question-id",
            default=None,
            help="LSAT bank question id for the end-to-end tutor check "
            "(defaults to the first question in the bank).",
        )
        parser.add_argument(
            "--skip-tutor",
            action="store_true",
            help="Only run the OAuth reachability probe; skip the tutor round-trip.",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        self._print_gate()

        probe = async_to_sync(claude_code.probe)()
        self._print_probe(probe)
        if not probe.get("reachable"):
            raise CommandError(
                "Claude Code OAuth probe failed: "
                + str(probe.get("error") or probe.get("reason") or "unreachable")
            )

        if opts["skip_tutor"]:
            self.stdout.write(self.style.SUCCESS("\nOAuth connection validated."))
            return

        self._run_tutor(opts["question_id"])

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------
    def _print_gate(self) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("Claude OAuth tier (chain tier 1)"))
        rows = {
            "development env": claude_code.is_development(),
            "oauth token": claude_code.oauth_token() is not None,
            "api key (tier 2)": claude_code.api_key() is not None,
            "model": claude_code.model(),
        }
        for key, value in rows.items():
            self.stdout.write(f"  {key:<18}: {value}")
        reason = claude_code.inactive_reason()
        if reason:
            self.stdout.write(self.style.WARNING(f"  (inactive: {reason})"))

    def _print_probe(self, probe: dict[str, Any]) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("\nOAuth reachability probe"))
        status = (
            self.style.SUCCESS("reachable")
            if probe.get("reachable")
            else self.style.ERROR("unreachable")
        )
        self.stdout.write(f"  status            : {status}")
        if probe.get("sample"):
            self.stdout.write(f"  sample            : {probe['sample']!r}")
        if probe.get("error"):
            self.stdout.write(
                self.style.ERROR(f"  error             : {probe['error']}")
            )
        if probe.get("reason"):
            self.stdout.write(f"  reason            : {probe['reason']}")

    def _run_tutor(self, question_id: str | None) -> None:
        from law_ai.lsat.services.bank import load_bank
        from law_ai.lsat.services.tutor import TutorRequest, tutor

        bank = load_bank()
        if not bank:
            raise CommandError("LSAT bank is empty; cannot run the tutor check.")
        if question_id is None:
            question_id = next(iter(bank))
        question = bank.get(question_id)
        if question is None:
            raise CommandError(f"question id not found in bank: {question_id}")

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nEnd-to-end LSAT tutor via Claude Code (question {question_id})"
            )
        )
        req = TutorRequest(question_id=question_id, user_choice=question.correct)
        resp = async_to_sync(tutor)(req, question)

        self.stdout.write(f"  used_llm          : {resp.used_llm}")
        self.stdout.write(f"  model             : {resp.model}")
        self.stdout.write(f"  confidence        : {resp.confidence}")
        self.stdout.write(f"  coaching          : {resp.coaching[:200]}")

        if not resp.used_llm or not resp.model.startswith(claude_code.PROVIDER_NAME):
            raise CommandError(
                "Tutor did not produce coaching via Claude Code "
                f"(used_llm={resp.used_llm}, model={resp.model})."
            )
        self.stdout.write(
            self.style.SUCCESS("\nClaude Code OAuth integration validated end-to-end.")
        )
