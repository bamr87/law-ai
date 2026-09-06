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

BL-20260527-05 adds an indexed Postgres mirror of the current state
(:class:`law_ai.lsat.models.LsatProposal`) so reads stop being linear in the
whole log as the queue grows. The JSONL file remains the audit trail and the
source of truth: every write appends there first and then refreshes the
mirror best-effort, and reads fall back to the replay whenever the mirror is
disabled or unreachable.
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
from law_ai.core.provenance import _in_async_context, provenance
from law_ai.core.settings_proxy import settings_proxy as settings
from law_ai.lsat.services import bank as _bank
from law_ai.lsat.services.bank import (
    Section,
    load_bank,
)

logger = logging.getLogger("law_ai.lsat.proposals")

ProposalStatus = Literal["pending", "approved", "rejected"]

#: Proposal kinds this store understands. ``question`` and ``guide`` predate
#: spec 048; the two ``library_*`` kinds carry the librarian's output. A
#: ``library_finding`` is a review report and is never promoted — it is read,
#: acted on by a human, and closed. A ``crosscheck`` row (BL-20260831-21) is
#: a *disagreement* raised by the blind-solve sweep: approving it means "the
#: key is right after all", so it promotes nothing into the bank either.
PROPOSAL_KINDS = (
    "question",
    "guide",
    "library_finding",
    "library_article",
    "crosscheck",
)

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

    ``proposal_kind`` (spec 045 FR-9) distinguishes question drafts from
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
    # The create event *is* the replayed row, so hand it straight to the
    # mirror instead of re-reading the whole log for one new proposal.
    _mirror_row(proposal_id, {proposal_id: dict(event)})
    return proposal_id


def link_guides_to_question(question_proposal_id: str, question_id: str) -> list[str]:
    """Point pending guides drafted for a question proposal at its bank id.

    BL-20260901-04. A guide authored beside a draft names the *proposal* id,
    because the question has no bank id until a reviewer approves it. This is
    the moment it gets one, so the linked guide drafts are rewritten to the
    real id and surface in the queue as guides for a live question.
    """
    linked: list[str] = []
    for row in list_proposals("pending", limit=1000):
        if row.get("proposal_kind") != "guide":
            continue
        if (row.get("meta") or {}).get("guide_for_proposal") != question_proposal_id:
            continue
        pid = str(row.get("id"))
        with _LOCK:
            _append(
                {
                    "type": "lsat_proposal.guide_link",
                    "id": pid,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "question_id": question_id,
                }
            )
        _mirror_row(pid)
        linked.append(pid)
    return linked


def record_judge_verdict(proposal_id: str, verdict: dict[str, Any]) -> None:
    """Attach an advisory judge verdict to a proposal's factory meta.

    BL-20260702-02. Append-only like every other transition: the verdict
    replays into ``meta.factory.judge`` so the HITL queue shows it beside the
    producer lineage. Advisory only — it changes no status and gates nothing.
    """
    event = {
        "type": "lsat_proposal.judge",
        "id": proposal_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "judge": verdict,
    }
    with _LOCK:
        _append(event)
    _mirror_row(proposal_id)


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
            # Legacy rows predate spec 045's guide drafts.
            state[pid].setdefault("proposal_kind", "question")
        elif kind == "lsat_proposal.transition" and pid in state:
            state[pid]["status"] = ev.get("status", state[pid].get("status"))
            state[pid]["updated_at"] = ev.get("timestamp")
            state[pid]["reviewer"] = ev.get("reviewer")
            state[pid]["note"] = ev.get("note")
            if ev.get("question_id"):
                state[pid]["question_id"] = ev["question_id"]
        elif kind == "lsat_proposal.guide_link" and pid in state:
            # BL-20260901-04: the question this guide was drafted for has been
            # promoted, so the guide now points at its real bank id.
            guide_draft = dict(state[pid].get("draft") or {})
            guide_draft["question_id"] = ev.get("question_id")
            state[pid]["draft"] = guide_draft
        elif kind == "lsat_proposal.judge" and pid in state:
            # BL-20260702-02: the factory judge tier's advisory verdict, kept
            # under the producer lineage block the HITL queue already shows.
            meta = dict(state[pid].get("meta") or {})
            factory_meta = dict(meta.get("factory") or {})
            factory_meta["judge"] = ev.get("judge")
            meta["factory"] = factory_meta
            state[pid]["meta"] = meta
        elif kind == "lsat_proposal.cross_check" and pid in state:
            # BL-20260527-06: the tutor-grade prediction taken at approval.
            state[pid]["cross_check"] = ev.get("cross_check")
        elif kind == "lsat_proposal.passage_link" and pid in state:
            # BL-20260702-07: the draft's parked passage has been promoted,
            # so the draft now points at a real PassageContext id.
            draft = dict(state[pid].get("draft") or {})
            draft["passage_id"] = ev.get("passage_id")
            state[pid]["draft"] = draft
    return state


