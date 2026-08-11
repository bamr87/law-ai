"""Filesystem anchors for the eval harness (BL-20260810-04).

Every path here is derived from this file's location, never from the
process CWD. The previous ``Path("backend/var/legalbench")`` literals were
CWD-relative, and the container runs with ``CWD=/app`` (which *is* the
backend directory) — so caches and reports landed in
``backend/backend/var/legalbench/`` where neither CI, the digest, nor a
human ever looked.
"""

from __future__ import annotations

from pathlib import Path

#: ``…/backend`` — the directory containing ``manage.py`` and ``law_ai/``.
BACKEND_ROOT = Path(__file__).resolve().parents[2]

#: Dataset cache + run artifacts.
CACHE_ROOT = BACKEND_ROOT / "var" / "legalbench"

#: Tracked accuracy baseline that regression checks compare against.
BASELINE_PATH = CACHE_ROOT / "baseline.json"

#: Append-only score history — one JSON object per completed run.
HISTORY_PATH = CACHE_ROOT / "history.jsonl"


def subset_cache_path(subset: str) -> Path:
    """Location of the cached items file for ``subset``."""
    return CACHE_ROOT / subset / "items.jsonl"


__all__ = [
    "BACKEND_ROOT",
    "BASELINE_PATH",
    "CACHE_ROOT",
    "HISTORY_PATH",
    "subset_cache_path",
]
