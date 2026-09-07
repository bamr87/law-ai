"""``backfill_embeddings`` — fill ``embedding`` on historical graph nodes.

BL-20260810-17. Ingest writes an embedding for every ``:Case`` and
``:StatuteSection`` it commits from now on, but the corpus that landed before
that has none, and a vector index only ever returns nodes that carry a vector.
This command walks the un-embedded nodes in batches and fills them in.

    make backfill-embeddings                      # dry run, counts only
    make backfill-embeddings COMMIT=1
    make manage CMD='backfill_embeddings --commit --label Case --limit 200'

Read-only unless ``--commit``. Idempotent: a node is only visited while its
``embedding`` is null (or was written by a different model), so re-running
after an interrupted pass picks up exactly where it stopped. Every batch goes
through the local embedder — no third-party tier is ever consulted.
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from law_ai.core.llm.embeddings import (
    case_embedding_text,
    embed_texts,
    embedding_model,
    statute_embedding_text,
)
from law_ai.core.neo4j.driver import get_neo4j_driver

LABELS = ("Case", "StatuteSection")

# Nodes with no vector, or one written by a different model — a vector index
# is only coherent when every vector in it came from the same embedder.
_PENDING_CASES = """
MATCH (c:Case)
WHERE c.archived_at IS NULL
  AND (c.embedding IS NULL OR coalesce(c.embedding_model, '') <> $model)
RETURN c.id AS id, c.title AS title, c.holding_summary AS holding_summary
ORDER BY c.id
LIMIT $limit
"""

_PENDING_SECTIONS = """
MATCH (s:StatuteSection)
WHERE s.archived_at IS NULL
  AND (s.embedding IS NULL OR coalesce(s.embedding_model, '') <> $model)
RETURN s.id AS id, s.citation AS citation, s.heading AS heading, s.text AS text
ORDER BY s.id
LIMIT $limit
"""

# One statement per label so the MATCH is label-anchored rather than a full
# scan. The label is never user input — it is one of LABELS.
_SET_EMBEDDING = {label: f"""
UNWIND $rows AS row
MATCH (n:{label} {{id: row.id}})
SET n.embedding = row.embedding,
    n.embedding_model = $model,
    n.embedding_at = datetime()
""" for label in LABELS}


def _text_for(label: str, row: dict[str, Any]) -> str:
    if label == "Case":
        return case_embedding_text(row.get("title"), row.get("holding_summary"))
    return statute_embedding_text(
        row.get("citation"), row.get("heading"), row.get("text")
    )


async def _fetch(
    session: Any, label: str, model: str, limit: int
) -> list[dict[str, Any]]:
    cypher = _PENDING_CASES if label == "Case" else _PENDING_SECTIONS
    result = await session.run(cypher, {"model": model, "limit": limit})
    return [dict(record) async for record in result]


async def run_backfill(
    *, labels: tuple[str, ...], batch_size: int, limit: int | None, commit: bool
) -> dict[str, dict[str, int]]:
    """Embed pending nodes label by label; return per-label counters."""
    model = embedding_model()
    driver = get_neo4j_driver()
    stats: dict[str, dict[str, int]] = {
        label: {"pending": 0, "embedded": 0, "skipped_empty": 0} for label in labels
    }

    async with driver.session() as session:
        for label in labels:
            done = 0
            while True:
                take = batch_size if limit is None else min(batch_size, limit - done)
                if take <= 0:
                    break
                rows = await _fetch(session, label, model, take)
                if not rows:
                    break
                stats[label]["pending"] += len(rows)
                texts = [_text_for(label, row) for row in rows]
                stats[label]["skipped_empty"] += sum(1 for t in texts if not t)
                if not commit:
                    done += len(rows)
                    # Nothing is written, so the same page comes back forever:
                    # one pass over the first page is all a dry run can do.
                    break
                vectors = await embed_texts(texts, component="backfill")
                payload = [
                    {"id": row["id"], "embedding": vector}
                    for row, vector in zip(rows, vectors, strict=True)
                    if vector is not None
                ]
                if not payload:
                    # Embedder is down; stop rather than spin on the same page.
                    break
                await session.run(
                    _SET_EMBEDDING[label], {"rows": payload, "model": model}
                )
                stats[label]["embedded"] += len(payload)
                done += len(rows)
    return stats


class Command(BaseCommand):
    help = (
        "Backfill nomic-embed-text embeddings onto :Case / :StatuteSection nodes "
        "so the GraphRAG vector leg can see the historical corpus. Read-only "
        "unless --commit."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--commit", action="store_true", help="actually write the vectors"
        )
        parser.add_argument(
            "--label",
            default=None,
            choices=list(LABELS),
            help="restrict to one label (default: both)",
        )
        parser.add_argument("--batch-size", type=int, default=32)
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args: Any, **opts: Any) -> None:
        batch_size = int(opts["batch_size"])
        if batch_size < 1:
            raise CommandError("--batch-size must be >= 1")
        limit = opts["limit"]
        if limit is not None and int(limit) < 1:
            raise CommandError("--limit must be >= 1")
        labels = (opts["label"],) if opts["label"] else LABELS
        commit = bool(opts["commit"])

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"backfill_embeddings ({embedding_model()}, local only): "
                + ("COMMIT mode." if commit else "dry run — pass --commit to write.")
            )
        )
        stats = async_to_sync(run_backfill)(
            labels=labels,
            batch_size=batch_size,
            limit=None if limit is None else int(limit),
            commit=commit,
        )
        for label, counts in stats.items():
            self.stdout.write(
                self.style.SUCCESS(
                    f"  {label}: pending={counts['pending']} "
                    f"embedded={counts['embedded']} "
                    f"no_text={counts['skipped_empty']}"
                )
            )
        if commit and not any(c["embedded"] for c in stats.values()):
            self.stdout.write(
                self.style.WARNING(
                    "Nothing was embedded. If nodes are pending, the local "
                    "embedder is unreachable — check `make local-ai-health` "
                    "and that the model is pulled."
                )
            )
