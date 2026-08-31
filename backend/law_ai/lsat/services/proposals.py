"""LSAT proposal store + gap analysis (spec 019 T-002).

Append-only JSONL log mirroring the pattern used by
:mod:`law_ai.core.audit_jsonl`. Every proposal lifecycle event (creation,
status transition, promotion) is recorded as one line; readers replay the
log to compute current state. This keeps the MVP free of any new database
migration while preserving full auditability.

Promotion writes the approved draft into the matching ``*_bank.json`` file
in :mod:`law_ai.lsat.services.bank.DATA_DIR` and invalidates the cached
``load_bank()`` result so the new question is immediately visible via the
existing ``/api/lsat/questions/`` endpoints.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict, deque
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from law_ai.core import audit_jsonl as audit_store
from law_ai.core.settings_proxy import settings_proxy as settings
from law_ai.lsat.services import bank as _bank
from law_ai.lsat.services.bank import (
    Section,
    load_bank,
)

logger = logging.getLogger("law_ai.lsat.proposals")

ProposalStatus = Literal["pending", "approved", "rejected"]

_BANK_FILES: dict[Section, str] = {
    "LR": "lr_bank.json",
    "RC": "rc_bank.json",
    "LG": "lg_bank.json",
}

_DEFAULT_DIR = Path("backend/var/lsat_proposals")
_PROPOSALS_FILENAME = "proposals.jsonl"

# Single-process write lock — JSONL appends are atomic at the OS level for
# the small payloads we emit, but threaded promotion needs serialisation so
# the bank file write doesn't race against itself.
_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Storage path helpers
# ---------------------------------------------------------------------------


def _proposals_dir() -> Path:
    raw = getattr(settings, "LSAT_PROPOSALS_DIR", None) or _DEFAULT_DIR
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _proposals_path() -> Path:
    return _proposals_dir() / _PROPOSALS_FILENAME


# ---------------------------------------------------------------------------
# Low-level append + tail
# ---------------------------------------------------------------------------


def _append(event: dict[str, Any]) -> None:
    path = _proposals_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, default=str) + "\n")


def _tail(limit: int = 5000) -> list[dict[str, Any]]:
    path = _proposals_path()
    if not path.is_file():
        return []
    buf: deque[str] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line:
                buf.append(line)
    out: list[dict[str, Any]] = []
    for line in buf:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# ---------------------------------------------------------------------------
# Public API (spec 019 FR-4..FR-6, FR-8)
# ---------------------------------------------------------------------------


def record_proposal(
    draft: dict[str, Any],
    *,
    agent_trace_id: str,
    model: str,
    confidence: float,
    source_concept_ids: Iterable[str] | None = None,
    meta: dict[str, Any] | None = None,
    proposal_kind: str = "question",
) -> str:
    """Persist one draft as ``pending`` and return the proposal id.

    ``meta`` (optional, spec 024 FR-9) carries producer lineage — e.g. the
    content factory's manifest/job/archetype/tier — verbatim onto the create
    event so it survives into the HITL queue and audit replay.

    ``proposal_kind`` (spec 041 FR-9) distinguishes question drafts from
    solve-guide drafts; legacy rows without the field replay as "question".
    """
    proposal_id = f"prop-{uuid4().hex[:12]}"
    event = {
        "type": "lsat_proposal.create",
        "id": proposal_id,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "pending",
        "proposal_kind": proposal_kind,
        "section": draft.get("section"),
        "difficulty": draft.get("difficulty"),
        "draft": draft,
        "agent_trace_id": agent_trace_id,
        "model": model,
        "confidence": confidence,
        "source_concept_ids": list(source_concept_ids or []),
    }
    if meta:
        event["meta"] = meta
    with _LOCK:
        _append(event)
    return proposal_id


def _replay(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Replay the JSONL log into the current state per proposal id."""
    state: dict[str, dict[str, Any]] = {}
    for ev in events:
        pid = ev.get("id")
        if not isinstance(pid, str):
            continue
        kind = ev.get("type")
        if kind == "lsat_proposal.create":
            state[pid] = dict(ev)
            # Legacy rows predate spec 041's guide drafts.
            state[pid].setdefault("proposal_kind", "question")
        elif kind == "lsat_proposal.transition" and pid in state:
            state[pid]["status"] = ev.get("status", state[pid].get("status"))
            state[pid]["updated_at"] = ev.get("timestamp")
            state[pid]["reviewer"] = ev.get("reviewer")
            state[pid]["note"] = ev.get("note")
            if ev.get("question_id"):
                state[pid]["question_id"] = ev["question_id"]
    return state


