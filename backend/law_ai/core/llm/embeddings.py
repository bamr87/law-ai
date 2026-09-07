"""Local embedding client for the GraphRAG vector leg (BL-20260810-17).

Spec 028 shipped a lexical + citation-expansion retriever and said so in its
own docstring: "Vector similarity is deliberately NOT part of this pass — no
embedding column exists on ``:Case`` yet." This module is that column's
producer.

Three rules it does not bend:

* **Always local.** Embeddings talk to ``OLLAMA_BASE_URL`` and nothing else,
  regardless of ``LLM_PROVIDER_CHAIN``. A vector index is a property of the
  corpus, so every vector in it must come from the same model; routing this
  through the chain would silently mix embedding spaces the first time the
  Claude tier answered. It also keeps ingest free of a per-document vendor
  cost and keeps LegalBench comparability intact.
* **Fail-open.** :func:`embed_text` returns ``None`` when Ollama is
  unreachable or the model is not pulled. Ingest must never block on the
  embedder, and the retriever degrades to its lexical + expansion legs.
* **Audited.** Every batch that reaches the network writes one
  ``embedding_batch`` provenance event (constitution §4).

The dimension is pinned to the model: ``nomic-embed-text`` emits 768 floats,
which is what ``008_vector_indexes.cypher`` declares. Changing the model means
a new migration and a re-backfill, not a settings tweak — a vector index whose
dimension disagrees with its vectors rejects every write.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from law_ai.core.provenance import provenance
from law_ai.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("law_ai.core.llm.embeddings")

#: The model the compose stack bootstraps, so the default path needs no setup.
DEFAULT_EMBED_MODEL = "nomic-embed-text"

#: Output width of ``nomic-embed-text``. Must match 008_vector_indexes.cypher.
EMBED_DIMENSIONS = 768

#: Neo4j vector index names created by 008_vector_indexes.cypher.
CASE_VECTOR_INDEX = "case_embedding_vec"
STATUTE_VECTOR_INDEX = "statute_section_embedding_vec"

#: Property that holds the vector on both labels.
EMBEDDING_PROPERTY = "embedding"

_MAX_CHARS = 8000


def embedding_model() -> str:
    """The pinned local embedding model."""
    return str(getattr(settings, "OLLAMA_EMBED_MODEL", "") or DEFAULT_EMBED_MODEL)


def case_embedding_text(title: str | None, holding_summary: str | None) -> str:
    """The text a ``:Case`` is embedded from — same fields the fulltext index uses."""
    return "\n".join(p for p in (title, holding_summary) if p and p.strip()).strip()[
        :_MAX_CHARS
    ]


def statute_embedding_text(
    citation: str | None, heading: str | None, text: str | None
) -> str:
    """The text a ``:StatuteSection`` is embedded from."""
    return "\n".join(p for p in (citation, heading, text) if p and p.strip()).strip()[
        :_MAX_CHARS
    ]


def _extract_vector(payload: Any) -> list[float]:
    """Pull the vector out of an Ollama ``/api/embeddings`` response."""
    if not isinstance(payload, dict):
        raise ValueError("embedding response is not an object")
    vector = payload.get("embedding")
    if vector is None:
        embeddings = payload.get("embeddings")
        if isinstance(embeddings, list) and embeddings:
            vector = embeddings[0]
    if not isinstance(vector, list) or not vector:
        raise ValueError("embedding response carries no vector")
    return [float(x) for x in vector]


async def embed_text(text: str, *, component: str = "graph") -> list[float] | None:
    """Embed one string locally, or return ``None`` when that is not possible.

    ``None`` (rather than an exception) is the contract: every caller — ingest,
    backfill, retrieval — must be able to carry on without a vector.
    """
    vectors = await embed_texts([text], component=component)
    return vectors[0]


async def embed_texts(
    texts: list[str], *, component: str = "graph"
) -> list[list[float] | None]:
    """Embed a batch, preserving order. Entries that fail come back ``None``.

    A single transport failure fails the whole batch (the backend is down, not
    one document), so the caller sees an all-``None`` list rather than a
    partially embedded corpus that would look complete.
    """
    wanted = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
    out: list[list[float] | None] = [None] * len(texts)
    if not wanted:
        return out

    model = embedding_model()
    base_url = str(settings.OLLAMA_BASE_URL).rstrip("/")
    timeout = float(getattr(settings, "OLLAMA_REQUEST_TIMEOUT_S", 120.0))
    url = f"{base_url}/api/embeddings"
    started = time.perf_counter()
    computed = 0
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for index, text in wanted:
                response = await client.post(
                    url, json={"model": model, "prompt": text[:_MAX_CHARS]}
                )
                response.raise_for_status()
                vector = _extract_vector(response.json())
                if len(vector) != EMBED_DIMENSIONS:
                    raise ValueError(
                        f"{model} returned {len(vector)} dims, "
                        f"expected {EMBED_DIMENSIONS}"
                    )
                out[index] = vector
                computed += 1
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        # Fail open: the caller keeps working without vectors.
        logger.info("local embeddings unavailable at %s (%s)", url, exc)
        return [None] * len(texts)

    provenance.log_event(
        "embedding_batch",
        {
            "component": component,
            "model": model,
            "computed": computed,
            "dimensions": EMBED_DIMENSIONS,
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 2),
        },
    )
    return out


__all__ = [
    "CASE_VECTOR_INDEX",
    "DEFAULT_EMBED_MODEL",
    "EMBEDDING_PROPERTY",
    "EMBED_DIMENSIONS",
    "STATUTE_VECTOR_INDEX",
    "case_embedding_text",
    "embed_text",
    "embed_texts",
    "embedding_model",
    "statute_embedding_text",
]
