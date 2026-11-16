<!-- kit: governance v0.1.0 -->
# 0002 — Missions

- **Status:** proposed
- **Date:** 2026-11-16
- **Proposed by:** Grok Bot (agent), at the maintainer's request
- **Ratified by:**
- **Affects:** constitution §1; PRD §1.1, §4
- **Supersedes:** none
- **Related:** [prd.md](../prd.md) §1.1, §3, §4, §5.5, §5.8; [philosophy.md](../philosophy.md); [lawmode-migration.md](../lawmode-migration.md)

## Context

Constitution §1 Mission Alignment was a one-line pointer to AGENTS.md — "privacy-aware, auditable, graph-native legal intelligence with HITL on high-stakes paths" — plus the product-runtime LLM policy. The fleet governance kit expects §1 to say who the repo serves and what it is for. The maintainer asked for mission statements in the same form as fredgar-ai amendment 0002: multiple missions, capped at three, comprehensive and epic, aiming to be the ultimate open home for the domain. Mission 1 is the maintainer's own wording, adapted to this repo: provide data, tools, resources and transparency for all stakeholders, legal professionals and the general public. The ambition is the direction, not a claim that the work is already finished.

## Amendment

Retitle constitution §1 **Missions**. Place the following at the head of §1. The product-runtime LLM policy (spec 034, ADR 0007) stays in §1 after this text, unchanged:

Law AI's direction is to become the ultimate open home for all things legal — data, tools, resources and transparency, gathered in one place that anyone can inspect and reuse.

1. **Provide data, tools, resources and transparency for all stakeholders, legal professionals and the general public.** Prospective and current law students, practicing lawyers, public defenders and legal-aid attorneys, professors and researchers, in-house counsel, builders, and the general public are first-class audiences. The aim is a shared, open commons: the same sources, the same tools, and the same trail of evidence for everyone.
2. **Make every public legal fact queryable, reproducible and auditable, and let AI explain it only with citations.** The path starts with open case law, statutes and dockets (CourtListener, CAP, RECAP and other public corpora), a citation knowledge graph, and the LSAT learning lab, and widens from there. The graph and its provenance log are the system of record; every holding, citation and enrichment claim keeps a path to its evidence; authority is never treated as correctness; optional AI stays grounded in retrieved source text rather than replacing it. A fully local runtime remains reachable for privileged work.
3. **Put that record in every learner's, builder's and practitioner's hands, and make legal analysis and legal-risk review effortless and auditable.** Serve it through the API, the interactive studio, the self-hosted stack and the public LSAT lab, so students can study against primary sources, lawyers can produce cited IRAC and precedent maps, and developers can review code for legal risk — an open toolkit for working with all things legal.

These missions set the course; they do not claim the work is finished. They serve the PRD goals in §3 and the users in §4: open and auditable legal intelligence, a living citation graph, LSAT and legal study, and a local-only mode for confidentiality-bound work. The earlier one-line mission — privacy-aware, auditable, graph-native legal intelligence with HITL on high-stakes paths — is absorbed into these three. Every feature must trace to them.

_Source: [prd.md](../prd.md) §1.1._

## Consequences

Agents and reviewers judge fit against these three missions before inventing scope, treating them as the direction of the repo rather than a description of what already ships. The product-runtime LLM policy remains in §1, so existing "see §1" references for the provider chain still hold. The same text is added as PRD §1.1; the existing executive-summary body becomes §1.2 Purpose. PRD §4 names the general public as a first-class audience. The PRD problem statement, goals, feature catalog and invariants are unchanged. This PR also aligns the README and AGENTS.md taglines and short purpose lines with the missions and links them to constitution §1. Cross-references that said "§1 Mission Alignment" now say "§1 Missions".
