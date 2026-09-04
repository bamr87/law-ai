---
id: lg-game-types
title: Game Types and Question Types
kind: question-type
level: core
sections: [LG]
summary: Sequencing, grouping, selection, distribution and hybrid games, plus the question types each one asks and the shortcut that answers the first one every time.
concepts: [sequencing, grouping-game, in-out-selection, numeric-distribution, hybrid-game, max-min, rule-substitution, could-be-true-except, must-be-true, elimination-grid]
archetypes: [lg-acceptability, lg-must-be-true, lg-could-be-true-except, lg-local-conditional, lg-in-out-selection, lg-numeric-distribution, lg-max-min, lg-hybrid, lg-rule-substitution, lg-grouping]
prerequisites: [lg-setup-and-notation]
related: [lg-inference-and-frames, lg-section-guide]
tags: [game-types, sequencing, grouping, selection, acceptability]
status: reviewed
last_reviewed: 2026-09-03
revision: 1
references: []
---

## The game types

- **Sequencing.** Entities in order. Rules are relative (*G before J*), blocks (*K and L adjacent*), or fixed (*M is third*). See [[concept:sequencing]].
- **Grouping.** Entities distributed among named categories, with capacity rules. See [[concept:grouping-game]].
- **In/out selection.** A single yes-or-no: which entities are chosen. Rules are almost entirely conditional, and the contrapositive does most of the work. See [[concept:in-out-selection]].
- **Numeric distribution.** The counts themselves are the puzzle — how many go in each group, before you decide who. See [[concept:numeric-distribution]].
- **Hybrid.** Two dimensions at once, usually order plus a category. Build a grid; do not try to hold the second dimension mentally. See [[concept:hybrid-game]].

## The question types

**Acceptability.** *Which one of the following could be a complete and accurate list?* Always the first question, and never solved by reasoning. Take each rule in turn and scan the five choices for a violation. One rule usually kills one choice, and four rules clear the board in under forty seconds. See [[concept:elimination-grid]].

**Must be true / could be true.** Answered from the master diagram plus your up-front inferences. If your inferences were thorough these are lookups; if not, they are five separate mini-games.

**Could be true EXCEPT / must be false.** Read the stem twice. Four choices are possible and one is impossible, and losing track of the polarity is the commonest error in the section. See [[concept:could-be-true-except]].

**Local conditional.** *If R is fourth, which one of the following must be true?* Redraw a **fresh** copy of the board with the new condition, work its consequences, answer, then discard it. Never write a local condition onto the master diagram.

**Maximum / minimum.** *What is the greatest number of…* Usually a numeric-distribution question in disguise; work the counts before the placements. See [[concept:max-min]].

**Rule substitution.** *Which one of the following, if substituted for the third rule, would have the same effect?* The hardest question type in the section. The credited answer must produce exactly the same set of possible boards — no more, no fewer. See [[concept:rule-substitution]].

> [!example] Acceptability by elimination
> *Rules: Q before T. If P is second, S is fifth. R and V consecutive. P not first.*
>
> ```
> (A) P Q R V S T   → P is first. Violates rule 4. Out.
> (B) Q P R V T S   → P second, S is sixth not fifth. Violates 2. Out.
> (C) Q R V P T S   → check all: Q before T yes; P not second so rule 2
>                      is inert; RV consecutive yes; P not first yes. Survives.
> (D) T Q R V P S   → T before Q. Violates rule 1. Out.
> (E) Q R P V T S   → R and V not consecutive. Violates 3. Out.
> ```
>
> Answer (C), reached in about thirty seconds with no diagram work at all. Rule-by-rule scanning across the choices is faster than choice-by-choice checking against the rules, because one rule can eliminate several choices in a single pass.

## Order of attack

1. **Acceptability first** — it is free, and the surviving choice is a valid board you can reuse as a hypothetical later.
2. **Local conditionals next** — each one is self-contained and produces a concrete board, and those boards answer global questions afterwards.
3. **Global must/could questions last** — by then you have three or four real boards on the page, and a single counterexample kills a "must be true" choice instantly.

That ordering is not stylistic. Doing globals first means reasoning abstractly; doing them last means checking against boards you already built.

> [!trap] Carrying a local condition forward
> A local question says "if R is fourth". Two questions later you are still treating R as fourth. This is the most common way to lose a whole game, and it is entirely preventable: draw local conditions on a separate line, and cross them out the moment the question is answered.

## Key takeaways

- Five game types; identify which one before notating, because it decides the board.
- Acceptability questions are pure elimination — scan by rule, not by choice.
- Local conditionals get a fresh board that is discarded immediately after.
- Answer in order: acceptability, locals, then globals against the boards you built.
- EXCEPT and must-be-false stems invert the task; misreading polarity is the top error.
