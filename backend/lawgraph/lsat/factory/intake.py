"""Intake pipeline — quality gates between raw generation and the HITL queue.

Spec 024 FR-7 / FR-9. Every raw batch passes four ordered gates:

1. **schema** — :class:`DraftQuestion` validation (the shared spec-019
   contract: exactly five A-E choices, length caps, key within A-E);
2. **concept lint** — every tag exists in the catalog, the section matches
   the target, and any referenced passage exists;
3. **dedup** — normalized token-Jaccard of the stem against the live bank,
   pending proposals, and earlier drafts in the same batch (spec 024 AC-3);
4. **balance** — batch answer-key skew detection: exceeding the tolerance
   *flags* every affected proposal rather than rejecting (spec 024 AC-4,
   resolving BL-20260606-02's check-at-intake requirement).

Survivors land in the spec-019 proposal store (``record_proposal``) with a
``meta`` block carrying the factory lineage (manifest, job, archetype, tier,
executor, gate stats), and each ingested batch logs exactly one provenance
event. Rejects never touch the store — they are returned to the caller with
machine-readable reasons (NFR-HITL-1: this module has no bank-write path).
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from lawgraph.agents_runtime.crews.lsat_content_author import DraftQuestion
from lawgraph.core.provenance import provenance
from lawgraph.lsat.factory.config import FactoryConfig
from lawgraph.lsat.factory.manifest import GenerationJob, drafts_dir
from lawgraph.lsat.services.bank import load_bank, load_concepts, load_passages
from lawgraph.lsat.services.proposals import list_proposals, record_proposal

logger = logging.getLogger("lawgraph.lsat.factory.intake")

AGENT_NAME = "LSATContentFactory"

RejectReason = Literal["schema", "concept", "section", "passage", "duplicate"]

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class GateRejection(BaseModel):
    """One draft that failed a gate, with a machine-readable reason."""

    draft_index: int
    reason: RejectReason
    detail: str


class IngestResult(BaseModel):
    """Outcome of ingesting one job's batch."""

    job_id: str
    accepted: list[str] = Field(
        default_factory=list, description="Proposal ids recorded as pending."
    )
    rejected: list[GateRejection] = Field(default_factory=list)
    balance_flag: str | None = Field(
        default=None,
        description="Set when the accepted batch's answer keys skew past "
        "tolerance; mirrored into each proposal's meta.",
    )
    pending_passage_path: str | None = Field(
        default=None,
        description="Where a passage_set job's new passage JSON was parked "
        "for reviewer wiring (promotion of passages is a follow-up).",
    )
    error: str | None = Field(
        default=None,
        description="Executor failure detail when the job produced no batch "
        "(truncated); None for jobs that reached the gates.",
    )
    trace_id: str | None = None
    model_label: str = "external"


def _tokens(text: str) -> frozenset[str]:
    return frozenset(_TOKEN_RE.findall(text.lower()))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _dedup_corpus() -> list[tuple[str, frozenset[str]]]:
    """(source id, stem token set) for the live bank + pending proposals."""
    corpus: list[tuple[str, frozenset[str]]] = [
        (q.id, _tokens(q.stem)) for q in load_bank().values()
    ]
    for row in list_proposals(status="pending", limit=500):
        draft = row.get("draft") or {}
        stem = str(draft.get("stem") or "")
        if stem:
            corpus.append((str(row.get("id")), _tokens(stem)))
    return corpus


def _closest(
    stem_tokens: frozenset[str], corpus: list[tuple[str, frozenset[str]]]
) -> tuple[str, float]:
    best_id, best_score = "", 0.0
    for source_id, tokens in corpus:
        score = _jaccard(stem_tokens, tokens)
        if score > best_score:
            best_id, best_score = source_id, score
    return best_id, best_score


