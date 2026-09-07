"""Intake gates for drafted writing prompts (BL-20260831-28).

The MCQ gates in :mod:`law_ai.lsat.factory.intake` assume a keyed item: five
choices, one credited answer, a stem to dedup on. A writing task has none of
those — it is an issue, two or more positions, stated perspectives, and an
annotated model essay — so it gets its own three gates:

1. **schema** — :class:`~law_ai.lsat.services.writing.WritingPrompt`
   validation, with the platform-owned fields (id, rubric, difficulty, source)
   injected rather than trusted from the model;
2. **lint** — concept tags exist in the catalog, and every ``criterion_id`` in
   the self-checks and the model-response annotations names a criterion the
   rubric actually defines (the same cross-reference the store enforces at
   load time, applied before the draft is queued rather than after);
3. **dedup** — token-Jaccard of the *issue* against the live library, so the
   loop does not re-author a debate it already has.

Survivors land in the HITL queue as ``proposal_kind="writing_prompt"``. Model
essays are the costly, quality-sensitive part of writing content, so nothing
here writes to the library: promotion is a reviewer's decision through
:func:`law_ai.lsat.services.proposals.promote_writing_prompt` (NFR-PROV-1).
"""

from __future__ import annotations

import logging
from typing import Any

from law_ai.core.provenance import provenance
from law_ai.lsat.factory.blueprints import DEFAULT_RUBRIC_ID
from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.intake import (
    AGENT_NAME,
    GateRejection,
    IngestResult,
    _jaccard,
    _tokens,
)
from law_ai.lsat.factory.manifest import GenerationJob
from law_ai.lsat.services.bank import load_concepts
from law_ai.lsat.services.proposals import record_proposal
from law_ai.lsat.services.writing import (
    WritingPrompt,
    load_writing_prompts,
    load_writing_rubrics,
)

logger = logging.getLogger("law_ai.lsat.factory.writing_intake")

#: Placeholder id a draft carries until a reviewer promotes it; the library
#: assigns the real ``ws-NNN`` at promotion.
DRAFT_ID = "ws-draft"


def _rubric_criteria(rubric_id: str) -> set[str]:
    rubric = load_writing_rubrics().get(rubric_id)
    return {c.id for c in rubric.criteria} if rubric else set()


def _lint(prompt: WritingPrompt, catalog: set[str], criteria: set[str]) -> str | None:
    """Concept + rubric cross-reference check; returns a detail or None."""
    unknown = [c for c in prompt.concepts if c not in catalog]
    if unknown:
        return f"unknown concept id(s): {unknown}"
    if not criteria:  # pragma: no cover - the library ships a rubric
        return None
    referenced = {c.criterion_id for c in prompt.self_check} | {
        a.criterion_id for a in prompt.model_response.annotations
    }
    bad = sorted(referenced - criteria)
    if bad:
        return f"unknown rubric criterion id(s): {bad}"
    return None


def _closest_issue(issue: str) -> tuple[str, float]:
    """Nearest existing prompt by issue-token Jaccard."""
    tokens = _tokens(issue)
    best_id, best_score = "", 0.0
    for existing in load_writing_prompts().values():
        score = _jaccard(tokens, _tokens(existing.issue))
        if score > best_score:
            best_id, best_score = existing.id, score
    return best_id, best_score


def _gate(
    raw: Any,
    index: int,
    *,
    job: GenerationJob,
    catalog: set[str],
    criteria: set[str],
    config: FactoryConfig,
    seen_issues: list[str],
) -> tuple[WritingPrompt | None, GateRejection | None]:
    if not isinstance(raw, dict):
        return None, GateRejection(
            draft_index=index, reason="schema", detail="draft is not an object"
        )
    data = dict(raw)
    # Platform-owned fields — never trusted from the model.
    data["id"] = DRAFT_ID
    data["rubric_id"] = DEFAULT_RUBRIC_ID
    data["difficulty"] = job.target.difficulty
    data["source"] = "LSATContentFactory (draft)"
    try:
        prompt = WritingPrompt.model_validate(data)
    except Exception as exc:
        return None, GateRejection(
            draft_index=index, reason="schema", detail=str(exc)[:300]
        )

    detail = _lint(prompt, catalog, criteria)
    if detail is not None:
        return None, GateRejection(draft_index=index, reason="concept", detail=detail)

    closest_id, score = _closest_issue(prompt.issue)
    for other in seen_issues:
        intra = _jaccard(_tokens(prompt.issue), _tokens(other))
        if intra > score:
            closest_id, score = f"{job.job_id}#batch", intra
    if score >= config.dedup_threshold:
        return None, GateRejection(
            draft_index=index,
            reason="duplicate",
            detail=f"issue ~{score:.2f} similar to {closest_id}",
        )
    return prompt, None


def ingest_writing_batch(
    payload: dict[str, Any],
    *,
    job: GenerationJob,
    config: FactoryConfig,
    executor_name: str,
    model_label: str,
    latency_ms: float = 0.0,
) -> IngestResult:
    """Gate one writing job's payload and queue the survivors for review."""
    catalog = set(load_concepts().keys())
    criteria = _rubric_criteria(DEFAULT_RUBRIC_ID)
    accepted: list[WritingPrompt] = []
    rejected: list[GateRejection] = []
    seen_issues: list[str] = []

    raw_drafts = payload.get("drafts") or []
    for index, raw in enumerate(raw_drafts):
        prompt, rejection = _gate(
            raw,
            index,
            job=job,
            catalog=catalog,
            criteria=criteria,
            config=config,
            seen_issues=seen_issues,
        )
        if rejection is not None or prompt is None:
            rejected.append(
                rejection
                or GateRejection(
                    draft_index=index, reason="schema", detail="gate returned nothing"
                )
            )
            continue
        seen_issues.append(prompt.issue)
        accepted.append(prompt)

    trace_id = provenance.log_agent_call(
        agent_name=AGENT_NAME,
        input_data={
            "manifest_id": job.job_id.rsplit("-job", 1)[0],
            "job_id": job.job_id,
            "archetype_id": job.target.archetype_id,
            "section": "WS",
            "difficulty": job.target.difficulty,
            "tier": job.tier,
            "executor": executor_name,
            "mode": "writing_prompt",
        },
        output_data={
            "drafts_in": len(raw_drafts),
            "accepted": len(accepted),
            "rejected": len(rejected),
        },
        model=model_label,
        latency_ms=latency_ms,
        confidence=0.0,
        sources=[],
    )

    accepted_ids: list[str] = []
    for prompt in accepted:
        meta: dict[str, Any] = {
            "factory": {
                "manifest_id": job.job_id.rsplit("-job", 1)[0],
                "job_id": job.job_id,
                "archetype_id": job.target.archetype_id,
                "tier": job.tier,
                "executor": executor_name,
                "template_version": job.template_version,
                "mode": "writing_prompt",
            }
        }
        accepted_ids.append(
            record_proposal(
                prompt.model_dump(),
                agent_trace_id=trace_id or "",
                model=model_label,
                confidence=0.0,
                source_concept_ids=job.target.concepts,
                meta=meta,
                proposal_kind="writing_prompt",
            )
        )

    if rejected:
        logger.info(
            "factory writing intake %s: accepted %d, rejected %d (%s)",
            job.job_id,
            len(accepted_ids),
            len(rejected),
            ", ".join(f"#{r.draft_index}:{r.reason}" for r in rejected),
        )

    return IngestResult(
        job_id=job.job_id,
        accepted=accepted_ids,
        rejected=rejected,
        trace_id=trace_id,
        model_label=model_label,
    )
