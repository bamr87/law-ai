---
id: quantifiers-and-overlap
title: Quantifiers — All, Most, Some, and What Combines
kind: foundation
level: advanced
sections: [LR]
summary: The three quantifiers, what each one licenses, which pairs combine into a valid inference, and why "most" plus "most" is the exam's favourite overlap question.
concepts: [universal-instantiation, must-be-true, most-strongly-supported, cannot-be-true]
archetypes: [lr-must-be-true, lr-cannot-be-true]
prerequisites: [conditional-logic-foundations]
related: [lr-inference-family, formal-fallacies-catalog]
tags: [quantifier, some, most, overlap, foundations]
status: reviewed
last_reviewed: 2026-09-03
revision: 1
references: []
---

## The three quantities

- **All** — every member, no exceptions. Equivalent to a conditional: *all A are B* is `A → B`. See [[concept:universal-instantiation]].
- **Most** — more than half. On the exam this means strictly greater than 50%, and it includes "all" as a special case: if all A are B, then most A are B is also true.
- **Some** — at least one. This is the quantifier people get wrong, because ordinary English uses "some" to mean "a few but not all". On the exam **some means one or more, up to and including every single one**.

That last point matters constantly. "Some senators voted for the bill" is true if all one hundred did. An answer choice saying "some A are B" is not contradicted by evidence that all A are B.

## What reverses and what does not

**Some** and its negation-free relatives are symmetric. If some A are B, then some B are A — at least one thing is both, and which side you look from does not change that. The same is true of "no": if no A are B, then no B are A.

**All** and **most** are not symmetric. *All A are B* tells you nothing about how much of B is A. *Most A are B* likewise: most surgeons are university graduates, but almost no university graduates are surgeons.

## Which combinations are valid

This is the whole content of the topic. Two quantified statements sharing a common term either license an inference or they do not.

| First | Second | Shared term | Valid conclusion |
|---|---|---|---|
| All A are B | All B are C | B | All A are C |
| All A are B | Some A are C | A | Some B are C |
| Most A are B | Most A are C | A | Some B are C |
| Most A are B | All B are C | B | Most A are C |
| Some A are B | All B are C | B | Some A are C |
| Some A are B | Most B are C | B | Nothing |
| Most A are B | Most B are C | B | Nothing |

Two rows deserve attention.

**Most + most sharing the *sufficient* term gives you *some*.** If most of the firm's partners are litigators and most of the firm's partners went to state schools, the two majorities must overlap by at least one person — you cannot have two groups each larger than half of the same set that share no member. So some litigators went to state schools. This is the exam's favourite overlap inference.

**Most + most sharing the *middle* term gives you nothing.** Most A are B, most B are C — the As could sit entirely in the part of B that is not C. No inference.

> [!example] The overlap inference in the wild
> *Most of the applicants who were interviewed had prior clerkship experience. Most of the applicants who were interviewed submitted a writing sample.*
>
> Both "most" statements are about the same set — applicants who were interviewed. Two subsets each larger than half must intersect.
>
> Credited inference: **at least one interviewed applicant had both clerkship experience and a writing sample.** Anything stronger — "most had both", "everyone with clerkship experience submitted a sample" — overreaches and is a distractor. Try it against [[question:lr-014]].

## Negating quantifiers

Inference and flaw questions both reward being able to negate cleanly.

- The negation of **all A are B** is **some A are not B** — not "no A are B", which is far stronger.
- The negation of **some A are B** is **no A are B**.
- The negation of **most A are B** is **at most half of A are B**.

Over-negating is the standard error: people flip "all" to "none" and then evaluate an answer that was never on the table. The same discipline powers the negation test in [[article:lr-assumption-family]].

> [!trap] Reading "some" as "not all"
> A stimulus says some board members opposed the merger. A choice says all board members opposed it. Beginners eliminate the choice as contradicted — but "some" is silent about whether all did, so the choice is *unsupported*, not *contradicted*. On a must-be-true question that distinction is invisible. On a cannot-be-true or a most-strongly-supported question it decides the item. See [[concept:cannot-be-true]].

## Key takeaways

- Some means at least one, up to and including all. It never implies "not all".
- Some and no are symmetric; all and most are not.
- Most plus most on a shared sufficient term yields some. On a shared middle term it yields nothing.
- All chains with all; most chains forward through all, never backward.
- Negate precisely: not-all is some-are-not, not none.
