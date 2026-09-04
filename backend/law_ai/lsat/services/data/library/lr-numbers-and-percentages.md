---
id: lr-numbers-and-percentages
title: Numbers, Percentages, and Rates
kind: question-type
level: advanced
sections: [LR]
summary: The quantitative traps — rate versus count, shifting bases, composition effects — and why almost every one of them is solved by asking what the denominator did.
concepts: [percent-vs-number, sampling-flaw, causation-vs-correlation, flaw-in-reasoning]
archetypes: [lr-percent-vs-number, lr-sampling-flaw]
prerequisites: [argument-anatomy]
related: [causal-reasoning-foundations, lr-flaw-family, lr-paradox-and-evaluate]
tags: [percentage, number, rate, statistics, denominator]
status: reviewed
last_reviewed: 2026-09-03
revision: 1
references: []
---

## The one question that solves most of them

When a stimulus mixes a percentage with a count, ask: **what happened to the denominator?**

A percentage is a ratio. It can move because the numerator moved, because the denominator moved, or both. An argument that treats a change in rate as a change in count — or the reverse — has ignored the denominator, and that is the flaw. See [[concept:percent-vs-number]].

```
Rate = numerator / denominator

Rate up   + denominator down   → numerator may be unchanged or falling
Rate down + denominator up     → numerator may be unchanged or rising
Count up  + denominator up more → rate falls
```

## The four recurring traps

- **Percentage stated, number concluded.** *"The share of graduates entering public-interest law doubled, so more graduates are entering public-interest law."* Only if the class size held steady. If the class halved, the count is flat.
- **Number stated, percentage concluded.** *"More residents were treated for asthma this year, so asthma is more prevalent."* Only if the population held steady.
- **Two populations compared by rate.** A hospital with a higher mortality *rate* may be taking the harder cases. Rates across differently-composed groups compare the groups' composition as much as their performance.
- **Composition shift (the average that moved without anyone moving).** The average changes because the mix changed. This one is subtle enough to earn its own example.

> [!example] The average that moved without anyone moving
> *The average tenure of employees at the firm fell from nine years to six over the past year. Retention must be deteriorating.*
>
> Ask what happened to the denominator — here, who is in the pool. Suppose the firm hired forty new people and nobody left. Every existing employee's tenure went *up* by a year, and the average still fell sharply, because the pool now contains forty people with tenure near zero.
>
> The conclusion does not follow, and the flaw is a composition shift, not bad arithmetic. A weaken choice reading *"the firm expanded its workforce by 40% during the year"* is the credited answer.

## Where these show up

Quantitative traps rarely appear as their own question type. They arrive inside other families:

- As the **flaw** in a flaw question — *"treats a change in proportion as though it established a change in absolute number."*
- As the **resolution** of a paradox — two facts that conflict until you notice one is a rate and the other a count. See [[article:lr-paradox-and-evaluate]].
- As a **weakener** in a causal argument, by showing the base population changed. See [[article:causal-reasoning-foundations]].

## Reading the language precisely

The exam is careful with its quantitative vocabulary, and so should you be.

| Phrase | What it is |
|---|---|
| *more*, *fewer*, *the number of* | A count |
| *higher*, *the rate of*, *the proportion of*, *the share of* | A ratio |
| *the average*, *the median* | A summary of a distribution, sensitive to composition |
| *twice as likely* | A ratio of ratios — says nothing about either absolute risk |

That last row matters. "Twice as likely" is compatible with a risk moving from one in a million to two in a million. A conclusion about how many people are affected does not follow from a relative risk.

> [!trap] Assuming the base held steady
> The stimulus almost never tells you what the denominator did. That silence is the point — the argument needs the base to be stable and does not say so, which makes "the population was unchanged" a classic unstated assumption. On assumption questions with a statistical stimulus, check for exactly that choice; see [[article:lr-assumption-family]].

## Key takeaways

- Ask what the denominator did. It solves most of the family.
- Rates and counts do not imply each other unless the base is stable.
- Rate comparisons across differently-composed groups compare composition too.
- An average can move sharply with no individual changing — composition shifts.
- Relative risk says nothing about absolute numbers; "twice as likely" can be tiny either way.
