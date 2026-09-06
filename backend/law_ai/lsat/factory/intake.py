"""Intake pipeline — quality gates between raw generation and the HITL queue.

Spec 024 FR-7 / FR-9. Every raw batch passes four ordered gates:

1. **schema** — :class:`DraftQuestion` validation (the shared spec-019
   contract: exactly five A-E choices, length caps, key within A-E);
2. **concept lint** — every tag exists in the catalog, the section matches
   the target, and any referenced passage exists;
3. **dedup** — normalized token-Jaccard of the stem against the live bank,
   pending proposals, and earlier drafts in the same batch (spec 024 AC-3).
   When the job writes against a shared passage/game, sentences that restate
   that context are dropped first and only the question-specific text is
   compared, on both sides (BL-20260702-08: LG batch-mates repeating the
   setup scored ~0.93 against each other in the first live run);
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
from collections.abc import Mapping
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel, Field

from law_ai.agents_runtime.crews.lsat_content_author import (
    DraftQuestion,
    answer_key_skew,
)
from law_ai.core.provenance import provenance
from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.embeddings import (
    EmbeddingIndex,
    EmbeddingUnavailable,
    closest_by_embedding,
)
from law_ai.lsat.factory.manifest import GenerationJob, drafts_dir
from law_ai.lsat.services.bank import load_bank, load_concepts, load_passages
from law_ai.lsat.services.proposals import list_proposals, record_proposal

logger = logging.getLogger("law_ai.lsat.factory.intake")

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
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal degradations during intake (e.g. the embedding "
        "dedup opinion was unavailable and only Jaccard ran).",
    )
    judge: dict[str, str] = Field(
        default_factory=dict,
        description="Advisory judge verdict per accepted proposal id "
        "(BL-20260702-02); empty when the judge tier is off.",
    )
    guides: dict[str, str] = Field(
        default_factory=dict,
        description="Guide proposal id per accepted question proposal id "
        "(BL-20260901-04); empty when guide-at-authoring is off.",
    )
    trace_id: str | None = None
    model_label: str = "external"


def _tokens(text: str) -> frozenset[str]:
    return frozenset(_TOKEN_RE.findall(text.lower()))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class _CorpusEntry(NamedTuple):
    """One stem the dedup gate compares against, with its passage linkage."""

    source_id: str
    stem: str
    tokens: frozenset[str]
    passage_id: str | None


_SENTENCE_RE = re.compile(r"(?<=[.?!:])\s+")

# Function words that carry no question-specific signal. Deliberately leaves
# modals and negation alone ("must", "could", "cannot", "not", "except"): in
# LG/RC stems those are exactly what tells one question from its neighbour.
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "and",
        "or",
        "if",
        "then",
        "is",
        "are",
        "be",
        "been",
        "that",
        "this",
        "these",
        "those",
        "which",
        "one",
        "following",
        "each",
        "with",
        "by",
        "as",
        "it",
        "its",
        "than",
        "from",
        "into",
        "any",
        "all",
        "some",
        "but",
        "so",
        "do",
        "does",
        "did",
        "would",
        "will",
        "has",
        "have",
        "had",
        "was",
        "were",
        "who",
        "whom",
        "whose",
        "what",
    ]
)

#: Share of a stem sentence's tokens already present in the passage/game
#: context above which the sentence counts as a restatement of that context.
_CONTEXT_SENTENCE_OVERLAP = 0.8

#: Fewer question-specific tokens than this and the residue is too thin to
#: compare on ("Which must be true?" would collapse onto every other short
#: question); the kept sentence(s) are then compared whole instead.
_MIN_QUESTION_TOKENS = 3


def _context_tokens(context: Mapping[str, Any] | None) -> frozenset[str]:
    """Token set of a passage/game context (setup, rules, passage text)."""
    if not context:
        return frozenset()
    parts: list[str] = [
        str(context[key])
        for key in ("title", "summary", "setup", "passage", "passage_b")
        if isinstance(context.get(key), str)
    ]
    rules = context.get("rules")
    if isinstance(rules, list):
        parts.extend(str(rule) for rule in rules)
    return _tokens(" ".join(parts))


def _question_sentences(stem: str, context: frozenset[str]) -> list[str]:
    """Sentences of *stem* that do not merely restate *context* (may be empty)."""
    kept: list[str] = []
    for sentence in _SENTENCE_RE.split(stem):
        toks = _tokens(sentence)
        if not toks:
            continue
        if len(toks & context) / len(toks) > _CONTEXT_SENTENCE_OVERLAP:
            continue
        kept.append(sentence.strip())
    return kept


def _question_text(stem: str, context: frozenset[str]) -> str:
    """The question-specific prose of *stem*; the whole stem when all of it
    restates the shared context (BL-20260702-08, reused by the embedding gate).
    """
    if not context:
        return stem
    kept = _question_sentences(stem, context)
    return " ".join(kept) if kept else stem


def _comparable_text(
    stem: str,
    entry_passage_id: str | None,
    *,
    context: frozenset[str],
    passage_key: str | None,
    config: FactoryConfig,
) -> str:
    """Text the semantic gate compares: context-stripped for passage mates."""
    if not config.dedup_strip_context or not context or passage_key is None:
        return stem
    if entry_passage_id != passage_key:
        return stem
    return _question_text(stem, context)


def _question_tokens(stem: str, context: frozenset[str]) -> tuple[frozenset[str], bool]:
    """Tokens of the question-specific part of *stem* (BL-20260702-08).

    Drops every sentence whose tokens mostly already appear in *context* — a
    draft restating the shared game setup or passage — then strips function
    words from what is left. Context tokens are *not* subtracted wholesale:
    in an LG stem the entity letters and verbs that also live in the setup
    ("If **H argues** third…" vs "If **K argues** third…") are the signal
    that separates two questions, so removing them would make every question
    on a game look alike.

    Returns ``(tokens, stripped)``. ``stripped`` is False when no sentence
    survived (nothing question-specific to compare — the full stem is used)
    and True otherwise; a residue thinner than :data:`_MIN_QUESTION_TOKENS`
    falls back to the kept sentences with their function words.
    """
    full = _tokens(stem)
    if not context:
        return full, False
    kept: set[str] = set()
    for sentence in _question_sentences(stem, context):
        kept |= _tokens(sentence)
    if not kept:
        return full, False
    residue = frozenset(kept - _STOPWORDS)
    if len(residue) < _MIN_QUESTION_TOKENS:
        return frozenset(kept), True
    return residue, True


def _dedup_context(
    payload: Mapping[str, Any], job: GenerationJob, passages: Mapping[str, Any]
) -> tuple[frozenset[str], str | None]:
    """Shared context a batch's stems may restate, plus its corpus key.

    Returns ``(context tokens, passage key)``: corpus entries carrying that
    key share the context and get the same stripping. In ``passage_set`` mode
    the context is the batch's own new passage and the key is the job id, so
    only intra-batch mates share it; in ``items`` mode both come from the
    target's existing passage.
    """
    target = job.target
    if target.mode == "passage_set":
        passage = payload.get("passage")
        context = passage if isinstance(passage, Mapping) else None
        return _context_tokens(context), job.job_id
    if target.passage_id is None:
        return frozenset(), None
    passage = passages.get(target.passage_id)
    if passage is None:
        return frozenset(), target.passage_id
    return _context_tokens(passage.model_dump()), target.passage_id


def _dedup_corpus() -> list[_CorpusEntry]:
    """Stems of the live bank + pending proposals, with passage linkage."""
    corpus: list[_CorpusEntry] = [
        _CorpusEntry(q.id, q.stem, _tokens(q.stem), q.passage_id)
        for q in load_bank().values()
    ]
    for row in list_proposals(status="pending", limit=500):
        draft = row.get("draft") or {}
        stem = str(draft.get("stem") or "")
        if stem:
            passage_id = draft.get("passage_id")
            corpus.append(
                _CorpusEntry(
                    str(row.get("id")),
                    stem,
                    _tokens(stem),
                    str(passage_id) if passage_id else None,
                )
            )
    return corpus


def _closest(
    stem_tokens: frozenset[str],
    corpus: list[_CorpusEntry],
    *,
    context: frozenset[str] = frozenset(),
    passage_key: str | None = None,
) -> tuple[str, float]:
    """Best Jaccard match in *corpus*; entries sharing the context are stripped too."""
    best_id, best_score = "", 0.0
    for entry in corpus:
        tokens = entry.tokens
        if context and passage_key is not None and entry.passage_id == passage_key:
            tokens, _ = _question_tokens(entry.stem, context)
        score = _jaccard(stem_tokens, tokens)
        if score > best_score:
            best_id, best_score = entry.source_id, score
    return best_id, best_score


def _embed_dedup(
    accepted: list[tuple[int, DraftQuestion]],
    corpus: list[_CorpusEntry],
    *,
    config: FactoryConfig,
    context: frozenset[str],
    passage_key: str | None,
) -> tuple[list[tuple[int, DraftQuestion]], list[GateRejection], str | None]:
    """Gate 3b — paraphrase detection over the drafts Jaccard let through.

    Token-Jaccard cannot see a reworded question (BL-20260702-01), so the
    survivors get a second, semantic opinion from the local embedding model.
    The comparison text is the same context-stripped question prose gate 3
    uses, so a batch written against one game is judged on its questions.

    Fails open: the first backend error stops the pass, every remaining draft
    is kept, and the returned warning is surfaced on the ``IngestResult`` —
    an offline run behaves exactly as it did before this gate existed.
    """
    if not config.embed_dedup_enabled or not accepted:
        return accepted, [], None
    index = EmbeddingIndex.from_config(config)
    pool: list[tuple[str, str]] = [
        (
            entry.source_id,
            _comparable_text(
                entry.stem,
                entry.passage_id,
                context=context,
                passage_key=passage_key,
                config=config,
            ),
        )
        for entry in corpus
    ]
    kept: list[tuple[int, DraftQuestion]] = []
    rejected: list[GateRejection] = []
    warning: str | None = None
    for index_in_batch, draft in accepted:
        if warning is not None:
            kept.append((index_in_batch, draft))
            continue
        text = _comparable_text(
            draft.stem,
            passage_key,
            context=context,
            passage_key=passage_key,
            config=config,
        )
        try:
            closest_id, score = closest_by_embedding(text, pool, index)
        except EmbeddingUnavailable as exc:
            warning = f"embedding dedup skipped: {exc}"
            logger.info("factory intake: %s", warning)
            kept.append((index_in_batch, draft))
            continue
        if score >= config.embed_dedup_threshold:
            rejected.append(
                GateRejection(
                    draft_index=index_in_batch,
                    reason="duplicate",
                    detail=f"stem ~{score:.2f} paraphrase of {closest_id} "
                    "(embedding similarity)",
                )
            )
            continue
        kept.append((index_in_batch, draft))
        pool.append((f"batch#{index_in_batch}", text))
    index.flush()
    return kept, rejected, warning


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
    corpus: list[_CorpusEntry],
    config: FactoryConfig,
    context: frozenset[str] = frozenset(),
    passage_key: str | None = None,
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

    # Gate 3: near-duplicate detection (bank + pending + intra-batch), on the
    # question-specific text when the stem restates a shared context.
    question, stripped = (
        _question_tokens(draft.stem, context)
        if config.dedup_strip_context
        else (_tokens(draft.stem), False)
    )
    closest_id, score = _closest(
        question,
        corpus,
        context=context if stripped else frozenset(),
        passage_key=passage_key,
    )
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
    if target.mode == "writing_prompt":
        # A writing task has no keyed choices to gate; its own module owns
        # the schema/lint/dedup rules (BL-20260831-28). Imported here to keep
        # the dependency one-way at module load.
        from law_ai.lsat.factory.writing_intake import ingest_writing_batch

        return ingest_writing_batch(
            payload,
            job=job,
            config=config,
            executor_name=executor_name,
            model_label=model_label,
            latency_ms=latency_ms,
        )
    catalog = set(load_concepts().keys())
    passages = dict(load_passages())
    corpus = _dedup_corpus()
    context, passage_key = _dedup_context(payload, job, passages)
    accepted_pairs: list[tuple[int, DraftQuestion]] = []
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
            context=context,
            passage_key=passage_key,
        )
        if rejection is not None or draft is None:
            rejected.append(
                rejection
                or GateRejection(
                    draft_index=index, reason="schema", detail="gate returned nothing"
                )
            )
            continue
        corpus.append(
            _CorpusEntry(
                f"{job.job_id}#{index}", draft.stem, _tokens(draft.stem), passage_key
            )
        )
        accepted_pairs.append((index, draft))

    # Gate 3b: paraphrase detection on the survivors (BL-20260702-01). Runs
    # after the token gate so the embedding backend only sees drafts that are
    # already schema-, lint-, and Jaccard-clean.
    warnings: list[str] = []
    accepted_pairs, embed_rejected, embed_warning = _embed_dedup(
        accepted_pairs,
        [e for e in corpus if not e.source_id.startswith(f"{job.job_id}#")],
        config=config,
        context=context,
        passage_key=passage_key,
    )
    if embed_warning:
        warnings.append(embed_warning)
    rejected.extend(embed_rejected)
    rejected.sort(key=lambda r: r.draft_index)
    accepted_drafts = [draft for _, draft in accepted_pairs]

    # Gate 4: batch answer-key balance (flag, don't reject — AC-4). Shared
    # with the direct agent paths via ``answer_key_skew`` (BL-20260606-02) so
    # factory and non-factory batches are judged by one rule.
    balance_flag = answer_key_skew(
        (d.correct for d in accepted_drafts), config.balance_tolerance
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
            "warnings": warnings,
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
        warnings=warnings,
        trace_id=trace_id,
        model_label=model_label,
    )