# ---------------------------------------------------------------------------
# Postgres mirror (BL-20260527-05)
#
# The JSONL log stays the audit trail and the source of truth for replay; the
# ``LsatProposal`` table is an indexed mirror of the *current* state so reads
# stop being linear in the whole log once the queue grows. Every write path
# below appends to the JSONL first and then refreshes the mirror row
# best-effort: an absent, unmigrated or unreachable database degrades to the
# replay rather than blocking a reviewer. Reads only prefer the mirror when
# ``LSAT_PROPOSALS_DB_READS`` is on, because a mirror that predates the
# backfill would silently hide older proposals — run
# ``manage.py lsat_proposals_backfill`` first, then flip the setting.
# ---------------------------------------------------------------------------


def _proposal_model() -> Any | None:
    """The mirror model, or ``None`` when the ORM must not be touched here."""
    if _in_async_context():
        # Django's ORM is sync-only; an async caller keeps the JSONL path.
        return None
    try:
        from law_ai.lsat.models import LsatProposal
    except Exception:  # pragma: no cover - app not loaded (bare script)
        return None
    return LsatProposal


def _db_reads_enabled() -> bool:
    return bool(getattr(settings, "LSAT_PROPOSALS_DB_READS", False))


def _mirror_defaults(row: dict[str, Any]) -> dict[str, Any]:
    """Scalar columns + verbatim payload for one replayed proposal row."""
    return {
        "proposal_kind": str(row.get("proposal_kind") or "question")[:32],
        "status": str(row.get("status") or "pending")[:16],
        "section": str(row.get("section") or "")[:8],
        "difficulty": str(row.get("difficulty") or "")[:16],
        "agent_trace_id": str(row.get("agent_trace_id") or "")[:64],
        "model": str(row.get("model") or "")[:128],
        "confidence": float(row.get("confidence") or 0.0),
        "reviewer": str(row.get("reviewer") or "")[:128],
        "note": str(row.get("note") or ""),
        "question_id": str(row.get("question_id") or "")[:64],
        "created_at": _as_datetime(row.get("created_at")),
        "updated_at": _as_datetime(row.get("updated_at"), fallback_now=False),
        "payload": row,
    }


def _as_datetime(raw: Any, *, fallback_now: bool = True) -> datetime | None:
    """Parse an ISO timestamp; ``fallback_now`` decides the unparseable case.

    ``created_at`` must always have a value (it orders the queue), while a
    pending proposal has no ``updated_at`` at all and must not be given a
    fake one.
    """
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return datetime.now(UTC) if fallback_now else None


def _mirror_row(
    proposal_id: str, state: dict[str, dict[str, Any]] | None = None
) -> None:
    """Refresh one mirror row from the JSONL replay. Never raises."""
    try:
        model = _proposal_model()
        if model is None:
            return
        row = (state if state is not None else _replay(_tail())).get(proposal_id)
        if row is None:
            return
        model.objects.update_or_create(id=proposal_id, defaults=_mirror_defaults(row))
    except Exception as exc:  # DB down / unmigrated / no DB access in tests
        logger.debug("lsat proposal mirror skipped for %s (%s)", proposal_id, exc)


def mirror_all() -> int:
    """Rewrite the whole mirror from the JSONL log; returns rows written.

    Used by ``manage.py lsat_proposals_backfill`` — the one-time catch-up for
    proposals recorded before the table existed.
    """
    model = _proposal_model()
    if model is None:
        raise RuntimeError("the LsatProposal mirror is not reachable from here")
    state = _replay(_tail())
    written = 0
    for pid, row in state.items():
        model.objects.update_or_create(id=pid, defaults=_mirror_defaults(row))
        written += 1
    return written


