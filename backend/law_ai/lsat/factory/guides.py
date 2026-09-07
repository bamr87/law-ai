"""Guide-at-authoring — draft a solve guide beside each drafted item.

BL-20260901-04. Guide coverage kept falling behind the bank (40 guides against
148 questions after spec 047 slice 2) because guides were only ever written by
a later sweep: every batch of new questions widened the gap that
``lsat_guide_backfill`` then had to close. Authoring the guide *with* the item
stops the gap from opening in the first place — the reviewer sees the question
and its walkthrough in the same queue, judged together.

Deliberate limits:

* **Both stay pending.** The guide is recorded as a ``proposal_kind="guide"``
  draft linked to its question proposal (``meta.guide_for_proposal``); neither
  reaches learners without a reviewer (constitution §5). When the question is
  approved, :func:`law_ai.lsat.services.proposals.promote_to_bank` relinks the
  guide draft onto the real question id.
* **Degraded drafts are dropped**, exactly as the backfill command does: an
  offline-fallback guide carries no content and would only clutter the queue.
* **Never fatal, and skippable.** ``FactoryConfig.guides_enabled`` /
  ``--no-guides`` turns it off for budget control, and any failure is a
  warning on the ingest result, not an aborted run.
"""

from __future__ import annotations

import logging
from typing import Any

from law_ai.agents_runtime.crews.lsat_solve_guide_author import LSATSolveGuideAuthor
from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.intake import IngestResult
from law_ai.lsat.services.proposals import (
    get_proposal,
    list_proposals,
    record_proposal,
)

logger = logging.getLogger("law_ai.lsat.factory.guides")

#: Key under a guide proposal's ``meta`` naming the question proposal it was
#: written for. The backfill sweep and this path both read it, so a question
#: never gets two guides queued at once.
LINK_KEY = "guide_for_proposal"


def _already_queued() -> set[str]:
    """Question-proposal ids that already have a pending guide draft."""
    queued: set[str] = set()
    for row in list_proposals("pending", limit=1000):
        if row.get("proposal_kind") != "guide":
            continue
        parent = (row.get("meta") or {}).get(LINK_KEY)
        if isinstance(parent, str):
            queued.add(parent)
    return queued


async def draft_guides(result: IngestResult, *, config: FactoryConfig) -> IngestResult:
    """Draft one solve guide per accepted question draft, in place.

    Returns the same :class:`IngestResult` with ``guides`` populated
    (question proposal id → guide proposal id).
    """
    if not config.guides_enabled or not result.accepted:
        return result
    author = LSATSolveGuideAuthor()
    queued = _already_queued()
    for proposal_id in result.accepted:
        if proposal_id in queued:
            continue
        row = get_proposal(proposal_id)
        draft = (row or {}).get("draft")
        if not isinstance(draft, dict):  # pragma: no cover - defensive
            result.warnings.append(f"guide skipped {proposal_id}: no draft row")
            continue
        try:
            output = await author.run({"question_id": proposal_id, "question": draft})
        except Exception as exc:  # pragma: no cover - the agent degrades itself
            logger.warning("guide draft failed for %s: %s", proposal_id, exc)
            result.warnings.append(f"guide draft failed for {proposal_id}: {exc}"[:300])
            continue
        if output.degraded:
            result.warnings.append(
                f"guide skipped for {proposal_id}: no provider answered"
            )
            continue
        meta: dict[str, Any] = {LINK_KEY: proposal_id}
        factory_meta = ((row or {}).get("meta") or {}).get("factory")
        if isinstance(factory_meta, dict):
            meta["factory"] = dict(factory_meta)
        guide_id = record_proposal(
            output.guide.model_dump(by_alias=True),
            agent_trace_id=output.trace_id or "",
            model=output.model,
            confidence=output.confidence,
            meta=meta,
            proposal_kind="guide",
        )
        result.guides[proposal_id] = guide_id
    return result
