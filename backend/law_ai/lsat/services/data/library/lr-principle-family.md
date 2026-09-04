---
id: lr-principle-family
title: Principle Questions
kind: question-type
level: core
sections: [LR]
summary: Moving between abstract rules and concrete cases in both directions, and the conditional structure hiding inside almost every principle.
concepts: [principle-application, conditional-reasoning, universal-instantiation, warrant]
archetypes: [lr-principle-apply]
prerequisites: [conditional-logic-foundations]
related: [lr-parallel-family, lr-assumption-family, writing-argumentative-method]
tags: [principle, rule, application, conditional]
status: reviewed
last_reviewed: 2026-09-03
revision: 1
references: []
---

## Two directions

A principle is a general rule. Principle questions move between the rule and a case, and the stem tells you which direction. See [[concept:principle-application]].

- **Identify the principle.** *Which one of the following principles, if valid, most helps to justify the reasoning above?* You are given a case and asked for the rule that licenses it.
- **Apply the principle.** *Which one of the following judgements most closely conforms to the principle stated above?* You are given a rule and asked which case it governs.

A third variant appears occasionally: two principles are stated and you must find the case they jointly decide, or the case where they conflict.

## Every principle is a conditional

This is the whole technique. A principle says: *when these conditions hold, this follows.* Rewrite it in the notation from [[article:conditional-logic-foundations]] and the question becomes mechanical.

```
Principle: "A public official should recuse herself from any decision
            in which she has a personal financial interest."

Notation:  Personal financial interest → Should recuse
```

Now the direction of the stem tells you what to check.

- **Applying** the principle means the case must satisfy the **sufficient** condition. A case where the official has a financial interest is governed. A case where she recused herself is *not* governed — that is the necessary condition, and satisfying it triggers nothing.
- **Justifying** a conclusion means the principle's sufficient condition must be met by the facts and its necessary condition must be what the argument concluded.

> [!example] Applying, with the trap visible
> *Principle: A reviewer should disclose any relationship with an author whose work she evaluates.*
>
> Notation: `Relationship with author → Should disclose`.
>
> **Conforms:** Chen evaluates a manuscript by a former colleague and discloses the connection. Sufficient condition met, necessary condition satisfied.
>
> **Does not conform, and is the standard trap:** Okonjo discloses that she has no relationship with the author she is reviewing. She has satisfied the *necessary* condition without the sufficient one triggering. The principle says nothing about her case, so it neither approves nor forbids what she did — and a choice describing it as conforming is testing whether you reversed the arrow.

## Matching scope exactly

The credited answer matches the principle on every dimension, and the exam builds distractors by shifting one:

- **Who it governs.** A principle about *public officials* does not decide a case about a private contractor.
- **What it requires.** *Should disclose* is not *must recuse*, and *is permitted to* is not *is obligated to*.
- **How strongly.** *Always*, *never*, *ordinarily*, *in most cases* — a principle qualified with "ordinarily" cannot decide a case conclusively.

> [!trap] The morally satisfying answer
> Principle questions often involve conduct, and one choice usually describes behaviour that is clearly right or clearly wrong. That choice is frequently not governed by the stated principle at all.
>
> The test is not "was this person's conduct appropriate" but "does *this rule* decide *this case*". A principle can be silent about genuinely bad behaviour, and when it is, the choice is wrong.

## Justifying a conclusion

On the identify direction, treat the question as a sufficient-assumption problem in disguise — see [[article:lr-assumption-family]]. Find the gap between the facts and the judgement, and choose the principle that bridges exactly that gap.

The common error is choosing a principle that is *too broad*. A rule that would justify the conclusion and a hundred other things is still sufficient, so breadth alone is not disqualifying — but a rule broad enough to be obviously false, or one whose sufficient condition the facts never establish, is. Check both halves: does the case trigger it, and does it deliver the conclusion?

## Key takeaways

- Rewrite every principle as a conditional before doing anything else.
- Applying: the case must meet the sufficient condition. Meeting the necessary one triggers nothing.
- Justifying: treat it as a sufficient assumption — bridge the gap between facts and judgement.
- Match on who, what, and how strongly; distractors shift exactly one of those.
- The question is whether the rule decides the case, not whether the conduct was admirable.
