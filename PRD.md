# Law AI
## Product Requirements Document (PRD)

**Version:** 1.0  
**Date:** April 29, 2026  
**Status:** Draft for Review  
**Owner:** Product Team (AI Legal Systems Initiative)  
**Related:** [Technical Proposal](docs/law-ai-proposal.md) | [Architecture](docs/architecture.md) | [Constitution](docs/constitution.md)

---

## 1. Executive Summary

**Law AI** is an open-source, AI-agent-orchestrated legal intelligence platform that empowers lawyers, law students, and legal researchers to understand, analyze, organize, and master complex legal content through intelligent multi-agent workflows, persistent knowledge graphs, and interactive visualizations.

The platform integrates:
- **Specialized AI Agent Crews** (built with CrewAI + LangGraph) for legal research, case analysis, precedent mapping, logic validation, and adaptive education.
- **Neo4j-powered Knowledge Graphs** that automatically connect cases, statutes, holdings, citations, and legal doctrines.
- **Graph-grounded retrieval** — lexical fulltext search combined with graph (`CITES`) traversal expansion for precise, explainable answers, with vector/hybrid GraphRAG as a planned but not-yet-implemented extension (see [§6.3](#63-data--model-requirements)).
- **Public Legal Data Pipelines** pulling from CourtListener, Harvard Caselaw Access Project (CAP), RECAP, legislation.gov.uk, and other open sources.
- **Dedicated LSAT & Bar Prep Lab** with grounded explanations linked to the live knowledge graph.
- **Modern Interactive Frontend** featuring draggable knowledge graphs (Cytoscape.js), real-time agent monitoring, and collaborative workspaces.

**Primary Goal:** Democratize high-quality legal AI by making it fully open-source, auditable, and extensible, with a local-only runtime mode (Ollama, no third-party processing) available for confidentiality-bound work — lowering barriers for solo practitioners, public defenders, law schools, and access-to-justice initiatives.

**Target Launch:** MVP in 3 months; v1.0 in 6 months. *(Status: this doc's original April 29, 2026 timeline has passed — see [§10](#10-milestones--roadmap) for a status note.)*

---

## 2. Problem Statement

Legal professionals and students face:
- **Information overload**: 6.9M+ U.S. cases (CAP), millions of dockets (RECAP), rapidly evolving statutes across 50+ jurisdictions.
- **Fragmented tools**: Proprietary platforms (Westlaw, Lexis) are expensive and black-box; open tools lack deep reasoning or persistent memory.
- **Repetitive cognitive load**: Manual IRAC analysis, citation chasing, precedent hunting, and argument mapping consume hours per matter.
- **Education gap**: LSAT/Bar prep resources are siloed from real case law; explanations often lack grounding in primary sources.
- **Trust & Auditability**: Current AI legal tools provide no provenance for outputs, raising ethical and professional responsibility concerns (ABA Model Rules 1.1, 1.6).

**Opportunity**: Mature open-source components now exist — CrewAI/LangGraph for orchestration, Neo4j + GraphRAG for legal knowledge representation, Eyecite/Blackstone for legal NLP, LegalBench for evaluation, and high-quality public datasets (CourtListener, Pile-of-Law). This is the moment to build the legal profession's first truly open, agentic, graph-native intelligence layer.

---

## 3. Goals & Success Metrics

### Primary Goals
1. Reduce time-to-insight for case analysis by ≥60% (measured via user studies & agent trace analytics).
2. Achieve ≥85% accuracy on LegalBench legal reasoning tasks for core agent crews (baseline: current SOTA open models).
3. Build a living, queryable knowledge graph covering ≥500k high-impact cases within 12 months (starting with SCOTUS + 5 Circuits + key state supreme courts).
4. Enable 10,000+ monthly active users (lawyers + students) in Year 1 with self-hostable open-source distribution.
5. Produce fully auditable AI outputs with source citations and agent decision traces (supporting professional ethics compliance).

### Key Performance Indicators (KPIs)
- **Accuracy**: LegalBench aggregate score; human expert blind review of generated briefs (target: >80% "useful with minor edits").
- **Efficiency**: Average session time to produce a usable case brief or memo.
- **Graph Quality**: Citation graph completeness (measured against SCDB and manual validation); query latency <800ms for hybrid retrieval.
- **Adoption**: GitHub stars/forks, Docker pulls, active self-hosted instances (via optional telemetry).
- **Education Impact**: LSAT practice module completion rates; pre/post assessment score improvement (target: +15–20 points equivalent).

### Success Criteria for MVP
- End-to-end ingestion of 50k+ cases into Neo4j with accurate citation + holding extraction.
- Functional Analyst + Precedent Hunter agent crew producing IRAC briefs with >70% expert approval rate.
- Interactive Cytoscape graph explorer working on real data.
- Basic LSAT module with 3 full practice sections + AI explanations.
- Docker Compose deployment running with the Claude-default provider chain; a fully offline mode is available by pinning `LLM_PROVIDER_CHAIN=ollama` (required, not optional, for confidentiality-bound data).

---

## 4. Target Users & Personas

| Persona | Description | Primary Jobs-to-be-Done | Pain Points Addressed |
|---------|-------------|-------------------------|-----------------------|
| **Solo Practitioner / Small Firm Lawyer** | 1–10 attorney firm handling civil litigation, family, or immigration | Rapid case evaluation, precedent research, memo drafting under billable-hour pressure | Expensive research tools; time spent on repetitive analysis; difficulty tracking evolving law |
| **Public Defender / Legal Aid Attorney** | High-volume, resource-constrained, mission-driven | Quick identification of favorable precedent in similar fact patterns | Lack of budget for premium databases; need for transparent, citable AI assistance |
| **Law Student / Future Lawyer** | 1L–3L preparing for classes, exams, moot court, or LSAT/Bar | Deep doctrinal understanding, efficient outlining, practice question explanations | Siloed study aids disconnected from primary sources; generic explanations |
| **Law Professor / Researcher** | Teaching or empirical legal studies | Building course materials, analyzing citation networks, hypothesis testing on case outcomes | Manual data collection; lack of integrated analysis + visualization tools |
| **In-House Counsel / Compliance** | Contract review, regulatory monitoring, risk assessment | Clause extraction, obligation tracking, jurisdiction-specific updates | Volume of contracts; keeping current with multi-jurisdictional changes |

**Accessibility & Inclusion**: Free self-host option; low-resource mode (quantized models); keyboard-navigable graph UI; planned internationalization (Spanish, Mandarin legal corpora in later phases).

---

## 5. Key Features (Prioritized)

### Phase 1 – MVP (P0 – Must Have)
**5.1 Data Ingestion & Knowledge Graph Foundation**
- Scheduled + on-demand ingestion from CourtListener API (opinions, dockets, judges) and bulk CAP downloads.
- Automated citation extraction (Eyecite), legal NER (Blackstone spaCy), and LLM-powered holding/entity/relation extraction into Neo4j.
- Core graph schema: `Case`, `Statute`, `Holding`, `Citation`, `Jurisdiction`, `LegalConcept`, `Party`, `Judge` nodes + `CITES`, `OVERRULES`, `HAS_HOLDING`, `APPLIES_IN`, `DISTINGUISHED_BY` relationships.
- Incremental sync with deduplication and provenance metadata (source URL, ingest timestamp, agent version).

**5.2 Core Agent Crews (CrewAI + LangGraph Orchestration)**
- **Ingestion Scout**: Fetches, parses, extracts, validates, and commits to graph with human approval gate for low-confidence extractions.
- **Legal Analyst**: Produces structured IRAC briefs, issue spotting, argument mapping, risk assessment with mandatory source citations.
- **Precedent Hunter**: Graph + embedding traversal to surface on-point, analogous, and distinguishing authorities; explains why each is relevant.
- **Orchestrator (LangGraph)**: Stateful workflow engine supporting multi-step plans, branching, checkpointing, time-travel debugging, and human-in-the-loop (HITL) approval nodes.

**5.3 Interactive Knowledge Graph Explorer**
- Cytoscape.js / React Flow visualization of subgraphs.
- Click-to-expand, filter by jurisdiction/date/concept, highlight citation paths, shortest-path precedent chains.
- Export subgraph as PNG/SVG/PDF or Cypher query.

**5.4 Analysis Studio**
- Split-pane interface: document/case viewer | live agent chat & trace log | structured output panel | linked graph view.
- All agent outputs persisted as versioned artifacts with full prompt/context used.

**5.5 Basic LSAT Learning Lab**
- 4 full official-style practice sections (public domain + validated synthetic).
- Immediate AI explanations tied to graph nodes/rules.
- Performance dashboard (accuracy by question type: LR Flaw/Strengthen/Assumption, RC, LG).

### Phase 2 – v1.0 (P1 – Should Have)
- Full multi-agent collaboration (Analyst + Hunter + Logic Weaver running in parallel with shared memory).
- Advanced GraphRAG with community summaries, global context, and LegalBench-RAG evaluation harness.
- User workspaces, project folders, shared read/write graphs, commenting on nodes.
- Full LSAT/Bar adaptive engine with spaced repetition, skill-gap radar charts, and personalized study plans linked to doctrine subgraphs.
- Public "Discover" feed of newly ingested high-impact opinions with one-click import.
- Export to Word/PDF with proper Bluebook citations and agent provenance footer.
- Self-hosting one-click installer (Coolify / Docker Compose + optional Supabase/Keycloak).

### Phase 3 – Expansion (P2 – Nice to Have / Future)
- UK/EU support (legislation.gov.uk, EUR-Lex, BAILII, Cambridge Law Corpus).
- Fine-tuned legal LLM (continued pretraining on Pile-of-Law + LegalBench feedback loop).
- Browser extension + Word/Outlook plugins for "analyze this clause/case" in context.
- Agent Marketplace (community-contributed crews and prompt packs, versioned and rated).
- Mobile PWA with offline graph subset sync.
- Empirical legal research module (regression analysis on case outcomes, citation network metrics).

---

## 6. Technical Requirements & Architecture

> The stack described here is a snapshot; [docs/constitution.md](docs/constitution.md) §2 ("Tech Stack (Locked)") is the enforced, authoritative version and should be treated as the tie-breaker if this section drifts. See also [docs/architecture.md](docs/architecture.md) for the current implementation-level architecture.

### 6.1 High-Level Architecture (see diagram)
```
Public Legal Sources (CourtListener, CAP, legislation.gov.uk, EUR-Lex)
          ↓ (Ingestion Scout Agent)
Backend Layer
  • Django 5 (ASGI/daphne) + Django REST Framework (REST) + Channels (WebSocket for agent streaming) + Celery (background jobs)
  • CrewAI + LangGraph (orchestration & state machines); LangChain (langchain-core) provides ChatProviderChain, the LangGraph-native LLM wrapper
  • PostgreSQL (users, projects, run history, LSAT metrics, LangGraph checkpoints)
  • Neo4j Community (knowledge graph — lexical fulltext + graph traversal retrieval today; no vector index yet)
  • LLM provider chain (law_ai.core.llm): Claude via Claude Code OAuth → Claude via ANTHROPIC_API_KEY → Ollama (local, last-tier fallback)
          ↓
Frontend (Next.js + TypeScript + Tailwind + shadcn/ui)
  • Interactive Cytoscape.js knowledge graph
  • Analysis Studio (real-time agent traces)
  • LSAT Lab (adaptive practice + analytics)
  • Collaboration & sharing layer
```

### 6.2 Core Technology Stack (All Open Source)
- **Backend**: Python 3.12+, Django 5 (ASGI/daphne), Django REST Framework, Channels, Celery, Pydantic v2 (domain layer), CrewAI, LangGraph, LangChain (`langchain-core` — a core dependency, not tool abstractions only; backs `ChatProviderChain`, the default LLM for `LegalWorkflow`)
- **Databases**: PostgreSQL 16, Neo4j 5.x Community
- **LLM Runtime**: ordered provider chain (`LLM_PROVIDER_CHAIN`), Claude default (Claude Code OAuth, then `ANTHROPIC_API_KEY`), then xAI Grok (subscription OAuth, spec 050), Ollama as the local last-tier fallback — required, not optional, for data under a confidentiality obligation forbidding third-party processing (see [docs/constitution.md](docs/constitution.md) §1)
- **NLP & Legal Parsing**: Eyecite, Blackstone (spaCy pipeline), pdfplumber, Unstructured.io
- **Frontend**: Next.js (App Router), React, TypeScript, Tailwind, shadcn/ui, TanStack Query, Cytoscape.js, React Flow, Recharts — see [docs/constitution.md](docs/constitution.md) §2 for the locked major versions
- **Auth**: API-key authentication (`law_ai.core.auth.ApiKeyAuthentication`); RBAC/SSO are not yet implemented
- **DevOps**: Docker Compose (full local stack, Docker-first for all dev/test/lint commands via `make`), GitHub Actions

### 6.3 Data & Model Requirements
- **Primary Corpora**: CourtListener (real-time + bulk), CAP bulk Parquet (6.9M cases), Pile-of-Law (256GB for domain adaptation), LegalBench (162 tasks for continuous evaluation).
- **Embedding Models**: Not yet implemented — retrieval today is lexical fulltext search plus graph (`CITES`) traversal expansion only (`backend/law_ai/agents_runtime/tools/graph_rag.py`). No embedding column exists on `:Case` yet; `chromadb` is a declared dependency with zero current usage. Vector/hybrid GraphRAG remains planned, not shipped.
- **Evaluation**: LegalBench harness integrated into CI, pinned to Ollama regardless of the product-runtime provider chain (so benchmark numbers stay comparable run-to-run); nightly regression on held-out tasks. LegalBench-RAG is aspirational pending the vector work above.

### 6.4 Security, Privacy & Compliance
- **Runtime LLM default**: Claude (Claude Code OAuth token, then `ANTHROPIC_API_KEY`) is the default provider, with xAI Grok as a further hosted tier; requests route through a third party — Anthropic, or xAI once authorised — unless the deployment pins `LLM_PROVIDER_CHAIN=ollama`. That local-only pin is **required**, not optional, for data under a confidentiality obligation forbidding third-party processing (see [docs/constitution.md](docs/constitution.md) §1, amended 2026-08-11).
- **Auditability**: Every agent decision, prompt, tool call, and retrieval logged through `core.provenance` (supporting ABA ethics opinions on AI use).
- **Access Control**: Currently API-key authentication only (`law_ai.core.auth.ApiKeyAuthentication`); workspace-level RBAC and SSO/SAML are not yet implemented.
- **Data Minimization**: Only store user-uploaded documents + derived graph nodes they explicitly approve.
- **Disclaimers**: Prominent "AI Assistant – Not Legal Advice" + "Verify all citations" in every output; one-click "report issue" to maintainers.

---

## 7. AI Agent Specifications (Detailed)

### Agent Roles & Responsibilities

> This table states the target agent roster. For which of these are actually shipped vs. still conceptual, see [docs/agent-roles.md](docs/agent-roles.md), which distinguishes "Current Agents (MVP)" from "Planned Agents (Post-MVP)." As of this writing, **Ingestion Scout, Legal Analyst, and Precedent Hunter are implemented** (`backend/law_ai/agents_runtime/crews/`), along with `TestSynthesizer` and `TopicFrontier` (LangGraph workflows) and `LSATContentAuthor` (an autonomy-gated agent, not a general "Educator"). **Logic Weaver and a standalone Orchestrator/Educator agent do not exist yet** — orchestration today is the `LegalWorkflow` LangGraph `StateGraph`, not a dedicated Orchestrator agent.

| Agent | Role Type | Core Responsibilities | Required Tools | Output Schema | Evaluation Method |
|-------|-----------|-----------------------|----------------|---------------|-------------------|
| **Ingestion Scout** | Data | Fetch/parse/extract/validate/commit legal documents to graph | CourtListener client, Eyecite, Blackstone, PDF parsers, Neo4j writer | Structured extraction + confidence score + proposed Cypher | Manual review queue + automated LegalBench-style entity F1 |
| **Legal Analyst** | Reasoning | IRAC brief, issue spotting, argument tree, risk assessment | Graph retriever, LegalBench prompts, structured output (Pydantic) | JSON: {issues, rules, application, conclusion, citations, risks} | Expert blind review; LegalBench "Rule QA" & "Issue Spotting" tasks |
| **Precedent Hunter** | Retrieval | Surface on-point, analogous, and distinguishing cases with explanations | Neo4j Cypher (shortest path, community detection), lexical fulltext + citation graph expansion (vector similarity planned, not yet implemented) | Ranked list + natural language justification + distinguishing factors | Citation recall@10 vs SCDB gold; human relevance rating |
| **Logic Weaver** *(planned, not shipped)* | Reasoning | Build argument maps, detect fallacies, strength scoring, counter-argument generation | Custom reasoning prompts, entailment models, LegalBench NLI tasks | Argument graph (nodes = propositions, edges = support/attack) | Agreement with expert annotations; fallacy detection precision |
| **Educator (LSAT/Bar)** *(closest shipped analog: `LSATContentAuthor`, a differently-scoped, HITL-gated autonomy agent)* | Education | Generate/validate practice questions, explain answers with graph grounding, adaptive sequencing | Question bank + generator, performance DB, concept subgraph retriever | Explanation + linked cases/rules + next recommended drill | Pre/post test delta; item response theory calibration |
| **Orchestrator** *(today: the `LegalWorkflow` LangGraph `StateGraph`, not a standalone agent)* | Meta | Plan decomposition, agent routing, state management, HITL gates, workflow checkpointing | LangGraph state machine, shared memory, human approval nodes | Executable plan + execution trace + final synthesized artifact | Workflow success rate; trace auditability score |

**Prompt Engineering Standards**:
- All prompts versioned in repo with Git SHA.
- Chain-of-Thought + structured output enforced.
- "Grounding first" principle: retrieval always precedes generation; "I don't know" explicitly allowed with confidence threshold.
- LegalBench tasks used as few-shot exemplars and regression tests.

---

## 8. User Experience & UI Requirements

### 8.1 Information Architecture
- **Dashboard** (landing after login): Recent analyses, graph health metrics, "Start New Analysis" CTA, trending ingested cases, LSAT streak counter.
- **Library** (global + personal): Hybrid search (semantic + graph + metadata filters), bulk actions, import from public feed.
- **Analysis Studio** (primary workspace): Persistent tabs per matter; real-time streaming of agent thoughts; editable structured outputs with "regenerate section" buttons.
- **Graph Explorer** (full-screen or side panel): Force-directed or hierarchical layouts, timeline scrubber, jurisdiction heat map, export controls.
- **Learning Lab**: Separate mode with timer, question palette, explanation panel that highlights relevant graph nodes, progress analytics.

### 8.2 Interaction Principles
- **Progressive Disclosure**: Start simple (chat + basic graph) → advanced (full crew orchestration, custom Cypher, agent prompt editing).
- **Explainability by Default**: Every claim in an output has a clickable citation that highlights the exact node/span in the source document or graph.
- **Human-in-the-Loop First**: Low-confidence extractions or high-stakes recommendations require explicit approval before committing to shared graph.
- **Keyboard & Screen-Reader Accessible**: Full ARIA support; Cytoscape graph keyboard-navigable with text alternatives.

### 8.3 Performance Targets (Client-Side)
- Graph visualization of 5k–10k nodes: <1.5s initial render, 60fps pan/zoom.
- Agent streaming: first token <800ms, full brief <25s (local 70B model on RTX 4090-class hardware).
- Search: hybrid results <600ms p95.

---

## 9. Non-Functional Requirements

| Category | Requirement | Target Metric | Notes |
|----------|-------------|---------------|-------|
| **Privacy** | Local-first execution | 100% offline capable | No telemetry unless user opts in |
| **Security** | Input sanitization, prompt injection resistance | OWASP LLM Top 10 compliance | Red-team testing in CI |
| **Reliability** | Agent workflow success rate | >98% for defined tasks | Automatic retry + fallback to simpler agent |
| **Scalability** | Concurrent users per self-hosted instance | 50–200 (depending on hardware) | Horizontal scaling guide for cloud deploys |
| **Performance** | End-to-end case brief generation | <30s (local), <8s (cloud GPU) | Quantized models supported |
| **Maintainability** | Code coverage + type safety | ≥75% coverage on backend (`--cov-fail-under=75`, per [backend/pyproject.toml](backend/pyproject.toml) and [docs/constitution.md](docs/constitution.md) §3); strict TypeScript + mypy --strict | Pre-commit hooks + CI |
| **Legal/Ethical** | Audit log completeness | 100% of agent actions logged | Immutable, exportable for bar complaints |
| **Open Source** | License & contribution model | MIT/AGPL dual; CLA required for large contributions | Clear governance in CONTRIBUTING.md |

---

## 10. Milestones & Roadmap

> **Status note (2026-08-11):** this section's dates are from the original April 29, 2026 draft and have not been reconciled against actual delivery. Spec 034 (Claude-default LLM provider chain) and spec 035 (LangChain/LangGraph promoted to core dependencies) both shipped 2026-08-11 and are not reflected in the phase breakdown below — see `specs/034-claude-default-runtime/` and `specs/035-langchain-first-class/` (or the current `specs/` index) for what has actually landed. Treat the phase content as directional, not a committed schedule.

**Q2 2026 (MVP – Internal Alpha)**
- Weeks 1–4: Core ingestion pipeline + Neo4j schema + Eyecite/Blackstone integration (50k cases)
- Weeks 5–8: Analyst + Precedent Hunter crews + basic LangGraph orchestrator + Analysis Studio
- Weeks 9–12: Cytoscape graph explorer + basic LSAT module + Docker Compose release

**Q3 2026 (v1.0 Public Beta)**
- Full multi-agent collaboration + GraphRAG + LegalBench CI integration
- User accounts, workspaces, sharing
- Public documentation, onboarding tutorial, "Getting Started" video series
- Community Discord + GitHub Discussions launch

**Q4 2026 – 2027 (Scale & Ecosystem)**
- UK/EU data + multilingual support
- Fine-tuned legal model release (weights + eval report)
- Agent Marketplace v1
- Mobile PWA + browser extension
- First law school pilot programs (curriculum integration grants)

---

## 11. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Legal accuracy / hallucinations** | Medium | High | Strict GraphRAG grounding + mandatory citations + LegalBench regression + prominent disclaimers + expert review queue for high-stakes outputs |
| **Citation graph errors (wrong overruling, missed negative treatment)** | Medium | High | Eyecite + LLM validation + human approval for "OVERRULES" edges; partnership with Free Law Project for data quality feedback loop |
| **Compute cost / accessibility for self-hosters** | High | Medium | Quantized models (4-bit/8-bit), CPU fallback, clear hardware recommendations, optional cheap cloud GPU marketplace integration |
| **Data freshness lag** | Low | Medium | Daily CourtListener sync cron + webhook support; "last updated" badges everywhere |
| **Adoption by risk-averse legal professionals** | High | High | Strong audit trail + ethics alignment (ABA opinions) + law school endorsements + "verify" one-click workflow |
| **Open source sustainability** | Medium | Medium | Clear governance, paid enterprise support tier (optional), grants from legal tech foundations, university partnerships |

---

## 12. Appendices

### A. Key Open Data Sources & Licenses
- CourtListener / Free Law Project – Open (API + bulk)
- Caselaw Access Project (Harvard) – Open bulk download
- Pile-of-Law (Hugging Face) – Open corpus for training
- LegalBench & LegalBench-RAG – Open evaluation harness (Stanford HazyResearch)
- legislation.gov.uk, EUR-Lex – Open Government Licence / EU equivalent
- Eyecite, Blackstone – Open source (Free Law Project / spaCy)

### B. Evaluation Benchmarks
- LegalBench (162 tasks across 6 legal reasoning types)
- LegalBench-RAG (retrieval-focused)
- Internal expert-annotated gold sets for IRAC, precedent relevance, and graph edge correctness

### C. Glossary
- **GraphRAG**: Retrieval-Augmented Generation over a knowledge graph (Cypher + vector hybrid).
- **IRAC**: Issue, Rule, Application, Conclusion – standard legal analysis framework.
- **HITL**: Human-in-the-Loop.
- **LegalBench**: Collaborative open benchmark for legal reasoning in LLMs.

### D. References
- Free Law Project: https://free.law/
- Caselaw Access Project: https://case.law/
- LegalBench paper: https://arxiv.org/abs/2308.11462
- Neo4j GraphRAG legal examples: neo4j-product-examples/graphrag-contract-review
- CrewAI & LangGraph documentation

---

## 13. AI Development Orchestration Capabilities (GitHub Copilot + Claude Code)

GitHub Copilot and Claude Code are the **sanctioned AI development orchestrators** for this repo (see [docs/constitution.md](docs/constitution.md) §1 and [AGENTS.md](AGENTS.md) "Development Orchestration"). The capabilities below are exercised through Copilot Chat (Ask / Edit / Agent modes) and the GitHub Copilot coding agent; Claude Code (CLI / IDE) runs the same AO-SDLC chain and `/evolve` from the shared [prompts/](prompts/). This dev-orchestration layer (which AI edits this repo) is independent of the product-*runtime* LLM layer (which model answers end users): as of specs 034 and 050, the product runtime is the ordered chain `LLM_PROVIDER_CHAIN=claude_code,anthropic_api,xai,ollama` — Claude by default, xAI Grok as a hosted fallback, Ollama as the local last tier (docs/constitution.md §1). Do not conflate the two when reading "which model" into this section.

1. **Spec-driven workflow execution** — Copilot Chat Agent mode runs the AO-SDLC chain ([/specify](prompts/specify.md) → [/clarify](prompts/clarify.md) → [/plan](prompts/plan.md) → [/tasks](prompts/tasks.md) → [/implement](prompts/implement.md)) end-to-end, halting at HITL gates.
2. **Autonomous BACKLOG advancement** — [/evolve](prompts/evolve.md) picks the highest-priority `BL-*` item and ships it; the GitHub Copilot coding agent runs the same chain in the cloud when an issue is assigned to `@copilot`.
3. **Workspace-aware refactoring** — Copilot Edits performs multi-file changes against `backend/law_ai/` and `frontend/` while honoring [.github/copilot-instructions.md](.github/copilot-instructions.md).
4. **Custom instructions enforcement** — Repo-level [.github/copilot-instructions.md](.github/copilot-instructions.md) plus path-scoped `*.instructions.md` files keep every Copilot turn aligned with [AGENTS.md](AGENTS.md).
5. **Subagent fan-out** — Copilot's `runSubagent` (and the `Explore` agent) parallelizes audits and read-only research without polluting the main chat.
6. **Pull-request review** — Copilot Code Review and `@copilot` PR comments handle first-pass review; humans approve at the spec gate and the merge gate.
7. **Inline completions** — Always-on Copilot completions in VS Code, governed by the same instructions file (no per-IDE configuration drift).
8. **CI integration** — GitHub Actions ([.github/workflows/](.github/workflows/)) invokes Copilot-authored validators (`spec_validator.py`, `backlog_lint.py`) and the weekly [evolve workflow](.github/workflows/evolve.yml).
9. **Provenance hooks** — Every Copilot-generated change must route through `core.provenance` so audit logs capture the same metadata regardless of which Copilot surface produced it.
10. **Documentation generation** — Copilot drafts ADRs, README updates, and prompt templates; humans curate.

**Forbidden**: Cursor, Continue.dev, Aider, Codex, Gemini CLI, or any other third-party coding agent. Adding their config files (`.cursorrules`, `.continuerc.json`, etc.) is a constitution violation. (Claude Code is sanctioned — its [CLAUDE.md](CLAUDE.md) / `.claude/` config is allowed.)

**Recommended Workflow**: Open the workspace in VS Code with the GitHub Copilot extension; Copilot Chat Agent mode auto-loads [.github/copilot-instructions.md](.github/copilot-instructions.md) and the prompts under [prompts/](prompts/). For unattended cloud cycles, enable the GitHub Copilot coding agent in repo settings and let the weekly `evolve` workflow file issues for `@copilot`.

---

**Document Control**  
Next Review: May 15, 2026  
Approval: Product, Engineering, Legal Ethics Review (external counsel)  
Distribution: GitHub (public), internal Notion, law school partners

*This PRD is a living document. All features and metrics are subject to validation with real users and legal domain experts during the alpha phase.*