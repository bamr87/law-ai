# AO-SDLC Guide

This file is superseded by **[AO-SDLC_Outline_Guide.md](../AO-SDLC_Outline_Guide.md)** (v2.0, 2026-08-11) at the repo root — the canonical AO-SDLC operating guide. It replaced the v1.0 Grok xAI research-synthesis template that used to live at this path (a generic, vendor-neutral outline with projected metrics, not a description of this repository). This file is kept only as a redirect so old links don't 404; do not restock it with a second copy of the guide.

Read the root guide directly. It's organized as:

| Section | Covers |
|---|---|
| §1 The Loop at a Glance | BACKLOG → `/specify` → `/clarify` → `/plan` → `/tasks` → `/implement` → gates → PR → follow-ups |
| §2 Governance Layer | `docs/constitution.md`, `AGENTS.md`, `BACKLOG.md` and what enforces each |
| §3 Spec-Driven Core | `specs/NNN-slug/{spec,plan,tasks}.md`, `spec_validator.py`, `backlog_lint.py` |
| §4 Runtime Architecture | 4.1 the LLM provider chain (`core/llm/`), 4.2 LangChain/LangGraph as core stack (spec 035), 4.3 the implemented agent roster |
| §5 Autonomy Levels | v1's four-level model mapped onto `/evolve`, `make autonomy-run`, and the constitution's HITL invariants |
| §6 Docker-First Execution | why every gate runs via `make` / `docker compose run --rm` |
| §7 Quality Gates & CI | the `.github/workflows/ci.yml` job table, plus nightly/integration/evolve workflows |
| §8 Observability & Audit | provenance, audit sinks, Phoenix/OTel tracing, the LLM health endpoint |
| §9 Validation Playbook | the live, dated end-to-end check run against the real provider chain |
| §10 Extending the System | how to add a feature, an agent, a provider, or raise autonomy |
| Appendix A / B | file map and glossary |

See [docs/ao-sdlc.md](ao-sdlc.md) for how these phases map onto Law AI's concrete files and agents.