def _park_pending_passage(
    payload: dict[str, Any], job: GenerationJob, config: FactoryConfig
) -> str | None:
    """Persist a passage_set job's new context for reviewer wiring (FR-7).

    Question promotion is handled by the spec-019 store; passage promotion is
    a recorded follow-up, so the passage JSON is parked as an artifact and the
    path is threaded into each proposal's meta — nothing is lost, and nothing
    reaches the live bank without a human.
    """
    passage = payload.get("passage")
    if not isinstance(passage, dict):
        return None
    park_dir = drafts_dir(config) / "pending_passages"
    park_dir.mkdir(parents=True, exist_ok=True)
    path = park_dir / f"{job.job_id}.passage.json"
    path.write_text(
        json.dumps(passage, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return str(path)


def _gate_draft(
    raw_item: Any,
    index: int,
    *,
    target: Any,
    catalog: set[str],
    passages: dict[str, Any],
    corpus: list[tuple[str, frozenset[str]]],
    config: FactoryConfig,
) -> tuple[DraftQuestion | None, GateRejection | None]:
    """Run gates 1-3 on one raw draft; returns exactly one of (draft, reject)."""
    if not isinstance(raw_item, dict):
        return None, GateRejection(
            draft_index=index, reason="schema", detail="draft is not an object"
        )
    data = dict(raw_item)
    data.setdefault("section", target.section)
    data.setdefault("difficulty", target.difficulty)
    # The platform owns passage linkage — never trust model-emitted ids.
    data.pop("passage_id", None)

    # Gate 1: schema (shared spec-019 contract).
    try:
        draft = DraftQuestion.model_validate(data)
    except Exception as exc:
        return None, GateRejection(
            draft_index=index, reason="schema", detail=str(exc)[:300]
        )

    # Gate 2: lint (section, concepts, passage linkage).
    linted, rejection = _lint_draft(
        draft, index, target=target, catalog=catalog, passages=passages
    )
    if rejection is not None or linted is None:
        return None, rejection
    draft = linted

    # Gate 3: near-duplicate detection (bank + pending + intra-batch).
    closest_id, score = _closest(_tokens(draft.stem), corpus)
    if score >= config.dedup_threshold:
        return None, GateRejection(
            draft_index=index,
            reason="duplicate",
            detail=f"stem ~{score:.2f} similar to {closest_id}",
        )
    return draft, None


def _lint_draft(
    draft: DraftQuestion,
    index: int,
    *,
    target: Any,
    catalog: set[str],
    passages: dict[str, Any],
) -> tuple[DraftQuestion | None, GateRejection | None]:
    """Gate 2: section consistency, concept validity, passage linkage."""
    if draft.section != target.section:
        return None, GateRejection(
            draft_index=index,
            reason="section",
            detail=f"draft section {draft.section!r} != target {target.section!r}",
        )

    unknown = [c for c in draft.concepts if c not in catalog]
    if unknown:
        return None, GateRejection(
            draft_index=index,
            reason="concept",
            detail=f"unknown concept id(s): {unknown}",
        )

    if target.mode == "items" and target.passage_id is not None:
        if target.passage_id not in passages:
            return None, GateRejection(
                draft_index=index,
                reason="passage",
                detail=f"target passage {target.passage_id!r} not found",
            )
        draft = draft.model_copy(update={"passage_id": target.passage_id})
    return draft, None


def ingest_batch(
    payload: dict[str, Any],
    *,
    job: GenerationJob,
    config: FactoryConfig,
    executor_name: str,
    model_label: str,
    latency_ms: float = 0.0,
) -> IngestResult:
    """Run one job's raw payload through the gates and record survivors."""
    target = job.target
    catalog = set(load_concepts().keys())
    passages = dict(load_passages())
    corpus = _dedup_corpus()
    accepted_drafts: list[DraftQuestion] = []
    rejected: list[GateRejection] = []

    raw_drafts = payload.get("drafts") or []
    for index, raw_item in enumerate(raw_drafts):
        draft, rejection = _gate_draft(
            raw_item,
            index,
            target=target,
            catalog=catalog,
            passages=passages,
            corpus=corpus,
            config=config,
        )
        if rejection is not None or draft is None:
            rejected.append(
                rejection
                or GateRejection(
                    draft_index=index, reason="schema", detail="gate returned nothing"
                )
            )
            continue
        corpus.append((f"{job.job_id}#{index}", _tokens(draft.stem)))
        accepted_drafts.append(draft)

    # Gate 4: batch answer-key balance (flag, don't reject — AC-4).
    balance_flag: str | None = None
    if len(accepted_drafts) >= 3:
        keys = Counter(d.correct for d in accepted_drafts)
        label, top = keys.most_common(1)[0]
        share = top / len(accepted_drafts)
        if share > config.balance_tolerance:
            balance_flag = (
                f"answer-key skew: {top}/{len(accepted_drafts)} drafts keyed "
                f"{label!r} (share {share:.2f} > tolerance "
                f"{config.balance_tolerance:.2f})"
            )

    pending_passage_path = (
        _park_pending_passage(payload, job, config)
        if target.mode == "passage_set"
        else None
    )

    # One provenance event per ingested batch (NFR-AUDIT-1), logged before
    # persistence so the parent trace exists even if a record write fails.
    trace_id = provenance.log_agent_call(
        agent_name=AGENT_NAME,
        input_data={
            "manifest_id": job.job_id.rsplit("-job", 1)[0],
            "job_id": job.job_id,
            "archetype_id": target.archetype_id,
            "section": target.section,
            "difficulty": target.difficulty,
            "tier": job.tier,
            "executor": executor_name,
            "mode": target.mode,
        },
        output_data={
            "drafts_in": len(raw_drafts),
            "accepted": len(accepted_drafts),
            "rejected": len(rejected),
            "balance_flag": balance_flag,
        },
        model=model_label,
        latency_ms=latency_ms,
        confidence=(
            round(sum(d.confidence for d in accepted_drafts) / len(accepted_drafts), 4)
            if accepted_drafts
            else 0.0
        ),
        sources=[],
    )

    accepted_ids: list[str] = []
    for draft in accepted_drafts:
        meta: dict[str, Any] = {
            "factory": {
                "manifest_id": job.job_id.rsplit("-job", 1)[0],
                "job_id": job.job_id,
                "archetype_id": target.archetype_id,
                "tier": job.tier,
                "executor": executor_name,
                "template_version": job.template_version,
                "mode": target.mode,
            }
        }
        if balance_flag:
            meta["factory"]["balance_flag"] = balance_flag
        if pending_passage_path:
            meta["factory"]["pending_passage_path"] = pending_passage_path
        proposal_id = record_proposal(
            draft.model_dump(),
            agent_trace_id=trace_id or "",
            model=model_label,
            confidence=draft.confidence,
            source_concept_ids=target.concepts,
            meta=meta,
        )
        accepted_ids.append(proposal_id)

    if rejected:
        logger.info(
            "factory intake %s: accepted %d, rejected %d (%s)",
            job.job_id,
            len(accepted_ids),
            len(rejected),
            ", ".join(f"#{r.draft_index}:{r.reason}" for r in rejected),
        )

    return IngestResult(
        job_id=job.job_id,
        accepted=accepted_ids,
        rejected=rejected,
        balance_flag=balance_flag,
        pending_passage_path=pending_passage_path,
        trace_id=trace_id,
        model_label=model_label,
    )
