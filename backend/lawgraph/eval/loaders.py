"""LegalBench dataset cache loader (spec 018 T-002).

Resolves task items from ``backend/var/legalbench/<subset>/`` cache directories.
If the cache directory is missing, the loader returns a minimal synthetic
stub set so the harness can be imported and tested without network access.

Cache format:
    backend/var/legalbench/
        core_reasoning/
            items.jsonl         # one JSON object per line
        precedent_retrieval/
            items.jsonl

Each JSONL line must have at least:
    {"index": <int|str>, "text": "<prompt>", "answer": "<label>"}

Additional fields (e.g. ``few_shot``, ``metadata``) are passed through to
the eval pipeline but are not required.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("lawgraph.eval.loaders")

_CACHE_ROOT = Path("backend/var/legalbench")

# ---------------------------------------------------------------------------
# Synthetic stubs used when no cache file is present (unit-test friendly)
# ---------------------------------------------------------------------------
_SYNTHETIC_STUBS: dict[str, list[dict[str, Any]]] = {
    "core_reasoning": [
        {
            "index": "stub-cr-0",
            "text": (
                "Under the mailbox rule, a contract is formed when the offeree "
                "dispatches acceptance. True or False?"
            ),
            "answer": "True",
        },
        {
            "index": "stub-cr-1",
            "text": (
                "An offer can be revoked after the offeree has sent a letter of "
                "acceptance but before the offeror receives it. True or False?"
            ),
            "answer": "False",
        },
    ],
    "precedent_retrieval": [
        {
            "index": "stub-pr-0",
            "text": (
                "Which case established the modern test for personal jurisdiction "
                "in the United States?"
            ),
            "answer": "International Shoe Co. v. Washington",
        },
    ],
    "contract_nli": [
        {
            "index": "stub-cnli-0",
            "text": "Hypothesis: The agreement is perpetual. Premise: This agreement is valid for 12 months.",
            "answer": "Contradiction",
        },
    ],
    "definitions": [
        {
            "index": "stub-def-0",
            "text": "Define mens rea in one sentence.",
            "answer": "Guilty mind",
        },
    ],
    "causation": [
        {
            "index": "stub-cause-0",
            "text": "Was defendant's act the proximate cause of plaintiff's injury? Yes or No?",
            "answer": "Yes",
        },
    ],
}


def load_task(subset: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Load items for ``subset`` from the JSONL cache or return synthetic stubs.

    Args:
        subset: One of the supported subset names (e.g. ``"core_reasoning"``).
        limit: Cap the returned list to at most *limit* items. ``None`` means no cap.

    Returns:
        List of item dicts with at least ``index``, ``text``, and ``answer`` keys.

    Raises:
        ValueError: If ``subset`` is not a recognised name.
    """
    from lawgraph.eval.legalbench import ALLOWED_SUBSETS

    if subset not in ALLOWED_SUBSETS:
        raise ValueError(
            f"Unknown subset {subset!r}. Allowed: {sorted(ALLOWED_SUBSETS)}"
        )

    cache_path = _CACHE_ROOT / subset / "items.jsonl"
    if cache_path.exists():
        items = _load_jsonl(cache_path)
        logger.debug("Loaded %d items from cache: %s", len(items), cache_path)
    else:
        items = list(_SYNTHETIC_STUBS.get(subset, []))
        logger.warning(
            "Cache file missing for subset %r (%s). "
            "Using %d synthetic stub(s). "
            "Run scripts to populate real data or place items.jsonl at %s.",
            subset,
            cache_path,
            len(items),
            cache_path,
        )

    if limit is not None:
        items = items[:limit]
    return items


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL file, skipping blank lines and comment lines."""
    items: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Skipping malformed JSONL line %d in %s: %s", lineno, path, exc
                )
                continue
            items.append(obj)
    return items
