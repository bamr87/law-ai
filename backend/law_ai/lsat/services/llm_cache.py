"""Keyed store for LSAT LLM responses (spec 041 FR-13/FR-14).

Once the provider chain has produced a walkthrough or a cross-check verdict
for a given (question, request-shape, prompt-version) tuple, repeat requests
serve the stored copy instead of spending another model call. Append-only
JSONL, replayed last-write-wins — the same durability pattern as
:mod:`law_ai.lsat.services.proposals` and :mod:`law_ai.core.audit_jsonl`.

Keys embed the prompt version, so bumping a prompt naturally invalidates its
cached responses; callers can also bypass with an explicit ``refresh``.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from law_ai.core.settings_proxy import settings_proxy as settings

_DEFAULT_DIR = Path("backend/var/lsat_response_cache")
_FILENAME = "responses.jsonl"
_LOCK = threading.Lock()


def _cache_dir() -> Path:
    raw = getattr(settings, "LSAT_RESPONSE_CACHE_DIR", None) or _DEFAULT_DIR
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_path() -> Path:
    return _cache_dir() / _FILENAME


def cache_key(kind: str, payload: dict[str, Any]) -> str:
    """Deterministic key over a request shape. ``kind`` namespaces consumers."""
    blob = json.dumps(payload, sort_keys=True, default=str)
    return f"{kind}:{hashlib.sha256(blob.encode('utf-8')).hexdigest()[:24]}"


def _replay() -> dict[str, dict[str, Any]]:
    path = _cache_path()
    if not path.is_file():
        return {}
    out: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = row.get("key")
            if isinstance(key, str):
                out[key] = row
    return out


def get(key: str) -> dict[str, Any] | None:
    """Return the stored payload for ``key``, or None on a miss."""
    row = _replay().get(key)
    if row is None:
        return None
    payload = row.get("payload")
    return payload if isinstance(payload, dict) else None


def put(key: str, payload: dict[str, Any]) -> None:
    """Store ``payload`` under ``key`` (last write wins on replay)."""
    row = {
        "key": key,
        "cached_at": datetime.now(UTC).isoformat(),
        "payload": payload,
    }
    with _LOCK, _cache_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def entries(kind: str) -> list[dict[str, Any]]:
    """All stored payloads whose key belongs to ``kind`` (for reporting)."""
    return [
        row["payload"]
        for key, row in sorted(_replay().items())
        if key.startswith(f"{kind}:") and isinstance(row.get("payload"), dict)
    ]
