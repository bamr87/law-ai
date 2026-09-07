"""Judge tier — adversarial review of accepted drafts before the HITL queue.

BL-20260702-02. Spec 024 defined a ``judge`` model tier and routed nothing to
it: :mod:`law_ai.lsat.factory.config` mapped the tier onto a model and the
pipeline went executor → intake → proposals with no review step. This module
is that step. After a batch's survivors are recorded as ``pending``, each one
is handed to :class:`~law_ai.agents_runtime.crews.lsat_draft_judge.LSATDraftJudge`
and the verdict is attached to the proposal's ``meta.factory.judge`` block.

Three deliberate limits:

* **Advisory.** A verdict never promotes, rejects, or reorders a proposal —
  it is metadata a human reviewer reads. The HITL gate stays where it is
  (constitution §5); auto-promotion on ``pass`` is spec 047 FR-20's decision.
* **Off by default.** ``FactoryConfig.judge_enabled`` (``--judge`` on
  ``lsat_factory run``) gates it, because judging doubles the model calls per
  batch.
* **Never fatal.** A judge that degrades or raises leaves the batch alone; the
  run reports it and finishes.
"""

from __future__ import annotations

import logging
from typing import Any

from law_ai.agents_runtime.crews.lsat_draft_judge import LSATDraftJudge
from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.intake import IngestResult
from law_ai.lsat.services.proposals import get_proposal, record_judge_verdict

logger = logging.getLogger("law_ai.lsat.factory.judge")


async def judge_result(
    result: IngestResult,
    *,
    config: FactoryConfig,
    tier_model_hint: str | None = None,
) -> IngestResult:
    """Review every draft *result* accepted and attach the verdicts in place.

    Returns the same :class:`IngestResult` with ``judge`` populated
    (proposal id → verdict word). A failure to review one draft is recorded as
    a warning, not an exception: the proposals are already queued and a
    missing verdict simply means a reviewer gets no hint.
    """
    if not config.judge_enabled or not result.accepted:
        return result
    judge = LSATDraftJudge()
    for proposal_id in result.accepted:
        row = get_proposal(proposal_id)
        draft = (row or {}).get("draft")
        if not isinstance(draft, dict):  # pragma: no cover - defensive
            result.warnings.append(f"judge skipped {proposal_id}: no draft row")
            continue
        try:
            output = await judge.run(
                {
                    "draft": draft,
                    "passage_id": draft.get("passage_id"),
                    "proposal_id": proposal_id,
                }
            )
        except Exception as exc:  # pragma: no cover - the agent degrades itself
            logger.warning("judge failed for %s: %s", proposal_id, exc)
            result.warnings.append(f"judge failed for {proposal_id}: {exc}"[:300])
            continue
        payload: dict[str, Any] = output.verdict.model_dump()
        payload["trace_id"] = output.trace_id
        payload["tier_model_hint"] = tier_model_hint
        record_judge_verdict(proposal_id, payload)
        result.judge[proposal_id] = output.verdict.verdict
        if output.degraded:
            result.warnings.append(
                f"judge degraded for {proposal_id}: no provider answered"
            )
    return result
