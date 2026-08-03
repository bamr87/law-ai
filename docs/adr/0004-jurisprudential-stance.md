# ADR 0004 — Jurisprudential Stance (Thrasymachus as Descriptive Premise)

- **Status**: accepted
- **Date**: 2026-08-03
- **Spec**: _none — documentation/philosophy amendment, no code surface_
- **Constitution clauses amended**: new [§13 Jurisprudential Honesty](../constitution.md#13-jurisprudential-honesty-power-aware-outputs); reinforces [§1 Mission Alignment](../constitution.md#1-mission-alignment), [§4 Provenance & Audit](../constitution.md#4-provenance--audit-non-negotiable), [§5 HITL](../constitution.md#5-human-in-the-loop-hitl-requirements)

## Context

Law AI's stated principles ([AGENTS.md](../../AGENTS.md) § "Core Principles") cover openness, privacy, auditability, legal accuracy, graph-native retrieval, and HITL. They describe *how* the system should behave but never state *what the project believes legal data is*. That gap has practical consequences for a graph-native retrieval system:

- Citation centrality (in-degree, PageRank) is trivially computable over the `(:Case)-[:CITES]->(:Case)` network described in [data-model.md](../data-model.md), and reads naturally as an authority score. It is more accurately a measure of which litigants could afford to litigate and appeal.
- "Legal Accuracy: all outputs must be grounded in retrieved sources" is silent on what the retrieved corpus *is*. Published opinions are a non-random, victor-authored sample of disputes (Priest & Klein 1984; Galanter 1974).
- Nothing in the constitution told a reviewer to reject a feature that presents corpus consensus as neutral ground truth.

Thrasymachus' claim in *Republic* I.338c — "justice is nothing else than the interest of the stronger" — names this precisely. Adopted carefully, it converts several existing rules from hygiene into consequences of a stated position, and gives reviewers a test to apply to new features.

## Decision

Adopt the Thrasymachean thesis **as a descriptive premise about the legal record, and explicitly reject it as a normative goal for the system**, recording the full argument in a new [docs/philosophy.md](../philosophy.md) — now the philosophical source of record, sitting above [constitution.md](../constitution.md) in the same way [AGENTS.md](../../AGENTS.md) sits above it for standards.

The split is the substance of the decision:

- **Descriptive half (adopted).** The corpus is the record of what the stronger parties have gotten courts to say. Selection effects, repeat-player advantage, victor-authored opinions, and coverage gaps are properties of our input data, not distortions to be assumed away.
- **Normative half (rejected).** Socrates' craft argument (*Republic* I.341c–342e) — a craft serves its subject, not its practitioner — governs the system's design. The beneficiary is the user, especially the under-resourced one. A system that serves whoever operates it fails the mission in [AGENTS.md](../../AGENTS.md).

Seven obligations (P1–P7) follow in [philosophy.md](../philosophy.md) §4 and are enforced as constitution §13: label authority signals as power measures; attribute every rule to its issuing authority; surface who prevailed where the record supports it; report absence explicitly; never present corpus consensus as verified truth; keep decision power with the human; and do not let the platform itself become the stronger party.

Constitution §13 adds two hard rejection rules — a spec may not present a citation/centrality signal as a correctness score, and may not state a legal proposition without its issuing authority — plus a review question ("who is the stronger, and what does this feature do for them?") applied at the spec gate.

## Consequences

- **Reviewers gain a concrete test.** Spec review and PR review now ask the §13 question. Two feature shapes are rejectable on sight: authority-as-correctness ranking, and unattributed statements of law.
- **Existing rules are re-grounded, not changed.** §1 (open-source runtime), §4 (provenance, soft-delete), §5 and §12-I1 (HITL, no auto-merge) keep their current text; philosophy.md §5 records why each is a consequence of the stance. No gate is loosened and no tech-stack lock moves.
- **New follow-up work is implied, not mandated here.** Disposition / prevailing-party metadata on `:Case`, explicit "thin result set" signalling in GraphRAG, and a UI treatment for citation-count labelling do not exist today. They are recorded in [BACKLOG.md](../../BACKLOG.md) (`BL-20260803-01` … `-05`) rather than smuggled into this ADR as silent requirements.
- **Documentation surface grows by one required doc.** `docs/philosophy.md` joins the `REQUIRED_DOCS` list in [tests/test_docs.py](../../tests/test_docs.py), so deletion or stubbing trips CI.
- **Cost.** One more document in the read-first chain, and a class of otherwise-attractive ranking features becomes harder to ship. Both are intended.

## Alternatives considered

1. **Do nothing — leave the principles as-is.** Rejected: the citation-centrality confusion is a live risk in a graph-native product, and "legal accuracy" alone does not catch it.
2. **Adopt the thesis wholesale, normatively.** Rejected: as a norm it licenses building a tool that serves whoever holds it, which contradicts the mission and inverts §5/§6 (HITL, human authority). The descriptive/normative split is what makes the thesis usable.
3. **Add a bullet to AGENTS.md and stop there.** Rejected as insufficient — the reasoning is what makes the obligations reviewable, and a single bullet cannot carry the descriptive/normative distinction without reading as cynicism.
4. **Encode it as an agent output filter (down-rank "powerful" parties).** Rejected as actively harmful: it installs a different stronger party and violates the "no political filter" limit in [philosophy.md](../philosophy.md) §6. Labelling, not filtering.
5. **Write it as a spec package under `specs/`.** Rejected: there is no code surface. The constitution's own amendment clause names an ADR as the mechanism for changing it; the implied code work is backlogged for a future `/specify` cycle.

## Supersedes / Superseded by

- Supersedes: none.
- Superseded by: none.