def _db_rows(status: str | None, limit: int) -> list[dict[str, Any]] | None:
    """Mirror rows for a listing, or ``None`` when the mirror cannot answer."""
    try:
        model = _proposal_model()
        if model is None or not _db_reads_enabled():
            return None
        if not model.objects.exists():
            # An empty mirror means "never backfilled", not "empty queue" —
            # answering [] here would hide the whole log.
            return None
        qs = model.objects.all()
        if status and status != "all":
            qs = qs.filter(status=status)
        return [
            dict(r.payload)
            for r in qs.order_by("-created_at")[:limit]
            if isinstance(r.payload, dict)
        ]
    except Exception as exc:
        logger.debug("lsat proposal mirror read skipped (%s)", exc)
        return None


def list_proposals(
    status: str | None = "pending",
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return proposals, newest-first, optionally filtered by status.

    ``status="all"`` (or ``None``) returns every replayed row regardless of
    current status. Served from the Postgres mirror when it is enabled and
    reachable, and from the JSONL replay otherwise (BL-20260527-05).
    """
    rows = _db_rows(status, limit)
    if rows is not None:
        return rows
    state = _replay(_tail())
    jsonl_rows = sorted(
        state.values(),
        key=lambda r: r.get("created_at") or "",
        reverse=True,
    )
    if status and status != "all":
        jsonl_rows = [r for r in jsonl_rows if r.get("status") == status]
    return jsonl_rows[:limit]


def get_proposal(proposal_id: str) -> dict[str, Any] | None:
    try:
        model = _proposal_model()
        if model is not None and _db_reads_enabled():
            row = model.objects.filter(id=proposal_id).first()
            if row is not None and isinstance(row.payload, dict):
                return dict(row.payload)
    except Exception as exc:
        logger.debug("lsat proposal mirror read skipped (%s)", exc)
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
    # One replay serves both the returned row and the mirror refresh.
    state = _replay(_tail())
    row = state.get(proposal_id)
    if row is None:
        raise KeyError(f"unknown proposal {proposal_id!r}")
    _mirror_row(proposal_id, state)
    _log_decision(row, status=status, reviewer=reviewer, note=note)
    return row


#: Audit-event kind every HITL decision on a proposal lands under
#: (BL-20260810-08). One row per approve *and* per reject, carrying the
#: reviewer identity and rationale, so a decision is never anonymous or
#: rationale-free in ``AuditEvent``.
DECISION_EVENT = "lsat_proposal_decision"


def _log_decision(
    row: dict[str, Any],
    *,
    status: ProposalStatus,
    reviewer: str,
    note: str | None,
) -> None:
    """Write the reviewer's decision to the audit layer (constitution §4).

    Goes through :func:`provenance.log_event` so the event tees to the JSONL
    store (agent ops dashboard) *and* inserts an ``AuditEvent`` row — the
    old approve-only ``audit_store.record`` never reached the database and
    the reject path wrote nothing at all. An audit hiccup must never block
    a reviewer, so failures are logged and swallowed.
    """
    # BL-20260811-04: when the decision came in over an authenticated request
    # the view publishes the account on a context variable, so the audit row
    # can carry a joinable user id alongside the legacy free-text name.
    from law_ai.core.reviewer import current_reviewer

    identity = current_reviewer()
    attributed = (reviewer or "").strip()
    payload: dict[str, Any] = {
        "proposal_id": row.get("id"),
        "proposal_kind": row.get("proposal_kind", "question"),
        "status": status,
        "reviewer": (
            attributed if attributed and attributed != "anonymous" else "(unattributed)"
        ),
        "reviewer_user_id": identity.user_id,
        "note": (note or "")[:500],
        "section": row.get("section"),
        "question_id": row.get("question_id"),
        "trace_id": row.get("agent_trace_id") or "",
        "model": row.get("model"),
        "confidence": row.get("confidence"),
    }
    try:
        provenance.log_event(DECISION_EVENT, payload)
    except Exception:  # pragma: no cover - audit failures must not block UX
        logger.warning(
            "provenance.log_event failed for %s", DECISION_EVENT, exc_info=True
        )


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

    # BL-20260702-07: a passage_set draft is meaningless without its context.
    # Refuse until the parked passage is promoted, which also links the draft.
    factory_meta = (row.get("meta") or {}).get("factory") or {}
    if factory_meta.get("mode") == "passage_set" and not draft.get("passage_id"):
        raise ValueError(
            f"proposal {proposal_id!r} was written against a new passage that is "
            "not promoted yet — promote "
            f"{factory_meta.get('pending_passage_path') or 'the parked passage'} "
            "first so the question links to it"
        )

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
        # BL-20260429-19: the approval *is* the editorial review, so it goes on
        # the item as a record rather than living only in the audit log. An
        # unattributed approval says so — "reviewed by nobody in particular" is
        # information, and inventing a reviewer would not be.
        "review": {
            "method": "editorial",
            "reviewed_by": (reviewer or "").strip() or "(unattributed)",
            "reviewed_at": datetime.now(UTC).date().isoformat(),
            "note": (note or "")[:300] or None,
        },
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

    # BL-20260901-04: a guide drafted beside this item named the proposal;
    # now that the question has a bank id, point the guide draft at it so a
    # reviewer sees the pair together.
    linked_guides = link_guides_to_question(proposal_id, question_id)

    updated = set_status(
        proposal_id,
        "approved",
        reviewer=reviewer,
        note=note,
        question_id=question_id,
    )
    if linked_guides:
        updated["linked_guide_proposals"] = linked_guides
    # The decision itself is audited by set_status (BL-20260810-08).
    return updated


#: Id prefix per section, mirroring the checked-in ``passages.json``.
_PASSAGE_ID_PREFIXES: dict[Section, str] = {"RC": "rc-passage-", "LG": "lg-game-"}

#: Audit-event kind for a promoted passage (BL-20260702-07).
PASSAGE_EVENT = "lsat_passage_promoted"


def pending_passages_dir() -> Path:
    """Where the content factory parks a ``passage_set`` job's new context."""
    from law_ai.lsat.factory.config import FactoryConfig
    from law_ai.lsat.factory.manifest import drafts_dir

    path = drafts_dir(FactoryConfig.from_settings()) / "pending_passages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _next_passage_id(section: Section, existing: set[str | None]) -> str:
    prefix = _PASSAGE_ID_PREFIXES[section]
    max_n = 0
    for raw in existing:
        if not isinstance(raw, str) or not raw.startswith(prefix):
            continue
        try:
            max_n = max(max_n, int(raw[len(prefix) :]))
        except ValueError:
            continue
    return f"{prefix}{max_n + 1:03d}"


def _read_parked_passage(path: Path) -> dict[str, Any]:
    """Load a parked passage JSON, refusing anything already promoted."""
    if not path.is_file():
        raise KeyError(f"no parked passage at {str(path)!r}")
    try:
        parked = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"parked passage {path} is malformed: {exc}") from exc
    if not isinstance(parked, dict):
        raise ValueError(f"parked passage {path} is not a JSON object")
    if parked.get("promoted_as"):
        raise ValueError(
            f"passage already promoted as {parked['promoted_as']!r} — "
            "promoting it twice would duplicate it in the bank"
        )
    return {k: v for k, v in parked.items() if k not in ("promoted_as", "promoted_at")}


