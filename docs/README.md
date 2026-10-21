# law-ai documentation

Human docs beyond the README, one topic per file. Start with the root [`README.md`](../README.md); agent instructions and the exact commands are in the root agent file.

| Where | What |
| --- | --- |
| [`adr/`](adr/) | This directory contains Architecture Decision Records (ADRs) for Law AI. |
| [`agent-roles.md`](agent-roles.md) | This document defines every agent that exists or is planned for Law AI. |
| [`ao-sdlc-guide.md`](ao-sdlc-guide.md) | This file is superseded by AO-SDLC_Outline_Guide.md (v2.0, 2026-08-11) at the repo root — the canonical AO-SDLC operating guide. |
| [`ao-sdlc.md`](ao-sdlc.md) | This page maps the AO-SDLC operating guide (v2.0, 2026-08-11) onto the concrete files, agents, and tools in this repository. |
| [`api-examples.md`](api-examples.md) | Quick-reference curl examples for every public REST endpoint. |
| [`architecture.md`](architecture.md) | Key Design Decisions: - Agent Orchestration: plain Python classes with async def run(input: dict) -> BaseModel for single-agent work (no CrewAI — see… |
| [`constitution.md`](constitution.md) | Org-wide, non-negotiable standards for every spec, plan, and implementation produced by humans or AI agents in this repo. |
| [`data-model.md`](data-model.md) | Law AI's Neo4j knowledge graph + Postgres quarantine. |
| [`data-sources.md`](data-sources.md) | Open, machine-readable corpora used by Law AI. |
| [`django-conventions.md`](django-conventions.md) | Closes BL-20260503-18. |
| [`e2e-testing.md`](e2e-testing.md) | The unit suites stop at the boundary. |
| [`images/`](images/) | 56 entries |
| [`legalbench.md`](legalbench.md) | Living evaluation manual for Law AI. |
| [`llm-provider-chain.md`](llm-provider-chain.md) | Every product-runtime model call in Law AI goes through one ordered chain: law_ai.core.llm tries each provider named in LLM_PROVIDER_CHAIN until one… |
| [`local-ai.md`](local-ai.md) | Companion to specs/010-local-ai-stack/. |
| [`lsat-answer-shuffling.md`](lsat-answer-shuffling.md) | BL-20260606-01. |
| [`lsat-library.md`](lsat-library.md) | The library is the LSAT module's prose layer: long-form, cross-linked study material on how the exam is built, what each section demands, how each… |
| [`lsat-playbooks.md`](lsat-playbooks.md) | A playbook is how one LSAT question type is recognised and solved: the stem phrasing that gives it away, the task in one line, the strategies that… |
| [`lsat-solve-guides.md`](lsat-solve-guides.md) | A solve guide walks one bank question: the steps a strong solver takes, in order, with the board they build as they go. |
| [`lsat-static.md`](lsat-static.md) | The LSAT module ships to learners through two surfaces. |
| [`lsat-synthesis.md`](lsat-synthesis.md) | A second way to grow the question bank: derive the item from a formal model, prove the key, and vary only the surface. |
| [`philosophy.md`](philosophy.md) | What we believe law is, what that makes a legal-intelligence system responsible for, and which of those beliefs are binding rules rather than… |
| [`related-github-repos.md`](related-github-repos.md) | Goal: Identify mature, open-source projects that provide building blocks for Law AI's core capabilities (multi-agent orchestration, legal NLP,… |
| [`security.md`](security.md) | Closes BL-20260430-10 and BL-20260503-16. |
| [`ui-ux-review.md`](ui-ux-review.md) | A repeatable pass over Law AI's application shell, navigation, and interaction contract. |
| [`ui-ux.md`](ui-ux.md) | Current-state inventory of every user-facing surface, the two styling idioms that actually ship, and the governance target for a maintainable design… |