def list_proposals(
    status: str | None = "pending",
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return proposals, newest-first, optionally filtered by status.

    ``status="all"`` (or ``None``) returns every replayed row regardless of
    current status.
    """
    state = _replay(_tail())
    rows = sorted(
        state.values(),
        key=lambda r: r.get("created_at") or "",
        reverse=True,
    )
    if status and status != "all":
        rows = [r for r in rows if r.get("status") == status]
    return rows[:limit]


def get_proposal(proposal_id: str) -> dict[str, Any] | None:
    return _replay(_tail()).get(proposal_id)


def set_status(
    proposal_id: str,
    status: ProposalStatus,
    *,
    reviewer: str = "anonymous",
    note: str | None = None,
    question_id: str | None = None,
) -> dict[str, Any]:
    """Append a status-transition row; return the new replayed state."""
    event = {
        "type": "lsat_proposal.transition",
        "id": proposal_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "status": status,
        "reviewer": reviewer,
        "note": note,
    }
    if question_id:
        event["question_id"] = question_id
    with _LOCK:
        _append(event)
    row = get_proposal(proposal_id)
    if row is None:
        raise KeyError(f"unknown proposal {proposal_id!r}")
    return row


def promote_to_bank(
    proposal_id: str,
    *,
    reviewer: str = "anonymous",
    note: str | None = None,
) -> dict[str, Any]:
    """Append the approved draft to the matching ``*_bank.json`` file.

    Returns the updated proposal row including the assigned ``question_id``.
    Raises ``KeyError`` if the proposal does not exist and ``ValueError`` if
    its section is unknown or its current status is not ``pending``.
    """
    state = _replay(_tail())
    row = state.get(proposal_id)
    if row is None:
        raise KeyError(f"unknown proposal {proposal_id!r}")
    if row.get("status") != "pending":
        raise ValueError(
            f"proposal {proposal_id!r} cannot be promoted from status "
            f"{row.get('status')!r}"
        )
    if row.get("proposal_kind", "question") != "question":
        raise ValueError(
            f"proposal {proposal_id!r} is a {row.get('proposal_kind')!r} draft — "
            "use promote_guide_to_bank"
        )

    draft = dict(row.get("draft") or {})
    section = draft.get("section")
    if section not in _BANK_FILES:
        raise ValueError(f"unknown section {section!r} in proposal {proposal_id!r}")

    bank_path = _bank.DATA_DIR / _BANK_FILES[section]
    bank_blob: dict[str, Any] = {"items": []}
    if bank_path.is_file():
        try:
            bank_blob = json.loads(bank_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"bank file {bank_path} is malformed: {exc}") from exc

    existing_ids = {item.get("id") for item in bank_blob.get("items", [])}
    question_id = _next_question_id(section, existing_ids)

    new_item: dict[str, Any] = {
        "id": question_id,
        "section": section,
        "type": section,
        "difficulty": draft.get("difficulty"),
        "stem": draft.get("stem"),
        "choices": draft.get("choices") or [],
        "correct": draft.get("correct"),
        "explanation": draft.get("explanation"),
        "concepts": draft.get("concepts") or [],
        "references": draft.get("references") or [],
        "source": f"LSATContentAuthor (approved {datetime.now(UTC).date().isoformat()})",
    }
    if draft.get("passage_id"):
        new_item["passage_id"] = draft["passage_id"]

    bank_blob.setdefault("items", []).append(new_item)

    with _LOCK:
        bank_path.write_text(
            json.dumps(bank_blob, indent=4, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        # Invalidate the cached bank so the new question is immediately
        # visible via /api/lsat/questions/<id> without restart.
        load_bank.cache_clear()

    updated = set_status(
        proposal_id,
        "approved",
        reviewer=reviewer,
        note=note,
        question_id=question_id,
    )
    # Mirror the promotion into the global audit log so the agent ops
    # dashboard can correlate with the parent trace.
    try:
        audit_store.record(
            {
                "type": "lsat_proposal.approved",
                "proposal_id": proposal_id,
                "question_id": question_id,
                "section": section,
                "reviewer": reviewer,
                "trace_id": row.get("agent_trace_id"),
            }
        )
    except Exception:  # pragma: no cover - audit failures must not block UX
        logger.warning(
            "audit_store.record failed for lsat_proposal.approved", exc_info=True
        )
    return updated


def promote_guide_to_bank(
    proposal_id: str,
    *,
    reviewer: str = "anonymous",
    note: str | None = None,
) -> dict[str, Any]:
    """Append an approved solve-guide draft to ``guides.json`` (spec 041 FR-9).

    Mirrors :func:`promote_to_bank` for ``proposal_kind == "guide"`` rows: the
    draft is re-validated against the :class:`SolveGuide` schema, written into
    the guide store, and the cached loader invalidated so the guide serves
    immediately. Raises ``KeyError`` for unknown proposals and ``ValueError``
    when the row is not a pending guide draft, fails validation, or a guide
    already exists for the target question.
    """
    from law_ai.lsat.services.guides import (
        SolveGuide,
        load_guides,
        reset_guide_cache,
        validate_guide_quality,
    )

    state = _replay(_tail())
    row = state.get(proposal_id)
    if row is None:
        raise KeyError(f"unknown proposal {proposal_id!r}")
    if row.get("status") != "pending":
        raise ValueError(
            f"proposal {proposal_id!r} cannot be promoted from status "
            f"{row.get('status')!r}"
        )
    if row.get("proposal_kind", "question") != "guide":
        raise ValueError(
            f"proposal {proposal_id!r} is a {row.get('proposal_kind')!r} draft — "
            "use promote_to_bank"
        )

    draft = dict(row.get("draft") or {})
    draft["source"] = (
        f"LSATSolveGuideAuthor (approved {datetime.now(UTC).date().isoformat()})"
    )
    guide = SolveGuide.model_validate(draft)
    if guide.question_id in load_guides():
        raise ValueError(
            f"question {guide.question_id!r} already has a solve guide — "
            "reject this draft or retire the existing guide first"
        )
    question = load_bank().get(guide.question_id)
    if question is None:
        raise ValueError(f"guide targets unknown question {guide.question_id!r}")
    problems = validate_guide_quality(guide, question)
    if problems:
        raise ValueError("guide failed quality checks: " + "; ".join(problems))

    guides_path = _bank.DATA_DIR / "guides.json"
    blob: dict[str, Any] = {"items": []}
    if guides_path.is_file():
        try:
            blob = json.loads(guides_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"guide file {guides_path} is malformed: {exc}") from exc
    blob.setdefault("items", []).append(
        json.loads(guide.model_dump_json(by_alias=True))
    )

    with _LOCK:
        guides_path.write_text(
            json.dumps(blob, indent=4, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        reset_guide_cache()

    updated = set_status(
        proposal_id,
        "approved",
        reviewer=reviewer,
        note=note,
        question_id=guide.question_id,
    )
    try:
        audit_store.record(
            {
                "type": "lsat_proposal.approved",
                "proposal_id": proposal_id,
                "proposal_kind": "guide",
                "question_id": guide.question_id,
                "reviewer": reviewer,
                "trace_id": row.get("agent_trace_id"),
            }
        )
    except Exception:  # pragma: no cover - audit failures must not block UX
        logger.warning(
            "audit_store.record failed for lsat_proposal.approved", exc_info=True
        )
    return updated


def _next_question_id(section: Section, existing: set[str | None]) -> str:
    prefix = section.lower() + "-"
    max_n = 0
    for raw in existing:
        if not isinstance(raw, str) or not raw.startswith(prefix):
            continue
        tail = raw[len(prefix) :]
        try:
            max_n = max(max_n, int(tail))
        except ValueError:
            continue
    return f"{prefix}{max_n + 1:03d}"


# ---------------------------------------------------------------------------
# Gap analysis (spec 019 FR-6)
# ---------------------------------------------------------------------------


def gap_analysis(
    *,
    window: int = 5000,
    min_attempts: int = 3,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Return weakest `(section, concept)` pairs from `lsat_grade` events.

    Output rows are sorted ascending by accuracy and capped at *limit*.
    Returns an empty list when there are fewer than ``min_attempts``
    samples for every pair.
    """
    events = audit_store.tail(window)
    buckets: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"attempts": 0, "correct": 0}
    )
    for ev in events:
        if ev.get("type") != "lsat_grade":
            continue
        section = str(ev.get("section") or "?")
        concepts = ev.get("concepts") or []
        if not concepts:
            concepts = ["(uncategorised)"]
        for concept in concepts:
            key = (section, str(concept))
            buckets[key]["attempts"] += 1
            if ev.get("correct"):
                buckets[key]["correct"] += 1

    rows: list[dict[str, Any]] = []
    for (section, concept), agg in buckets.items():
        attempts = agg["attempts"]
        if attempts < min_attempts:
            continue
        correct = agg["correct"]
        rows.append(
            {
                "section": section,
                "concept": concept,
                "attempts": attempts,
                "correct": correct,
                "accuracy": round(correct / attempts, 4),
            }
        )
    rows.sort(key=lambda r: (r["accuracy"], -r["attempts"]))
    return rows[:limit]
