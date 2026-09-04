---
id: lg-inference-and-frames
title: Inferences and Frames
kind: technique
level: advanced
sections: [LG]
summary: The up-front work that turns a fifteen-minute game into a six-minute one — how to combine rules, when to split the game into frames, and how to know you are done.
concepts: [numeric-distribution, sequencing, grouping-game, conditional-reasoning, contrapositive, max-min]
archetypes: [lg-must-be-true, lg-numeric-distribution, lg-max-min]
prerequisites: [lg-setup-and-notation]
related: [lg-game-types, quantifiers-and-overlap]
tags: [inference, frames, hypotheticals, technique]
status: reviewed
last_reviewed: 2026-09-03
revision: 1
references: []
---

## Where inferences come from

After the board is drawn, spend two minutes deriving what the game did not say. Inferences come from a short list of sources, and running the list is more reliable than waiting for insight.

- **Shared entities.** Two rules mentioning the same entity almost always combine. `Q … T` and `T … V` give `Q … T … V`, which fixes Q out of the last two slots and V out of the first two.
- **Blocks against restrictions.** A two-slot block plus a barred slot eliminates several placements at once.
- **The numbers.** Count entities against capacity. A game with seven entities and groups of at most three, three, and two has no slack anywhere.
- **Contrapositives.** Every conditional's negative end. Games are written to trigger them.
- **Most-restricted entity or slot.** Whichever element appears in the most rules is where the game is decided. Start there.

> [!example] Chaining and counting together
> *Five lectures — F G H J K — are given on five consecutive days. G is before H. J is before G. K is not on day one or day five.*
>
> Chain: `J … G … H`. Three entities in a fixed relative order.
>
> Now count. J needs at least two entities after it, so J is on day one, two, or three. H needs at least two before it, so H is on day three, four, or five. K is barred from days one and five.
>
> Combine: if J is not on day one, the only remaining candidates for day one are F or G — and G cannot be first because J precedes it. So **day one is J or F**, always. That single inference answers a large share of the question set and took about forty seconds.

## Frames

When a game has a rule that forces a small number of possibilities, draw them all out. Two or three complete boards beat one abstract diagram, because every subsequent question becomes a lookup rather than a derivation.

Frame when you see:

- A rule with exactly two options — *H is first or last*, *either P or Q is selected, not both*.
- A block with only two or three viable positions.
- A numeric split with limited options — *the groups have sizes 3-2-2 or 3-3-1*.

Do not frame when the branching runs to five or more boards. Past three or four, drawing them costs more than the questions save.

```
Rule: H is first or last.

Frame 1:  H __ __ __ __ __       Frame 2:  __ __ __ __ __ H
          then RV block fits              then RV block fits
          2-3, 3-4, 4-5, 5-6              1-2, 2-3, 3-4, 4-5
```

Each frame then absorbs the remaining rules, and most questions resolve to "true in both frames" (must be true), "true in one" (could be true), or "true in neither" (cannot be true).

## Knowing when to stop

Two minutes on inference, then move. The signal to stop is that a full pass through the sources above produces nothing new. Test takers who keep hunting for one more inference lose more time than the inference would have saved.

Conversely, the signal that you stopped too early is finding yourself doing the same derivation inside two different questions. If you deduce something twice, it belonged on the master diagram.

> [!trap] Building hypotheticals you never reuse
> A local question produces a valid, complete board. Most people answer the question and erase it. That board is evidence: it is a concrete counterexample that can instantly kill a "must be true" choice on a later question.
>
> Keep every complete board you build, numbered, off to the side. By the fourth question you usually have three of them, and global questions become a scan across boards rather than fresh reasoning.

## Key takeaways

- Work the inference sources as a checklist: shared entities, blocks against restrictions, numbers, contrapositives, most-restricted element.
- Frame when a rule forces two or three possibilities; do not frame past four.
- Two minutes of up-front inference, then stop — but if you derive something twice, it belonged on the master board.
- Keep every complete hypothetical you build; they answer later global questions for free.
- The most-constrained entity or slot is where every game is decided. Start there.
