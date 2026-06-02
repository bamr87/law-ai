"""Append-only JSONL audit store (spec 003 FR-1).

Every provenance event is teed here so the agent ops dashboard can tail
recent activity without grepping container logs. The file is bounded by
a simple in-process ring rotation: when ``MAX_AUDIT_LINES`` is exceeded
the file is truncated to its last ``KEEP_AUDIT_LINES`` lines.

Concurrency note: relies on POSIX append atomicity for writes <= 4 KB,
which is comfortably above any provenance event we currently emit.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from pathlib import Path
from typing import Any

from lawgraph.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("lawgraph.audit_store")


def _path() -> Path:
    raw = Path(settings.AUDIT_PATH)
    return raw if raw.is_absolute() else Path.cwd() / raw


def record(event: dict[str, Any]) -> None:
    """Append ``event`` to the audit JSONL. Failures are swallowed (NFR-AUDIT-1)."""
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, default=str) + "\n")
        _rotate_if_needed(path)
    except Exception as exc:  # pragma: no cover - log-only safety net
        logger.warning("audit_store.record failed: %s", exc)


def tail(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent ``limit`` events, newest first.

    Returns an empty list when the file does not exist or any line fails
    to parse (the bad line is skipped, not raised).
    """
    path = _path()
    if not path.is_file():
        return []
    if limit <= 0:
        return []
    buf: deque[str] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line:
                buf.append(line)
    out: list[dict[str, Any]] = []
    for line in reversed(buf):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def by_trace(trace_id: str, max_scan: int = 5000) -> list[dict[str, Any]]:
    """Return events whose ``trace_id`` matches ``trace_id`` (or whose
    ``input.child_trace_ids`` contains it), oldest first.

    Also walks parent → children: if any matched event lists child_trace_ids,
    events with those ids are pulled in too. This makes the analysis dashboard
    show every leg of a multi-agent run when given any one of its trace_ids.

    Scans up to the last ``max_scan`` lines to keep cost bounded.
    """
    path = _path()
    if not path.is_file() or not trace_id:
        return []
    buf: deque[str] = deque(maxlen=max_scan)
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line:
                buf.append(line)
    parsed: list[dict[str, Any]] = []
    for line in buf:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    wanted: set[str] = {trace_id}
    # Expand 2 hops: collect child_trace_ids from any event already in scope,
    # then re-scan once. Two passes cover parent→children and child→sibling
    # via parent pointer, which is enough for the current AnalysisStudio fan-out.
    for _ in range(2):
        before = len(wanted)
        for ev in parsed:
            tid = ev.get("trace_id")
            inp = ev.get("input") if isinstance(ev.get("input"), dict) else {}
            children = (inp or {}).get("child_trace_ids") or []
            if tid in wanted and isinstance(children, list):
                wanted.update(c for c in children if isinstance(c, str))
            if (
                isinstance(children, list)
                and any(c in wanted for c in children)
                and isinstance(tid, str)
            ):
                wanted.add(tid)
        if len(wanted) == before:
            break

    return [ev for ev in parsed if ev.get("trace_id") in wanted]


def _rotate_if_needed(path: Path) -> None:
    """Truncate to the last ``KEEP_AUDIT_LINES`` when the file outgrows the cap."""
    cap = settings.MAX_AUDIT_LINES
    keep = settings.KEEP_AUDIT_LINES
    if cap <= 0 or keep <= 0 or keep >= cap:
        return
    with path.open("r", encoding="utf-8") as fh:
        lines = fh.readlines()
    if len(lines) <= cap:
        return
    tail_lines = lines[-keep:]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(tail_lines), encoding="utf-8")
    tmp.replace(path)
