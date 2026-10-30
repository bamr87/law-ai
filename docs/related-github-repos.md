# Related GitHub Repositories for Law AI

> Open-source projects, by category, that Law AI can build on for agents, legal NLP, knowledge graphs, GraphRAG, data pipelines, benchmarks and visualization.

**Goal**: Identify mature, open-source projects that provide building blocks for Law AI's core capabilities (multi-agent orchestration, legal NLP, knowledge graphs, GraphRAG, legal data pipelines, benchmarks, and visualization). These can be **directly leveraged, forked, or integrated** to accelerate development and avoid reinventing the wheel.

This document organizes repos by category with:
- Short description
- Why it's relevant to Law AI
- Recommended integration points
- **Status** — whether the repo was actually adopted, once 30+ specs had shipped

> **Status as of 2026-08.** This survey was written in the repo's first commit (2026-05-03), before any spec had shipped, and describes intent rather than the codebase. Some recommendations were adopted as originally planned (`eyecite`, `langgraph`, LegalBench, `cytoscape.js`). Several were superseded by hand-rolled, native implementations that turned out simpler than integrating the listed project (the CrewAI hybrid, the Neo4j GraphRAG fork). A few packages are declared as dependencies but never actually wired in. A handful of linked repos have moved, been renamed, or stopped existing since 2026-05. Each row below now carries a **Status** cell reflecting what's true today — treat the original "Recommendation" and "Action Plan" prose as historical intent, not current architecture. For what's actually running, see [architecture.md](architecture.md) and [AGENTS.md](../AGENTS.md).

---

## 1. Agent Orchestration & Multi-Agent Frameworks

These are the foundation for Law AI's agent crews (Ingestion Scout, Legal Analyst, Precedent Hunter, Orchestrator, etc.).

