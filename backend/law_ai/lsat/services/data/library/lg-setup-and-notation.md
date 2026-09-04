---
id: lg-setup-and-notation
title: Game Setup and Notation
kind: technique
level: core
sections: [LG]
summary: Choosing the right board for the game, a compact and unambiguous notation for every common rule, and the setup errors that cost whole games.
concepts: [sequencing, grouping-game, conditional-reasoning, contrapositive, elimination-grid]
archetypes: [lg-acceptability, lg-grouping]
prerequisites: [lg-section-guide, conditional-logic-foundations]
related: [lg-game-types, lg-inference-and-frames]
tags: [notation, diagram, setup, board]
status: reviewed
last_reviewed: 2026-09-03
revision: 1
references: []
---

## Pick the board from the structure

Before writing a single rule, decide what the game is asking you to build. Three boards cover the large majority.

- **Slots in a line** — when entities are ordered or assigned to numbered positions. Draw the positions as a row of underscores.
- **Groups as columns** — when entities are distributed among categories. Draw one column per group, with capacity marked if the game gives it.
- **A grid** — when two attributes are assigned to each entity, or when entities are matched across two dimensions.

Getting this wrong is the most expensive setup error, because every rule then has to be recorded in a shape that does not hold it well. If a game distributes six interns among three departments across two shifts, that is a grid, and drawing it as three columns loses the shift dimension.

## Notation for the common rules

Compactness matters: notation you have to decode is notation that slows you down.

| Rule in English | Notation |
|---|---|
| G before J | `G … J` |
| G immediately before J | `GJ` |
| K and L consecutive, order unknown | `[KL]` |
| M not in slot 3 | `3: NOT M` |
| Exactly one of P or Q | `P xor Q` |
| If R then S | `R → S` with `NOT S → NOT R` written beneath |
| R and S not together | `R → NOT S` |
| At least one of T, U | `NOT T → U` |

Two habits are worth building. **Always write the contrapositive** underneath a conditional rule — the game will trigger the negative end, and deriving it under pressure is where errors come from. And **put negative rules on the board**, not in the margin: a "not M" written under slot three is seen; one written in a list is looked up.

> [!example] A complete setup
> *Six files — P Q R S T V — are shelved on six numbered shelves, one per shelf. Q is shelved somewhere before T. If P is on shelf two, then S is on shelf five. R and V are on consecutive shelves. P is not on shelf one.*
>
> ```
> Inventory: P Q R S T V   (6 entities, 6 slots, one each)
>
>  __  __  __  __  __  __
>   1   2   3   4   5   6
>   ^ NOT P
>
> Rules:  Q … T
>         P2 → S5        (contrapositive: NOT S5 → NOT P2)
>         [RV]
> ```
>
> Everything is now visible in one glance: the slot restriction sits on the board where it applies, the conditional carries its contrapositive, and the block is bracketed. No rule needs to be re-read from the prompt again.

## Setup errors that cost games

- **Mis-translating "unless" or "only if".** A reversed conditional produces a board that is wrong in a way you will not notice until three questions have gone against you. Translate deliberately; see [[article:conditional-logic-foundations]].
- **Assuming one-to-one.** Not every game places exactly one entity per slot. Check whether entities repeat, whether slots can be empty, and whether the counts match — a game with seven entities and five slots behaves completely differently.
- **Losing an "at least" or "at most".** Capacity constraints are rules and belong on the board, written above the group they govern.
- **Rewriting the rules instead of notating them.** Copying rules out in sentences produces a second prompt to read, not a diagram.

> [!trap] Not checking the numbers
> Before starting the questions, count. How many entities, how many slots, can slots be empty, can entities repeat? A surprising share of hard games are hard entirely because of a numeric constraint stated in one clause of the setup — "at least two but no more than four" — that most readers absorb as flavour text.
>
> The numbers frequently produce the game's most powerful inference before you have combined a single pair of rules. See [[article:lg-inference-and-frames]].

## Key takeaways

- Choose the board first: linear slots, group columns, or a grid.
- Notate compactly; write every conditional's contrapositive beneath it.
- Put negative and capacity constraints on the board, not in a margin list.
- Check whether the game is one-to-one before assuming it.
- Count entities against slots before answering anything — the numbers often carry the key inference.
