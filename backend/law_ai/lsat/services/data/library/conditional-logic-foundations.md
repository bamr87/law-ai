---
id: conditional-logic-foundations
title: Conditional Logic — Necessary, Sufficient, and the Contrapositive
kind: foundation
level: foundation
sections: [LR, LG]
summary: Translating if/then language into notation, taking contrapositives reliably, chaining conditionals, and recognising the two invalid moves the exam tests constantly.
concepts: [conditional-reasoning, contrapositive, modus-ponens, modus-tollens, necessary-assumption, sufficient-assumption, universal-instantiation]
archetypes: [lr-conditional-inference, lr-contrapositive-inference]
prerequisites: [argument-anatomy]
related: [quantifiers-and-overlap, lr-assumption-family, lg-setup-and-notation, formal-fallacies-catalog]
tags: [conditional, contrapositive, notation, foundations]
status: reviewed
last_reviewed: 2026-09-03
revision: 1
references:
  - title: Stanford Encyclopedia of Philosophy — Classical Logic
    url: https://plato.stanford.edu/entries/logic-classical/
---

## Sufficient and necessary

A conditional says: whenever the first thing holds, the second must hold too. Write it `S → N`.

- **S is sufficient** for N — S happening is enough to guarantee N.
- **N is necessary** for S — without N, S cannot happen.

The two are not interchangeable and the exam's entire conditional apparatus rests on that. "All lawyers passed the bar" gives you `Lawyer → Passed bar`. It does *not* give you that everyone who passed the bar is a lawyer. See [[concept:conditional-reasoning]].

## Translation

The hard part is never the logic. It is turning English into the right arrow.

| English | Notation | Note |
|---|---|---|
| If A, then B | `A → B` | The base case |
| A only if B | `A → B` | "Only if" marks the **necessary** condition |
| All A are B | `A → B` | |
| No A are B | `A → NOT B` | |
| A requires B | `A → B` | "Requires" marks the necessary condition |
| Unless A, B | `NOT A → B` | Negate the "unless" term, it becomes sufficient |
| A only when B | `A → B` | |
| Every time A, B | `A → B` | |

Two of these cause most errors. **"Only if" attaches to the necessary condition** — "you may vote only if you are a member" is `Vote → Member`, not the reverse. And **"unless"** is best handled mechanically: negate the term attached to "unless" and make it the sufficient condition. "The filing is late unless it arrives Friday" becomes `NOT Arrives Friday → Late`.

## The contrapositive

For any `A → B`, the contrapositive `NOT B → NOT A` is logically equivalent — same statement, said from the other end. Take it by **flipping the terms and negating both**.

```
Original:        Enforceable → Both parties signed
Contrapositive:  NOT Both parties signed → NOT Enforceable
```

The contrapositive is where roughly half of all conditional inferences on the exam actually live, because the exam writes stimuli that trigger the negative end. Taking it should be automatic; see [[concept:contrapositive]].

> [!example] Chaining and its contrapositive
> *Every application reviewed in the first round was complete. Only complete applications included a financial statement. Ramirez's application did not include a financial statement.*
>
> Translate:
> ```
> First round      → Complete
> Complete         → Financial statement
> ```
> Chain them: `First round → Complete → Financial statement`, so `First round → Financial statement`.
>
> Contrapositive of the chain: `NOT Financial statement → NOT First round`.
>
> Ramirez has no financial statement. Therefore Ramirez's application was not reviewed in the first round. That is the credited inference, and note that it was only reachable from the contrapositive.

## The two invalid moves

The exam tests these relentlessly, both as wrong answers and as the flaw in flaw questions.

- **Affirming the consequent.** From `A → B` and `B`, concluding `A`. Wrong: B can arrive by other routes. *All lawyers passed the bar. Kim passed the bar. Therefore Kim is a lawyer.* Kim might be a paralegal who sat it.
- **Denying the antecedent.** From `A → B` and `NOT A`, concluding `NOT B`. Wrong for the same reason. *All lawyers passed the bar. Kim is not a lawyer. Therefore Kim did not pass.*

The two *valid* moves are modus ponens (`A → B`, `A`, therefore `B` — see [[concept:modus-ponens]]) and modus tollens (`A → B`, `NOT B`, therefore `NOT A` — see [[concept:modus-tollens]]). Everything else with one conditional and one fact is invalid.

> [!trap] Diagramming everything
> Notation is a tool for stimuli that are genuinely conditional and genuinely tangled. Diagramming a causal argument or a two-sentence stimulus with one conditional in it costs more time than it saves, and a chain of five arrows you built under time pressure is a new source of error. Diagram when there are two or more conditionals to combine, or when "unless" and "only if" appear together. Otherwise, translate in your head and move.

## Key takeaways

- `S → N`: the sufficient condition guarantees, the necessary condition is required. They are not symmetric.
- "Only if" and "requires" mark the necessary term; "unless" means negate-and-make-sufficient.
- The contrapositive flips and negates, and is where a large share of credited inferences live.
- Chain conditionals through shared terms, then take the contrapositive of the whole chain.
- Affirming the consequent and denying the antecedent are the two invalid moves, and the exam tests both constantly.