def _link_pending_drafts(path: Path, passage_id: str) -> list[str]:
    """Wire ``passage_id`` onto every pending draft parked against *path*.

    The linkage is an appended log row (``lsat_proposal.passage_link``) that
    :func:`_replay` folds onto the draft, so a later
    :func:`promote_to_bank` carries the passage id into the bank item.
    """
    linked: list[str] = []
    for row in list_proposals(status="pending", limit=500):
        meta = (row.get("meta") or {}).get("factory") or {}
        parked = meta.get("pending_passage_path")
        if not isinstance(parked, str):
            continue
        try:
            same = Path(parked).expanduser().resolve() == path
        except OSError:  # pragma: no cover - unresolvable path in meta
            same = False
        if not same:
            continue
        pid = str(row.get("id"))
        with _LOCK:
            _append(
                {
                    "type": "lsat_proposal.passage_link",
                    "id": pid,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "passage_id": passage_id,
                }
            )
        _mirror_row(pid)
        linked.append(pid)
    return linked


def promote_passage(
    pending_path: str,
    *,
    reviewer: str = "anonymous",
    note: str | None = None,
) -> dict[str, Any]:
    """Promote a parked factory passage into ``passages.json`` (BL-20260702-07).

    A ``passage_set`` job invents its own context, which intake parks under
    ``drafts/pending_passages/`` rather than writing to the live data — the
    passage is content, and content needs a human. This is that human's
    button: the parked JSON is validated as a :class:`PassageContext`, given
    the next id for its section, appended to ``passages.json``, and the
    cached loader invalidated so the passage serves immediately. Every
    *pending* draft from the same job is then linked to the new
    ``passage_id`` so :func:`promote_to_bank` carries it into the bank item
    instead of leaving the reviewer to wire it by hand.

    Raises ``KeyError`` when nothing is parked at the path and ``ValueError``
    for a path outside the park directory, a malformed or unknown-section
    payload, or a passage that was already promoted.
    """
    from law_ai.lsat.services.bank import PassageContext, load_passages

    path = Path(pending_path).expanduser().resolve()
    park_dir = pending_passages_dir().resolve()
    if path.parent != park_dir or not path.name.endswith(".passage.json"):
        raise ValueError(
            f"{pending_path!r} is not a parked passage under {park_dir} — "
            "only the content factory's pending_passages/ artifacts promote"
        )
    data = _read_parked_passage(path)
    section = data.get("section")
    if section not in _PASSAGE_ID_PREFIXES:
        raise ValueError(f"parked passage has unsupported section {section!r}")

    passages_path = _bank.DATA_DIR / "passages.json"
    blob: dict[str, Any] = {"items": []}
    if passages_path.is_file():
        try:
            blob = json.loads(passages_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{passages_path} is malformed: {exc}") from exc
    existing: set[str | None] = {
        item.get("id") for item in blob.get("items", []) if isinstance(item, dict)
    }
    passage_id = _next_passage_id(section, existing)
    passage = PassageContext.model_validate({**data, "id": passage_id})
    promoted_at = datetime.now(UTC).isoformat()

    blob.setdefault("items", []).append(json.loads(passage.model_dump_json()))
    with _LOCK:
        passages_path.write_text(
            json.dumps(blob, indent=4, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        # Serve the new passage without a restart, exactly as promote_to_bank
        # does for questions.
        load_passages.cache_clear()
        path.write_text(
            json.dumps(
                {**data, "promoted_as": passage_id, "promoted_at": promoted_at},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    linked = _link_pending_drafts(path, passage_id)
    attributed = (reviewer or "").strip()
    try:
        provenance.log_event(
            PASSAGE_EVENT,
            {
                "passage_id": passage_id,
                "section": section,
                "title": passage.title,
                "pending_passage_path": str(path),
                "linked_proposals": linked,
                "reviewer": (
                    attributed
                    if attributed and attributed != "anonymous"
                    else "(unattributed)"
                ),
                "note": (note or "")[:500],
            },
        )
    except Exception:  # pragma: no cover - audit failures must not block UX
        logger.warning(
            "provenance.log_event failed for %s", PASSAGE_EVENT, exc_info=True
        )

    return {
        "passage_id": passage_id,
        "section": section,
        "title": passage.title,
        "pending_passage_path": str(path),
        "linked_proposals": linked,
        "promoted_at": promoted_at,
        "reviewer": reviewer,
        "note": note,
    }


def promote_crosscheck(
    proposal_id: str,
    *,
    reviewer: str = "anonymous",
    note: str | None = None,
) -> dict[str, Any]:
    """Close a cross-check disagreement as "the key is right" (BL-20260831-21).

    A ``crosscheck`` row is a report, not a draft: the sweep found the chain
    picking a different answer than the bank. Approving it records that a
    human re-verified the key and nothing changes in the bank — the deliberate
    difference from :func:`promote_to_bank`, which the API view relies on.
    Rejecting the row instead means the key is wrong and the question needs an
    edit, which is a separate, human-authored change.

    Raises ``KeyError`` for an unknown proposal and ``ValueError`` when the row
    is not a pending cross-check.
    """
    row = get_proposal(proposal_id)
    if row is None:
        raise KeyError(f"unknown proposal {proposal_id!r}")
    if row.get("status") != "pending":
        raise ValueError(
            f"proposal {proposal_id!r} cannot be closed from status "
            f"{row.get('status')!r}"
        )
    if row.get("proposal_kind") != "crosscheck":
        raise ValueError(
            f"proposal {proposal_id!r} is a {row.get('proposal_kind')!r} draft — "
            "use the matching promote_* helper"
        )
    return set_status(
        proposal_id,
        "approved",
        reviewer=reviewer,
        note=note,
        question_id=str((row.get("draft") or {}).get("question_id") or "") or None,
    )


def promote_guide_to_bank(
    proposal_id: str,
    *,
    reviewer: str = "anonymous",
    note: str | None = None,
) -> dict[str, Any]:
    """Append an approved solve-guide draft to ``guides.json`` (spec 045 FR-9).

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
    # The decision itself is audited by set_status (BL-20260810-08).
    return updated


def promote_library_article(
    proposal_id: str,
    *,
    reviewer: str = "anonymous",
    note: str | None = None,
) -> dict[str, Any]:
    """Write an approved library draft into ``data/library/`` (spec 048 FR-16).

    The only code path that mutates library content. ``LSATLibrarian`` itself
    writes nothing (spec 048 AC-10): a reviewer promotes a specific proposal id
    by hand, and the draft is re-parsed through the *full* loader validation
    before it lands, so a promoted article cannot break the load for everyone.

    A ``library_article`` draft carries ``article_id`` and ``markdown``. The
    file is written whole, so an expansion arrives as the complete revised
    article rather than as a patch this function has to apply.
    """
    from law_ai.lsat.services.library import (
        LibraryError,
        load_library,
        parse_article,
        reset_library_caches,
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
    if row.get("proposal_kind") != "library_article":
        raise ValueError(
            f"proposal {proposal_id!r} is a {row.get('proposal_kind')!r} draft — "
            "only 'library_article' drafts write to the library"
        )

    draft = dict(row.get("draft") or {})
    article_id = str(draft.get("article_id") or "").strip()
    markdown = str(draft.get("markdown") or "")
    if not article_id or not markdown.strip():
        raise ValueError(f"proposal {proposal_id!r} is missing article_id or markdown")

    # Parse before writing, not after: a draft that fails the dialect, the
    # cross-reference check or a structural gate must never reach the disk.
    try:
        parse_article(markdown, article_id=article_id, where=f"library/{article_id}.md")
    except LibraryError as exc:
        raise ValueError(f"draft failed library validation: {exc}") from exc

    path = _bank.DATA_DIR / "library" / f"{article_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        path.write_text(markdown.rstrip("\n") + "\n", encoding="utf-8")
        reset_library_caches()

    # A whole-library reload is the real gate: per-file parsing cannot see a
    # dangling cross-reference or a prerequisite cycle the new text introduces.
    try:
        load_library()
    except LibraryError as exc:
        path.unlink(missing_ok=True)
        reset_library_caches()
        raise ValueError(
            f"draft broke the library on reload and was rolled back: {exc}"
        ) from exc

    updated = set_status(proposal_id, "approved", reviewer=reviewer, note=note)
    # The decision itself is audited by set_status (BL-20260810-08).
    return updated


#: Id prefix for promoted writing prompts, mirroring the shipped library.
_WRITING_ID_PREFIX = "ws-"


def _next_writing_prompt_id(existing: set[str]) -> str:
    max_n = 0
    for raw in existing:
        if raw.startswith(_WRITING_ID_PREFIX):
            tail = raw[len(_WRITING_ID_PREFIX) :]
            if tail.isdigit():
                max_n = max(max_n, int(tail))
    return f"{_WRITING_ID_PREFIX}{max_n + 1:03d}"


def promote_writing_prompt(
    proposal_id: str,
    *,
    reviewer: str = "anonymous",
    note: str | None = None,
) -> dict[str, Any]:
    """Write an approved writing draft into ``writing_prompts.json``.

    BL-20260831-28. The writing library was hand-authored because the factory
    had no way to grow it; this is the reviewer's button for a factory draft.
    Mirrors :func:`promote_to_bank`: the draft is re-validated through the
    store's own model with the platform-owned fields (id, source) stamped
    here, appended to the library file, and the loader caches dropped so it
    serves immediately. Model essays are LLM-written, so the source label says
    so — a reader can always tell who wrote the worked example.

    Raises ``KeyError`` for an unknown proposal and ``ValueError`` when it is
    not a pending ``writing_prompt`` draft or fails validation.
    """
    from law_ai.lsat.services.writing import (
        WritingPrompt,
        load_writing_prompts,
        reset_writing_caches,
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
    if row.get("proposal_kind") != "writing_prompt":
        raise ValueError(
            f"proposal {proposal_id!r} is a {row.get('proposal_kind')!r} draft — "
            "only 'writing_prompt' drafts write to the writing library"
        )

    draft = dict(row.get("draft") or {})
    path = _bank.DATA_DIR / "writing_prompts.json"
    blob: dict[str, Any] = {"items": []}
    if path.is_file():
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{path} is malformed: {exc}") from exc
    existing = {
        str(item.get("id"))
        for item in blob.get("items", [])
        if isinstance(item, dict) and item.get("id")
    }
    prompt_id = _next_writing_prompt_id(existing)
    draft["id"] = prompt_id
    draft["source"] = (
        f"LSATContentFactory (approved {datetime.now(UTC).date().isoformat()})"
    )
    try:
        prompt = WritingPrompt.model_validate(draft)
    except Exception as exc:
        raise ValueError(f"draft failed writing-prompt validation: {exc}") from exc

    blob.setdefault("items", []).append(json.loads(prompt.model_dump_json()))
    with _LOCK:
        path.write_text(
            json.dumps(blob, indent=4, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        reset_writing_caches()

    # A full reload is the real gate: the store fails loudly on cross-reference
    # drift (unknown rubric, criterion, or concept), which per-model validation
    # cannot see. Roll the write back rather than breaking the library.
    try:
        load_writing_prompts()
    except Exception as exc:
        blob["items"] = [item for item in blob["items"] if item.get("id") != prompt_id]
        with _LOCK:
            path.write_text(
                json.dumps(blob, indent=4, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            reset_writing_caches()
        raise ValueError(
            f"draft broke the writing library on reload and was rolled back: {exc}"
        ) from exc

    updated = set_status(proposal_id, "approved", reviewer=reviewer, note=note)
    updated["writing_prompt_id"] = prompt_id
    # The decision itself is audited by set_status (BL-20260810-08).
    return updated


def cross_check_on_approval(proposal_id: str) -> dict[str, Any] | None:
    """Blind-solve a just-approved question and pin the verdict to the proposal.

    BL-20260527-06: the LSAT counterpart of the LegalBench regression bundle.
    Once a draft is in the bank it is run through
    :func:`law_ai.lsat.services.crosscheck.cross_check` with ``refresh=True``
    so a *fresh* "tutor-grade" prediction exists for the item from day one;
    later sweeps append further ``lsat_cross_check`` audit events and
    :func:`law_ai.lsat.services.regression.regression_report` compares them.

    The verdict is appended to the proposal log as an
    ``lsat_proposal.cross_check`` row (replayed onto the proposal as
    ``cross_check``) and returned. Returns ``None`` when the proposal is not
    an approved question or the check itself failed — a provider outage must
    never undo an approval. Sync callers only (DRF views, commands).
    """
    from asgiref.sync import async_to_sync

    from law_ai.lsat.services.crosscheck import cross_check

    row = get_proposal(proposal_id)
    if row is None or row.get("status") != "approved":
        return None
    if row.get("proposal_kind", "question") != "question":
        return None
    question = load_bank().get(str(row.get("question_id") or ""))
    if question is None:
        return None
    try:
        result = async_to_sync(cross_check)(question, refresh=True)
    except Exception:
        logger.warning(
            "cross-check on approval failed for %s", proposal_id, exc_info=True
        )
        return None
    verdict: dict[str, Any] = {
        "question_id": question.id,
        "checked_at": datetime.now(UTC).isoformat(),
        "agree": result.agree,
        "bank_choice": result.bank_choice,
        "model_choice": result.model_choice,
        "model": result.model,
        "used_llm": result.used_llm,
        "requires_human_review": result.requires_human_review,
    }
    with _LOCK:
        _append(
            {
                "type": "lsat_proposal.cross_check",
                "id": proposal_id,
                "timestamp": verdict["checked_at"],
                "cross_check": verdict,
            }
        )
    _mirror_row(proposal_id)
    return verdict


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
