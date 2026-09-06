"""LLM-judged §13 attribution over IRAC *prose* (BL-20260905-85).

``tests/agents/test_attribution_rule.py`` enforces the half of constitution
§13 that a machine can check without a model: every citation an agent emits
carries court + jurisdiction + decided_at + binding/persuasive, or the run is
pinned for review. That gate is **per citation**, so it says nothing about the
sentence that states law and names no authority at all — an
``IRACOutput.application`` paragraph can assert a rule outright, cite nothing
for it, and still pass every deterministic check because the citations it
*did* emit were well attributed.

Judging prose needs a reader, so this module asks one. The judge is the same
local Ollama model the LegalBench harness measures against — pinned there, not
routed through ``LLM_PROVIDER_CHAIN``, for the reason spec 034 gives: a silent
fallback to another provider changes what is being measured. Hence the
``legalbench`` marker, which ``make test-backend`` excludes.

Run it with the local stack up::

    make local-ai-up
    docker compose run --rm -e ATTRIBUTION_JUDGE=1 backend \\
        pytest tests/agents/test_attribution_prose_judge.py -m legalbench -q --no-cov

Override ``ATTRIBUTION_JUDGE_BASE_URL`` / ``ATTRIBUTION_JUDGE_MODEL`` to judge
with something other than the default local endpoint and model.

The two helpers below (prompt construction and verdict parsing) are covered by
ordinary unit tests, so a broken judge harness is caught in the default suite
even though the judgement itself is opt-in.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import pytest

#: Opt-in switch. The marker already keeps this out of `make test-backend`;
#: the env gate keeps it out of an ad-hoc `pytest -m ""` sweep on a machine
#: with no model pulled, where it would fail for the wrong reason.
JUDGE_ENABLED = bool(os.getenv("ATTRIBUTION_JUDGE"))
#: Where the judge lives, and which model plays it. `settings.test` blanks
#: every LLM endpoint on purpose, so these are read from the environment.
JUDGE_BASE_URL = os.getenv("ATTRIBUTION_JUDGE_BASE_URL", "http://ollama:11434")
JUDGE_MODEL = os.getenv("ATTRIBUTION_JUDGE_MODEL", "mistral:7b-instruct-q4_K_M")

_JUDGE_INSTRUCTIONS = """\
You are auditing a legal analysis for attribution, not for correctness.

A STATEMENT OF LAW is a sentence asserting what the law requires, permits or
forbids. It is ATTRIBUTED when the sentence names an authority that appears in
the citation list below (by case name, statute citation, or ordinance
citation). Applying law to the facts of this dispute is not a statement of law.

Citations available to this analysis:
{citations}

Analysis paragraph:
{application}

Reply with JSON only, no prose around it:
{{"verdict": "pass" or "fail", "unattributed": ["<verbatim sentence>", ...]}}

