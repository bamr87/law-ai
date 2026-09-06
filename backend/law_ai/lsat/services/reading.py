"""Durable library reading progress (BL-20260905-39).

Read state used to exist only as ``lsat_article_read`` events in the JSONL
audit tail, replayed on every request. That tail is a bounded ring, so once a
deployment's log rotated past a read event the article un-marked itself
server-side and the learner's progress went *backwards* — visible the moment
they opened a browser whose ``localStorage`` could not paper over it.

:class:`~law_ai.lsat.models.LsatArticleRead` is the projection that does not
rotate. The event is still written first and stays the audit trail; this module
is the pair of functions that keep the table in step with it and read it back.

Every function here is best-effort in the same direction as
``law_ai.lsat.services.attempts``: a database that is absent, unmigrated or
unreachable degrades to the JSONL replay rather than failing a learner's click.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("law_ai.lsat.reading")


def record_article_read(
    reader: str,
    *,
    article_id: str,
    read: bool,
    sections: list[str] | None = None,
    kind: str = "",
) -> Any | None:
    """Upsert this reader's state for one article. Never raises.

    An un-mark writes ``read=False`` rather than deleting the row
    (constitution §4): the row is the current state, and "was read, then
    wasn't" is part of it.
    """
    from law_ai.lsat.models import LsatArticleRead

    try:
        row, _ = LsatArticleRead.objects.update_or_create(
            reader=reader,
            article_id=article_id,
            defaults={
                "read": bool(read),
                "sections": list(sections or []),
                "kind": kind or "",
            },
        )
        return row
    except Exception:  # pragma: no cover - storage hiccup must not break UX
        logger.warning("failed to persist LSAT article read state", exc_info=True)
        return None


def persisted_read_state(reader: str) -> dict[str, bool]:
    """``{article_id: read}`` for ``reader``, or ``{}`` when unavailable.

    Empty on any failure by design — the caller overlays this on the JSONL
    replay, so "no table" degrades to exactly the old behaviour.
    """
    from law_ai.lsat.models import LsatArticleRead

    try:
        return {
            str(row["article_id"]): bool(row["read"])
            for row in LsatArticleRead.objects.filter(reader=reader).values(
                "article_id", "read"
            )
        }
    except Exception:
        logger.debug("LSAT read-state table unavailable", exc_info=True)
        return {}


__all__ = ["persisted_read_state", "record_article_read"]
