// 008 — Vector indexes for the GraphRAG vector leg (BL-20260810-17).
// Spec 028 shipped lexical + citation-expansion retrieval only, because no
// embedding property existed. `core/llm/embeddings.py` now writes one at
// ingest (and `backfill_embeddings` fills historical nodes), so the retriever
// can fuse a vector top-K with its lexical top-K.
//
// The dimension is pinned to nomic-embed-text (768) and the similarity to
// cosine; both must match `law_ai.core.llm.embeddings.EMBED_DIMENSIONS` or
// Neo4j rejects every write. Changing the embedding model means a NEW
// migration plus a re-backfill, never an edit to this file.

CREATE VECTOR INDEX case_embedding_vec IF NOT EXISTS
  FOR (c:Case) ON (c.embedding)
  OPTIONS {indexConfig: {
    `vector.dimensions`: 768,
    `vector.similarity_function`: 'cosine'
  }};

CREATE VECTOR INDEX statute_section_embedding_vec IF NOT EXISTS
  FOR (s:StatuteSection) ON (s.embedding)
  OPTIONS {indexConfig: {
    `vector.dimensions`: 768,
    `vector.similarity_function`: 'cosine'
  }};