"fail" means at least one statement of law names no authority from the list.
"""


def judge_prompt(application: str, citations: list[str]) -> str:
    """Build the judge prompt for one ``IRACOutput.application`` paragraph."""
    listed = "\n".join(f"- {c}" for c in citations) if citations else "- (none)"
    return _JUDGE_INSTRUCTIONS.format(citations=listed, application=application)


def parse_verdict(response: str) -> tuple[str, list[str]]:
    """Read ``(verdict, unattributed_sentences)`` out of a judge reply.

    A reply that cannot be parsed is ``("error", [])`` rather than a pass: an
    unreadable judge must never be scored as "the prose was fine" — that is
    the exact failure mode this test exists to rule out.
    """
    match = re.search(r"\{.*\}", response, re.DOTALL)
    if not match:
        return "error", []
    try:
        payload: Any = json.loads(match.group(0))
    except json.JSONDecodeError:
        return "error", []
    if not isinstance(payload, dict):
        return "error", []
    verdict = str(payload.get("verdict") or "").strip().lower()
    if verdict not in {"pass", "fail"}:
        return "error", []
    raw = payload.get("unattributed") or []
    sentences = [str(s) for s in raw] if isinstance(raw, list) else []
    return verdict, sentences


# --- the two fixtures the judge is asked to tell apart ----------------------

CITATIONS = [
    "C.R.S. § 38-12-103 (Colorado, statute)",
    "Martinez v. Steadman, us-co (2004-05-11, binding)",
]

ATTRIBUTED_APPLICATION = (
    "Under C.R.S. § 38-12-103 a landlord must return a security deposit "
    "within one month of the end of the tenancy. Martinez v. Steadman holds "
    "that the month runs from surrender of the keys, not from the lease's "
    "nominal end date. Here the tenant surrendered the keys on 1 March and "
    "the landlord returned nothing by 1 April, so the deadline passed."
)

UNATTRIBUTED_APPLICATION = (
    "A landlord who wilfully retains a deposit owes the tenant treble "
    "damages and attorney fees. Here the landlord returned nothing by "
    "1 April, so the tenant may recover three times the withheld amount."
)


class TestJudgeHarness:
    """Default-suite coverage for the harness, not for the judgement."""

    def test_prompt_carries_the_paragraph_and_every_citation(self) -> None:
        prompt = judge_prompt(ATTRIBUTED_APPLICATION, CITATIONS)
        assert ATTRIBUTED_APPLICATION in prompt
        for citation in CITATIONS:
            assert citation in prompt

    def test_prompt_says_none_rather_than_leaving_a_blank(self) -> None:
        """An empty citation list is a fact for the judge, not an empty gap."""
        assert "- (none)" in judge_prompt(UNATTRIBUTED_APPLICATION, [])

    def test_reads_a_fail_and_its_sentences(self) -> None:
        verdict, sentences = parse_verdict(
            'Here you go: {"verdict": "fail", "unattributed": ["A landlord ..."]}'
        )
        assert verdict == "fail"
        assert sentences == ["A landlord ..."]

    def test_reads_a_pass(self) -> None:
        assert parse_verdict('{"verdict": "pass", "unattributed": []}') == ("pass", [])

    @pytest.mark.parametrize(
        "reply",
        [
            "the paragraph looks fine to me",
            '{"verdict": "probably ok"}',
            "{not json at all}",
            '["fail"]',
        ],
    )
    def test_an_unreadable_judge_is_an_error_not_a_pass(self, reply: str) -> None:
        assert parse_verdict(reply) == ("error", [])


@pytest.mark.legalbench
@pytest.mark.skipif(
    not JUDGE_ENABLED,
    reason="ATTRIBUTION_JUDGE not set; LLM-judged attribution test is opt-in",
)
class TestProseAttributionJudged:
    """§13's prose half, judged by the pinned local model."""

    @staticmethod
    def _judge(application: str) -> tuple[str, list[str]]:
        # Endpoint and model come from the environment, not from settings:
        # `settings.test` deliberately points OLLAMA_BASE_URL at a closed port
        # so no test can reach a model by accident. Opting in therefore means
        # naming the endpoint too.
        from law_ai.eval.legalbench import _call_ollama

        response = _call_ollama(
            judge_prompt(application, CITATIONS),
            model=JUDGE_MODEL,
            base_url=JUDGE_BASE_URL,
        )
        return parse_verdict(response)

    def test_an_attributed_paragraph_passes(self) -> None:
        verdict, unattributed = self._judge(ATTRIBUTED_APPLICATION)
        assert verdict == "pass", f"judge flagged {unattributed!r}"

    def test_a_bare_statement_of_law_is_caught(self) -> None:
        """The case the deterministic per-citation gate cannot see.

        Every citation this analysis emits is fully attributed; the paragraph
        still asserts a treble-damages rule that no listed authority supports.
        """
        verdict, unattributed = self._judge(UNATTRIBUTED_APPLICATION)
        assert verdict == "fail", "judge missed an unattributed statement of law"
        assert unattributed, "a fail verdict must name the sentence it failed on"
