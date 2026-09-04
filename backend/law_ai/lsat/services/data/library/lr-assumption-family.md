---
id: lr-assumption-family
title: The Assumption Family
kind: question-type
level: core
sections: [LR]
summary: Necessary versus sufficient assumptions, the negation test that settles necessary questions, and why the two subtypes need opposite instincts.
concepts: [necessary-assumption, sufficient-assumption, conditional-reasoning, warrant]
archetypes: [lr-necessary-assumption, lr-sufficient-assumption]
prerequisites: [argument-anatomy, conditional-logic-foundations]
related: [lr-strengthen-and-weaken, lr-flaw-family, lr-section-guide]
tags: [assumption, negation-test, gap]
status: reviewed
last_reviewed: 2026-09-03
revision: 1
references: []
---

## Two questions that look identical

Both subtypes ask about something unstated that the argument relies on, and their stems differ by a few words.

- **Necessary assumption.** *The argument depends on assuming which one of the following?* The credited answer is something the argument **needs** — without it the argument collapses. It is usually modest, sometimes almost trivially so.
- **Sufficient assumption.** *Which one of the following, if assumed, allows the conclusion to be properly drawn?* The credited answer is something that, added to the premises, **guarantees** the conclusion. It is usually strong, often stronger than seems necessary.

The instincts are opposite. On necessary questions a choice that seems too weak is often right and a strong one is usually wrong. On sufficient questions a choice that seems too weak is wrong, because it leaves the gap open. See [[concept:necessary-assumption]] and [[concept:sufficient-assumption]].

## Find the gap first

Both subtypes are solved the same way up to the last step: locate the **gap** — the term or idea that appears in the conclusion but not in the premises, or vice versa.

```
Premises talk about:   hours of training completed
Conclusion talks about: competence on the job
Gap:                    training hours ↔ competence
```

Almost every credited answer in this family bridges exactly that gap. Pre-phrasing it before reading the choices turns a five-way judgement call into a matching exercise.

## The negation test

For necessary assumptions only, there is a mechanical check that settles nearly every hard item.

**Negate the choice. If the argument falls apart, the choice is necessary. If the argument survives, it is not.**

Negate precisely — the negation of "all" is "not all", the negation of "will" is "will not necessarily". Over-negating produces a statement so strong that it damages any argument, which makes every choice look correct.

> [!example] Running the negation test
> *The city's new bike lanes have not reduced congestion: traffic speeds on the affected corridors are unchanged since the lanes opened. So the lanes should be removed.*
>
> Gap: from "have not reduced congestion" to "should be removed" — the argument needs congestion reduction to be the standard by which the lanes are judged.
>
> Candidate: *"The bike lanes provide no benefit that would justify keeping them apart from congestion reduction."*
> Negated: *"The bike lanes do provide some other benefit that would justify keeping them."* The argument now fails — removal no longer follows. **Necessary.**
>
> Candidate: *"Traffic speed is the only accurate measure of congestion."*
> Negated: *"Traffic speed is not the only accurate measure."* The argument is weakened but not destroyed; speed can still be evidence. **Not necessary** — this is a strengthener wearing an assumption costume.

## Sufficient assumptions and the conditional bridge

Sufficient-assumption stimuli are frequently conditional. Translate the premises and the conclusion into arrows, and the credited answer is almost always the arrow that completes the chain.

```
Premise:     Applied → Interviewed
Conclusion:  Applied → Hired
Missing:     Interviewed → Hired
```

If the chain has a hole, the answer plugs it exactly. Do not accept a choice that plugs it partially or that runs the wrong direction — `Hired → Interviewed` looks similar and does nothing.

> [!trap] "Sounds like an assumption"
> The most attractive wrong answer in this family is a statement the author would probably endorse, about a topic the argument mentions, that the argument does not actually need. Agreement is not the test. On necessary questions the test is negation; on sufficient questions the test is whether the conclusion now *follows*. Neither test is "does this feel like something they assumed".

> [!drill] Practise the distinction
> Take any assumption item and ask both questions of the credited answer: is it required, and is it enough? A necessary assumption is usually not sufficient, and a sufficient one is often not necessary. Items like [[question:lr-005]] reward noticing which one the stem asked for.

## Key takeaways

- Necessary assumptions are required; sufficient assumptions are enough. Opposite instincts on strength.
- Find the gap between premise terms and conclusion terms before reading any choice.
- Negate the choice to test necessity; if the argument survives, it was not necessary.
- Negate precisely — over-negation makes every choice look required.
- On conditional sufficient-assumption items, the answer is the missing arrow, in the right direction.
