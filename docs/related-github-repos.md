# Related GitHub Repositories for LexGraph AI

**Goal**: Identify mature, open-source projects that provide building blocks for LexGraph AI's core capabilities (multi-agent orchestration, legal NLP, knowledge graphs, GraphRAG, legal data pipelines, benchmarks, and visualization). These can be **directly leveraged, forked, or integrated** to accelerate development and avoid reinventing the wheel.

This document organizes repos by category with:
- Short description
- Why it's relevant to LexGraph
- Recommended integration points
- License / Maturity notes

---

## 1. Agent Orchestration & Multi-Agent Frameworks

These are the foundation for LexGraph's agent crews (Ingestion Scout, Legal Analyst, Precedent Hunter, Orchestrator, etc.).

| Repository | Description | Relevance to LexGraph | Integration Points |
|------------|-------------|-----------------------|--------------------|
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | Lightweight, role-based multi-agent orchestration framework (44k+ stars) | Primary choice for LexGraph's "crews" (Analyst + Hunter + Weaver). Simple, fast, and production-ready. | Use as-is for `LegalAnalystCrew`, `PrecedentHunterCrew`. Extend with custom tools (Neo4j, CourtListener). |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | Stateful, graph-based agent workflows with checkpointing, time-travel, and human-in-the-loop (24k+ stars) | Perfect for LexGraph's `Orchestrator` (LangGraph state machines + HITL gates + full audit trails). | Core for complex multi-step legal workflows. Combine with CrewAI (hybrid approach already recommended in AGENTS.md). |
| [microsoft/autogen](https://github.com/microsoft/autogen) | Conversational multi-agent framework with dynamic group chat | Useful for "debate-style" legal reasoning (e.g., Analyst vs. Opposing Counsel simulation). | Secondary — great for advanced "Logic Weaver" or adversarial testing modes. |
| [brainblend-ai/atomic-agents](https://github.com/brainblend-ai/atomic-agents) | Lightweight, structured, developer-centric agent framework | Good alternative if CrewAI/LangGraph feel too heavy. Strong emphasis on typed I/O. | Use for simpler agents or as inspiration for Pydantic-structured outputs. |

**Recommendation**: Stick with **CrewAI + LangGraph hybrid** (already chosen in the architecture). These two repos alone cover 80% of LexGraph's orchestration needs.

---

## 2. Legal NLP, Parsing & Information Extraction

Critical for the Ingestion Scout and entity/relation extraction into Neo4j.

| Repository | Description | Relevance to LexGraph | Integration Points |
|------------|-------------|-----------------------|--------------------|
| [freelawproject/eyecite](https://github.com/freelawproject/eyecite) | State-of-the-art open-source legal citation parser (used by CourtListener) | **Must-use**. Handles Bluebook citations, parallel citations, and court abbreviations perfectly. | Drop-in replacement for custom citation logic in `IngestionScout`. Already in the tech stack. |
| [ICLRandD/Blackstone](https://github.com/ICLRandD/Blackstone) | spaCy pipeline + model trained on UK legal text (NER, sentence segmentation, etc.) | Excellent for legal entity recognition (parties, courts, judges, holdings). | Integrate into ingestion pipeline alongside Eyecite. Fine-tune further on US case law. |
| [HazyResearch/pile-of-law](https://github.com/HazyResearch/pile-of-law) | 256GB curated legal corpus (opinions, regulations, contracts) for domain adaptation | Perfect for continued pre-training or fine-tuning of legal LLMs (Llama-3.1 legal variant). | Use to train/fine-tune a "LexGraph-Legal" model on top of Llama 3.1. |
| [atticusproject/cuad](https://github.com/atticusproject/cuad) | Expert-annotated contract understanding dataset (13 clause types, 500+ contracts) | Gold standard for contract clause extraction & risk assessment agents. | Power a future `ContractRiskAssessor` agent. Use for LegalBench-style eval. |
| [lexpredict/lexpredict-lexnlp](https://github.com/lexpredict/lexpredict-lexnlp) | Older but still useful legal NLP library (feature extraction, contract parsing) | Good reference implementation and feature ideas. | Use for inspiration or specific extractors (dates, monetary amounts, etc.). |

**Recommendation**: Prioritize **Eyecite + Blackstone** for MVP ingestion. Add CUAD for contract features in Phase 2.

---

## 3. Legal Datasets, Benchmarks & Evaluation

Essential for grounding LexGraph in real legal data and measuring reasoning quality.

| Repository | Description | Relevance to LexGraph | Integration Points |
|------------|-------------|-----------------------|--------------------|
| [HazyResearch/legalbench](https://github.com/HazyResearch/legalbench) | 162-task collaborative benchmark for legal reasoning in LLMs (Rule QA, Issue Spotting, etc.) | **Core evaluation harness**. Already referenced throughout LexGraph design. | Run nightly in CI (`scripts/eval-legalbench.sh`). Use as few-shot examples and regression tests for every new agent. |
| [zeroentropy-ai/legalbenchrag](https://github.com/zeroentropy-ai/legalbenchrag) | First open retrieval benchmark specifically for legal contracts and documents | Complements LegalBench with RAG-focused tasks (retrieval quality over legal text). | Extend LegalBench eval pipeline with LegalBench-RAG tasks for GraphRAG validation. |
| [openlegaldata/awesome-legal-data](https://github.com/openlegaldata/awesome-legal-data) | Curated list of 100+ legal datasets, corpora, benchmarks, and tools | The "bible" of open legal data. Includes CourtListener, CAP, legislation.gov.uk, EUR-Lex, SCDB, etc. | Primary reference when adding new data sources. Already heavily used in LexGraph design. |
| [freelawproject/courtlistener](https://github.com/freelawproject/courtlistener) | The actual CourtListener platform + RECAP archive (99%+ of US precedential opinions) | **Primary data source** for LexGraph. | Use their API client and bulk replication tools directly. They also maintain Eyecite. |
| [caselawaccessproject/caselaw-access-project](https://github.com/caselawaccessproject) (or case.law) | Harvard's 6.9M case corpus with bulk downloads | Excellent bulk training / graph population data. | One-time bulk import into Neo4j for seed graph (already planned). |

**Recommendation**: Make **LegalBench** the mandatory regression suite. Every new agent or retrieval improvement must show non-negative delta on relevant tasks.

---

## 4. Knowledge Graphs, GraphRAG & Legal Graph Examples

Neo4j + GraphRAG is a cornerstone of LexGraph's architecture.

| Repository | Description | Relevance to LexGraph | Integration Points |
|------------|-------------|-----------------------|--------------------|
| [neo4j-product-examples/graphrag-contract-review](https://github.com/neo4j-product-examples/graphrag-contract-review) | End-to-end GraphRAG demo on commercial contracts using Neo4j + LLM entity extraction | Almost identical to LexGraph's contract + case analysis workflow. | Fork and adapt the entity extraction + Cypher ingestion pipeline for legal opinions. |
| [tomasonjo/blogs](https://github.com/tomasonjo/blogs) (multiple GraphRAG posts) | Tomaz Bratanic's excellent GraphRAG tutorials (including legal/contract examples) | Best practical guidance on building production GraphRAG with Neo4j. | Follow his patterns for "From Local to Global GraphRAG", community summaries, and hybrid retrievers. |
| [microsoft/graphrag](https://github.com/microsoft/graphrag) | Official Microsoft GraphRAG library (entity extraction, community detection, global search) | Mature implementation of the "GraphRAG" paper. Can complement Neo4j. | Use for advanced summarization layers on top of Neo4j graph (hybrid approach). |
| [neo4j/neo4j-graphrag](https://github.com/neo4j/neo4j-graphrag) (or langchain integrations) | Official Neo4j GraphRAG Python package + LangChain integration | Simplifies building retrievers that combine vector + Cypher. | Primary library for LexGraph's `GraphRAG` tool. |
| [cboulanger/ltkg-tools](https://github.com/cboulanger/ltkg-tools) | Legal Theory Knowledge Graph tools + Neo4j integration | Early example of legal doctrine graphs. | Inspiration for `LegalConcept` nodes and doctrine evolution tracking. |

**Recommendation**: Start with **neo4j-product-examples/graphrag-contract-review** + Tomaz's tutorials. They solve 60-70% of the GraphRAG engineering problems LexGraph faces.

---

## 5. Full-Stack Legal AI / RAG Applications & Examples

Real-world projects that combine several of the above capabilities.

| Repository | Description | Relevance to LexGraph | Integration Points |
|------------|-------------|-----------------------|--------------------|
| [thomasbln/graphrag-legal-demo](https://github.com/thomasbln/graphrag-legal-demo) | Live demo + code for GraphRAG on legal contracts with Neo4j + GPT-4 | Very close to LexGraph's Analysis Studio + Knowledge Graph vision. | Study the frontend (graph visualization) and backend (retrieval + agent) patterns. |
| [HazyResearch/legalbenchrag](https://github.com/HazyResearch/legalbenchrag) (already listed) | Retrieval benchmark + example pipelines | Shows how to evaluate legal RAG systems rigorously. | Adopt their evaluation methodology. |
| [alaingilbert/legal-ai](https://github.com/alaingilbert/legal-ai) (example) | Various legal AI experiments (search, summarization, Q&A) | Good collection of smaller legal NLP scripts. | Borrow specific components (e.g., statute parsing). |
| [UKPLab/legal-reasoning](https://github.com/UKPLab) (various repos) | UKP Lab's legal reasoning and argument mining work | Strong academic baselines for argument mining and fallacy detection (`Logic Weaver` agent). | Use their models/datasets for the Logic Weaver agent. |

---

## 6. Visualization & Interactive Graph Components

For LexGraph's Cytoscape.js / React Flow knowledge graph explorer.

| Repository | Description | Relevance to LexGraph | Integration Points |
|------------|-------------|-----------------------|--------------------|
| [cytoscape/cytoscape.js](https://github.com/cytoscape/cytoscape.js) | Industry-standard graph visualization library (used by many legal tech tools) | **Primary choice** for LexGraph's interactive knowledge graph. | Already in the tech stack. Look at legal-tech examples (e.g., citation networks). |
| [wbkd/react-flow](https://github.com/wbkd/react-flow) | React component for node-based UIs and graphs | Excellent complement or alternative to Cytoscape for the Analysis Studio canvas. | Use for agent workflow visualization or editable argument maps. |
| [neo4j/neo4j-browser](https://github.com/neo4j/neo4j-browser) + visualization plugins | Official Neo4j graph explorer | Great reference for how to expose Cypher results interactively. | Steal UX patterns for LexGraph's graph explorer. |

---

## 7. How to Leverage These Repos in LexGraph AI (Action Plan)

### Phase 1 (MVP – Months 1-3)
1. **Ingestion** — Integrate `eyecite` + `Blackstone` immediately (already in stack).
2. **Orchestration** — Adopt `crewAI` + `langgraph` (already chosen).
3. **Evaluation** — Set up `legalbench` as the CI regression suite on day 1.
4. **GraphRAG** — Fork `neo4j-product-examples/graphrag-contract-review` and adapt to case law.

### Phase 2 (v1.0)
1. Add `pile-of-law` for domain-adaptive fine-tuning.
2. Incorporate `CUAD` for contract features.
3. Use `microsoft/graphrag` for advanced global summarization on top of Neo4j.
4. Add `legalbenchrag` tasks to the evaluation harness.

### Phase 3 (Expansion)
1. Explore `autogen` for multi-agent debate features.
2. Use academic repos (UKPLab) for advanced `Logic Weaver` capabilities.
3. Build on `awesome-legal-data` when adding UK/EU sources.

---

## 8. Quick Wins – Repos You Can Start Using Today

| Repo | One-Line Win |
|------|--------------|
| `eyecite` | Replace any custom citation regex with production-grade parser |
| `legalbench` | Add 5 lines of code to run nightly regression on all agents |
| `crewAI` | Create your first `LegalAnalystCrew` in < 30 minutes |
| `neo4j-product-examples/graphrag-contract-review` | Copy the entity extraction + Neo4j ingestion pattern |
| `pile-of-law` | Start continued pre-training of a legal Llama-3.1 variant |

---

## Summary

LexGraph AI does **not** need to be built from scratch. The open-source ecosystem already provides:

- **~80% of the agent orchestration layer** (CrewAI + LangGraph)
- **~70% of the legal NLP layer** (Eyecite + Blackstone + Pile-of-Law)
- **~60% of the GraphRAG + knowledge graph layer** (Neo4j examples + Microsoft GraphRAG)
- **100% of the evaluation layer** (LegalBench + LegalBench-RAG)
- **Primary data sources** (CourtListener + CAP via awesome-legal-data)

**Next Step**: Create a `libs/` or `vendor/` directory in the LexGraph workspace and begin forking/integrating the highest-priority repos listed above, starting with `eyecite`, `legalbench`, and the Neo4j GraphRAG contract example.

This approach will dramatically reduce time-to-MVP while ensuring LexGraph stands on the shoulders of the best legal + AI open-source work available.