| Repository | Description | Relevance to Law AI | Status (2026-08) |
|------------|-------------|-----------------------|--------------------|
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | Lightweight, role-based multi-agent orchestration framework | Original primary choice for Law AI's "crews" (Analyst + Hunter + Weaver). | **Declared, not adopted.** `crewai>=1.14.0` is in `backend/pyproject.toml`, but `grep -rl "crewai" backend/law_ai` finds no imports. The shipped classes in `agents_runtime/crews/` (`LegalAnalyst`, `PrecedentHunter`, `TestSynthesizer`, `LSATContentAuthor` — no `Crew` suffix) are hand-written Pydantic-output classes that call `law_ai.core.llm` directly, not CrewAI primitives. |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | Stateful, graph-based agent workflows with checkpointing, time-travel, and human-in-the-loop | For Law AI's `Orchestrator` (state machines + HITL gates + audit trails). | **Adopted — the actual orchestration engine.** `LegalWorkflow` (`agents_runtime/graphs/legal_workflow.py`) is a `StateGraph` with an `AsyncPostgresSaver` checkpointer reading `settings.POSTGRES_URL`. Spec 035 added `ChatProviderChain` (`core/llm/langchain.py`), a real `BaseChatModel` wrapping the [product-runtime provider chain](../AGENTS.md), as its default LLM. |
| [microsoft/autogen](https://github.com/microsoft/autogen) | Conversational multi-agent framework with dynamic group chat | Proposed for "debate-style" legal reasoning (Analyst vs. opposing counsel). | **Not adopted.** No debate/adversarial agent mode has shipped. |
| [Eigenwise/atomic-agents](https://github.com/Eigenwise/atomic-agents) (renamed from `brainblend-ai/atomic-agents`) | Lightweight, structured, developer-centric agent framework, typed I/O | Proposed alternative if CrewAI/LangGraph felt too heavy. | **Not adopted.** The typed-Pydantic-output pattern it would have supplied was built by hand instead (see the crews row above). |

**What actually happened**: LangGraph became the real engine, as planned. CrewAI did not — the crews ended up as plain classes on top of `law_ai.core.llm` because that gave direct control over provenance logging (constitution §4: `core.llm` is "the sole sanctioned choke point for model calls") without a second framework's abstractions in the way. If a future spec wants CrewAI-native features (task delegation, crew-level memory), evaluate then against the cost of unwinding the current pattern — don't assume the original recommendation still holds.

---

## 2. Legal NLP, Parsing & Information Extraction

Critical for the Ingestion Scout and entity/relation extraction into Neo4j.

| Repository | Description | Relevance to Law AI | Status (2026-08) |
|------------|-------------|-----------------------|--------------------|
| [freelawproject/eyecite](https://github.com/freelawproject/eyecite) | Open-source legal citation parser (used by CourtListener) | Bluebook citations, parallel citations, court abbreviations. | **Adopted.** Live in `ingestionapp/services/scout.py`. |
| [ICLRandD/Blackstone](https://github.com/ICLRandD/Blackstone) | spaCy pipeline + model trained on UK legal text (NER, sentence segmentation) | Legal entity recognition (parties, courts, judges, holdings). | **Dropped (BL-20260429-03), superseded by spaCy 3.** It requires `spacy==2.1.8` against this project's `spacy>=3.8.0`, and spaCy 2.1 / thinc 7 publish no wheels for the Python 3.12 base image, so the `nlp` extra could never actually install; upstream last pushed 2024-07-16 and is treated as unmaintained. The extra now installs spaCy 3's `en_core_web_sm`, and `ingestionapp/services/ner.py` provides the lazy-loading shim the follow-up asked for — `ENABLE_NER=true` merges its PARTY/COURT/STATUTE spans into `scout._extract_entities`, off by default. |
| [Breakend/PileOfLaw](https://github.com/Breakend/PileOfLaw) (moved from `HazyResearch/pile-of-law`) | 256GB curated legal corpus for domain adaptation | Proposed for continued pre-training / fine-tuning a legal LLM. | **Not adopted.** Law AI does not fine-tune a base model; the [product-runtime LLM policy](../AGENTS.md) uses an ordered chain of hosted Claude and local Ollama models as-is. |
| [atticusproject/cuad](https://github.com/atticusproject/cuad) | Expert-annotated contract clause dataset | Proposed gold standard for contract clause extraction. | **Not adopted, and the link is dead** — the `atticusproject` GitHub org no longer exists. CUAD is now distributed as a dataset on Hugging Face if this is revisited. No contract-clause agent has shipped. |
| [LexPredict/lexpredict-lexnlp](https://github.com/LexPredict/lexpredict-lexnlp) | Legal NLP library (feature extraction, contract parsing) | Reference implementation for extractors (dates, monetary amounts). | Reference only — not adopted, not currently needed. |

**What actually happened**: Eyecite shipped as planned. Blackstone stalled on a real dependency conflict (spaCy major-version pin) and was ultimately dropped: BL-20260429-03 closed by delivering the *capability* — a lazy, flag-gated NER pass — on spaCy 3 (`ingestionapp/services/ner.py`) rather than by resolving a pin that upstream has not touched since 2024.

---

## 3. Legal Datasets, Benchmarks & Evaluation

Essential for grounding Law AI in real legal data and measuring reasoning quality.

| Repository | Description | Relevance to Law AI | Status (2026-08) |
|------------|-------------|-----------------------|--------------------|
| [HazyResearch/legalbench](https://github.com/HazyResearch/legalbench) | 162-task collaborative benchmark for legal reasoning in LLMs | Core evaluation harness. | **Adopted, but not as a pip dependency.** `backend/law_ai/eval/legalbench.py` + `loaders.py` resolve task items from a local `backend/var/legalbench/<subset>/` JSONL cache (falling back to synthetic stubs when a cache file is absent) — the harness never installs the `legalbench` package. Runs nightly (`.github/workflows/nightly-tests.yml`, `make test-legalbench-gate`) and stays pinned to Ollama regardless of the product-runtime provider chain, so scores remain comparable across runs (constitution §1). |
| [zeroentropy-ai/legalbenchrag](https://github.com/zeroentropy-ai/legalbenchrag) | Open retrieval benchmark for legal contracts and documents | Proposed to complement LegalBench with RAG-focused tasks. | **Not adopted.** No retrieval-specific eval tasks beyond LegalBench have shipped. |
| [openlegaldata/awesome-legal-data](https://github.com/openlegaldata/awesome-legal-data) | Curated list of 100+ legal datasets, corpora, benchmarks, tools | Reference when adding new data sources. | Reference only, still actively maintained upstream — useful starting point if a new jurisdiction or source is added. |
| [freelawproject/courtlistener](https://github.com/freelawproject/courtlistener) | The CourtListener platform + RECAP archive (US precedential opinions) | Primary data source. | **Adopted.** `ingestionapp/sources/courtlistener.py` (spec 001, spec 018) is a live `SOURCE_REGISTRY` adapter; `COURTLISTENER_API_KEY` is a configured setting. Two other adapters exist alongside it: `colorado_statutes.py` and `statute_scout.py`. |
| ~~`caselawaccessproject/caselaw-access-project`~~ | — | Bulk case corpus for graph seeding. | **Link was never valid** — that GitHub path does not resolve and doesn't appear to have ever existed under that name. The real project is Harvard LIL's Caselaw Access Project: code at [harvard-lil/capstone](https://github.com/harvard-lil/capstone) (archived 2024-09, read-only), bulk data at [case.law](https://case.law). **Not adopted** — no bulk CAP import exists in `ingestionapp/`; ingestion is incremental via the three live source adapters above, not a one-time bulk seed. |

---

## 4. Knowledge Graphs, GraphRAG & Legal Graph Examples

Neo4j is a cornerstone of Law AI's architecture; GraphRAG was originally planned as a fork of an existing example.

| Repository | Description | Relevance to Law AI | Status (2026-08) |
|------------|-------------|-----------------------|--------------------|
| [neo4j-product-examples/graphrag-contract-review](https://github.com/neo4j-product-examples/graphrag-contract-review) | End-to-end GraphRAG demo on commercial contracts (Neo4j + LLM entity extraction) | Originally planned as the fork target for Law AI's GraphRAG tool. | **Not adopted; superseded by a native implementation.** The shipped tool (`agents_runtime/tools/graph_rag.py`, spec 028 / BL-20260810-01) is a from-scratch lexical-search-plus-graph-expansion retriever: Neo4j fulltext indexes (`007_fulltext_indexes.cypher`) for top-K lexical hits, then `CITES`-edge traversal for graph expansion, with constitution §13 attribution and §4 provenance logging on every round-trip. It has zero dependency on this repo — nothing was forked. Vector similarity is explicitly deferred (no embedding column exists on `:Case` yet), noted in the tool's own module docstring. |
| [tomasonjo/blogs](https://github.com/tomasonjo/blogs) | Tomaz Bratanic's GraphRAG tutorials (Neo4j) | Practical guidance for building production GraphRAG with Neo4j. | Reference only — useful reading if the vector-similarity leg of GraphRAG gets built. |
| [microsoft/graphrag](https://github.com/microsoft/graphrag) | Microsoft's GraphRAG library (entity extraction, community detection, global search) | Proposed for advanced summarization layers atop Neo4j. | **Not adopted.** No community-detection or global-search layer exists in `agents_runtime/tools/`. |
| [neo4j/neo4j-graphrag-python](https://github.com/neo4j/neo4j-graphrag-python) (corrected from the now-dead `neo4j/neo4j-graphrag`) | Official Neo4j GraphRAG Python package + LangChain integration | Proposed as the primary library for the `GraphRAG` tool. | **Not adopted.** Not in `backend/pyproject.toml`; the native tool above does the same job without it. |
| [cboulanger/ltkg-tools](https://github.com/cboulanger/ltkg-tools) | Legal Theory Knowledge Graph tools + Neo4j integration | Inspiration for doctrine-evolution graph modeling. | Reference only, not adopted. Repo is still active upstream (pushed 2025-07) if doctrine-level graph modeling becomes a priority. |

**What actually happened**: the same pattern as CrewAI — the team judged that a small, purpose-built retriever against the exact schema (`:Case`, `CITES`) was less work than adapting a generic contract-review example, and the audit trail / attribution requirements (constitution §4, §13) were easier to guarantee in code the team wrote than in a fork. If GraphRAG grows a vector-similarity leg, `tomasonjo/blogs` and `neo4j/neo4j-graphrag-python` remain the most relevant references to revisit.

---

## 5. Full-Stack Legal AI / RAG Applications & Examples (Reference Only)

External projects that combine several of the above capabilities. None of these were forked or integrated — they're listed here as prior art worth a skim, not as dependencies or status subjects like the tables above.

| Repository | Description | Relevance to Law AI |
|------------|-------------|-----------------------|
| [thomasbln/graphrag-legal-demo](https://github.com/thomasbln/graphrag-legal-demo) | GraphRAG on legal contracts with Neo4j + an LLM | Frontend graph-visualization and backend retrieval/agent patterns worth comparing against `GraphViewer.tsx` and `graph_rag.py`. |
| [zeroentropy-ai/legalbenchrag](https://github.com/zeroentropy-ai/legalbenchrag) | Retrieval benchmark + example pipelines (also listed in §3) | Evaluation methodology for legal RAG systems. |
| [UKPLab](https://github.com/UKPLab) (org, various repos — no single `legal-reasoning` repo exists there) | Argument mining and legal-reasoning research | Academic baselines if a "Logic Weaver" argument-mining agent is ever built (no such agent exists today). |

Dropped from this section: `alaingilbert/legal-ai`, which the original author had already tagged "(example)" as an uncertain reference — the repo does not exist under that name and never resolved.

---

## 6. Visualization & Interactive Graph Components

For Law AI's knowledge graph explorer.

| Repository | Description | Relevance to Law AI | Status (2026-08) |
|------------|-------------|-----------------------|--------------------|
| [cytoscape/cytoscape.js](https://github.com/cytoscape/cytoscape.js) | Industry-standard graph visualization library | Primary choice for the interactive knowledge graph. | **Adopted.** `cytoscape` is a `frontend/package.json` dependency, live in `components/GraphViewer.tsx`. |
| [xyflow/xyflow](https://github.com/xyflow/xyflow) (rebranded from `wbkd/react-flow`; npm package now `@xyflow/react`, `reactflow` is deprecated) | React component for node-based UIs and graphs | Proposed complement/alternative to Cytoscape for an editable Analysis Studio canvas. | **Removed (BL-20260830-01).** `@xyflow/react` sat in `frontend/package.json` with zero imports and was dropped along with TanStack Query, framer-motion and lucide-react. Still a candidate for an editable Analysis Studio canvas — re-add it in the commit that first imports it. |
| [neo4j/neo4j-browser](https://github.com/neo4j/neo4j-browser) | Official Neo4j graph explorer + visualization plugins | UX reference for exposing Cypher results interactively. | Reference only, not adopted as a dependency. |

---

## 7. Original Action Plan (2026-05) vs. What Shipped

The phased plan below is kept verbatim from the first commit for historical context. It predates specs 001–035; read it as a snapshot of Month-1 intent, not a live roadmap.

### Phase 1 (as planned)
1. Ingestion — integrate `eyecite` + `Blackstone` immediately.
2. Orchestration — adopt `crewAI` + `langgraph`.
3. Evaluation — set up `legalbench` as the CI regression suite on day 1.
4. GraphRAG — fork `neo4j-product-examples/graphrag-contract-review` and adapt to case law.

**What shipped**: 1 and 3 landed close to plan (`eyecite` live, LegalBench nightly in CI — though against a local cache, not the pip package; Blackstone stalled on the spaCy conflict in §2). 2 and 4 did not — LangGraph shipped alone as the engine, and GraphRAG shipped as a native tool, both without the paired/forked dependency originally planned. See §1 and §4 above for why.

### Phase 2 / Phase 3 (as planned, not evaluated here)
Domain-adaptive fine-tuning on `pile-of-law`, CUAD contract features, `microsoft/graphrag` global summarization, `legalbenchrag` tasks, `autogen` debate agents, and UKPLab argument-mining baselines were all proposed for later phases. None have shipped as of 2026-08; see [BACKLOG.md](../BACKLOG.md) for whether any are currently planned.

---

## 8. What's Actually Running Today

Superseding the original "Quick Wins" list, which mixed shipped and never-attempted items without distinguishing them:

| Repo | Actual role |
|------|--------------|
| `eyecite` | Citation parsing in `ingestionapp/services/scout.py`. |
| `langgraph` | Default orchestration engine (`LegalWorkflow`), with `ChatProviderChain` as its LLM. |
| `legalbench` | Nightly CI regression, resolved from a local cache — no pip dependency. |
| `cytoscape.js` | Knowledge graph explorer (`GraphViewer.tsx`). |
| `courtlistener` (API, not the listed GitHub repo) | Primary case-law ingestion source. |

Declared as a dependency but not actually wired into any code path: `crewai` (backend). The frontend half of that pattern is gone — BL-20260830-01 dropped `@xyflow/react`, `@tanstack/react-query`, `framer-motion` and `lucide-react` from `frontend/package.json`. `spacy` is now wired in behind `ENABLE_NER` (`ingestionapp/services/ner.py`); `blackstone` was removed from the `nlp` extra because its `spacy==2.1.8` pin cannot install on Python 3.12. Anyone picking this doc back up should treat `crewai` as the highest-signal "either finish the integration or drop the dependency" candidate.

---

## Summary

The original claim that Law AI could avoid building most of its stack from scratch was **partly right**: citation parsing (`eyecite`), the workflow engine (`langgraph`), the regression harness (`legalbench`), the graph UI (`cytoscape.js`), and the primary data source (`courtlistener`) all came from the open-source ecosystem roughly as planned. The orchestration-crew layer and the GraphRAG retrieval layer did not — both ended up as small, purpose-built implementations on top of the chosen primitives (`law_ai.core.llm`, native Neo4j Cypher) rather than forks of the repos originally scouted here, because the audit/provenance requirements in [constitution.md](constitution.md) §4 were easier to guarantee in first-party code than to retrofit onto someone else's abstraction.

**If you're extending this doc**: keep the Status column current per section rather than letting the whole file drift silently again — this version replaced one that had gone stale for the entire life of the project (first commit to 2026-08, 30+ specs, zero content updates).
