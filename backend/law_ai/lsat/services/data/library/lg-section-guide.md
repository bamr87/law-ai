---
id: lg-section-guide
title: Logic Games — Section Guide
kind: section-guide
level: core
sections: [LG]
summary: Analytical Reasoning left the scored exam in August 2024, and remains the best available trainer for the constraint tracking that conditional Logical Reasoning rewards.
concepts: [sequencing, grouping-game, elimination-grid, must-be-true, could-be-true-except, conditional-reasoning]
archetypes: []
prerequisites: [conditional-logic-foundations]
related: [lg-setup-and-notation, lg-game-types, lg-inference-and-frames, lsat-exam-architecture]
tags: [logic-games, analytical-reasoning, section-guide]
status: reviewed
last_reviewed: 2026-09-03
revision: 1
references:
  - title: LSAC — About the LSAT
    url: https://www.lsac.org/lsat/taking-lsat/about-lsat
---

## Status: unscored, still useful

LSAC removed Analytical Reasoning from the scored LSAT in August 2024. A modern administration has no Logic Games section, and no study plan should treat it as a scoring priority. See [[article:lsat-exam-architecture]].

It stays in this library and in the drill bank for one concrete reason: it is the cleanest available practice at **holding several formal constraints at once and drawing consequences from them**. That is precisely the skill that conditional Logical Reasoning questions test under time pressure, and games train it in a purer, more diagnosable form than LR does — when you get a game wrong you can see exactly which inference you failed to make.

Treat it as a gym, not as an exam section. Twenty minutes on a grouping game is a legitimate way to spend a study session in phase 1 or 2 of [[article:building-a-study-plan]]; it is not a legitimate substitute for LR drilling in phase 3.

## The shape of a game

A game gives you an **inventory** of entities, a **structure** to place them into, and a set of **rules** constraining the placement. Then it asks four to seven questions, most of which are about what must, could, or cannot be true.

```
Setup:  Seven applicants — F G H J K L M — are interviewed
        one at a time, in order, on seven consecutive days.
Rules:  G is interviewed before J.
        H is interviewed either first or last.
        K and L are interviewed on consecutive days.
```

The work splits three ways, and the proportions matter: roughly 40% of your time on the setup and notation, 30% on up-front inferences, 30% on the questions. People who rush the setup pay for it on every question; people who never move past the setup run out of clock.

## The three skills

- **Notation.** Turning rules into marks you can see at a glance. See [[article:lg-setup-and-notation]].
- **Inference.** Combining rules to derive what the game did not tell you — the step that separates a fifteen-minute game from a six-minute one. See [[article:lg-inference-and-frames]].
- **Question technique.** Knowing which question types can be answered from the master diagram and which require a hypothetical. See [[article:lg-game-types]].

> [!example] Why the up-front inference matters
> Take the setup above and add: *M is interviewed on day four.*
>
> Work the combination before answering anything. H is first or last. K and L are a consecutive block, and day four is taken by M — so the KL block fits in days one-two, two-three, five-six, or six-seven. If H takes day one, KL cannot use days one-two, and so on.
>
> Two minutes spent here collapses most of the question set into lookups. Skipping it means rebuilding this reasoning inside every single question, five times over, under the clock.

## What transfers to the scored exam

- **Conditional discipline.** Games force correct handling of "unless", "only if", and contrapositives, because a mis-translated rule produces a board that visibly fails. See [[article:conditional-logic-foundations]].
- **Exhaustive case analysis.** The habit of asking "what are all the possibilities" is directly the habit that answers must-be-true and cannot-be-true questions in LR.
- **Distinguishing must from could.** Games make the difference between *must be true* and *could be true* concrete, and that distinction decides a whole LR family. See [[article:lr-inference-family]].

> [!tip] How much to spend
> If Logic Games is enjoyable and you have time, use it in phase 1 and 2 as conditional-logic training. If it is not, skip it entirely — nothing on the scored exam requires it, and the same reasoning is trainable through conditional LR drilling. The one thing not to do is spend phase 3 on it, which is where scored-section pacing has to be built.

## Key takeaways

- Analytical Reasoning left the scored exam in August 2024; it is a trainer, not a section.
- Setup and up-front inference deserve roughly 70% of the time spent on a game.
- Games train constraint tracking, conditional translation, and must-versus-could in a diagnosable form.
- Use it early in a study plan, if at all; never at the expense of phase-3 LR pacing work.
- Skipping it entirely is a defensible plan. Substituting it for LR drilling is not.
