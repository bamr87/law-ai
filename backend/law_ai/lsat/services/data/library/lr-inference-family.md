---
id: lr-inference-family
title: Inference Questions — Must Be True, Most Strongly Supported, Cannot Be True
kind: question-type
level: core
sections: [LR]
summary: The family with no argument to attack — what follows from the facts, how the three stems differ in strictness, and why the safest-sounding answer usually wins.
concepts: [must-be-true, most-strongly-supported, cannot-be-true, universal-instantiation, conditional-reasoning]
archetypes: [lr-must-be-true, lr-most-strongly-supported, lr-cannot-be-true, lr-conditional-inference]
prerequisites: [conditional-logic-foundations, quantifiers-and-overlap]
related: [lr-section-guide, rc-question-families, lr-paradox-and-evaluate]
tags: [inference, must-be-true, deduction]
status: reviewed
last_reviewed: 2026-09-03
revision: 1
references: []
---

## No argument, just facts

Inference stimuli usually contain no conclusion at all — they are a set of claims, and the question asks what follows. That changes the whole approach: there is nothing to attack, no gap to bridge, no flaw to name. The task is downward, not sideways. See [[concept:must-be-true]].

Because there is nothing to pre-phrase in the usual sense, this is the one family where going to the choices early is correct. What you *can* do first is combine: if the stimulus contains two conditionals sharing a term, chain them; if it contains two "most" statements about the same group, note the overlap. Frequently the credited answer is exactly that combination.

## Three stems, three strictness levels

| Stem | Standard | What a good answer looks like |
|---|---|---|
| *must be true* / *properly inferred* | Airtight. No gap at all. | Often modest, often a contrapositive or a chain |
| *most strongly supported* | Very likely, not certain | Can require a small reasonable step |
| *cannot be true* / *must be false* | Contradicted by the stimulus | The one choice inconsistent with the facts |

The difference between the first two is real but narrower than it looks. On *must be true*, any gap disqualifies. On *most strongly supported*, a choice can go slightly beyond the text if nothing else comes close — but "slightly" is doing serious work, and the credited answer is still the most conservative of the plausible ones. See [[concept:most-strongly-supported]].

*Cannot be true* inverts everything: four choices are consistent with the stimulus and one is not. See [[concept:cannot-be-true]].

> [!example] Combining before choosing
> *All of the museum's Renaissance holdings were acquired before 1970. Every work acquired before 1970 was catalogued by hand. Most hand-catalogued works have not yet been digitised.*
>
> Chain the conditionals: `Renaissance → acquired before 1970 → hand-catalogued`. So all Renaissance holdings were hand-catalogued.
>
> Now the third fact: most hand-catalogued works are not digitised. Careful — that is about hand-catalogued works *as a whole*, not about the Renaissance subset. "Most Renaissance holdings are not digitised" does **not** follow, because the Renaissance works could all sit in the digitised minority.
>
> What does follow: *"At least some works that were catalogued by hand were acquired before 1970"* — modest, airtight, and exactly the kind of answer this family rewards.

## Strong language is usually wrong

Words like *always*, *never*, *only*, *all*, *none*, *must* raise the bar a choice has to clear, and a stimulus of three sentences rarely supports that bar. Words like *some*, *at least one*, *may*, *not all* lower it.

This is a tendency, not a rule — a stimulus containing "all" can license a conclusion containing "all". But when two choices both look defensible, the weaker one is the better bet, and the habit of reaching for the impressive-sounding answer is expensive here.

> [!trap] The plausible extension
> The classic wrong answer in this family is true, sensible, and one small step beyond the text. The stimulus says a policy reduced emissions; the choice says the policy was worth its cost. Nothing in the stimulus is about cost.
>
> The check: point at the sentence that supports the choice. If you cannot put your finger on specific text, it does not follow — no matter how reasonable it sounds. This is the same discipline that governs Reading Comprehension inference questions; see [[article:rc-question-families]].

## Method

1. Read the stimulus for **combinable elements**: conditionals sharing a term, quantifiers about the same group, a numerical constraint.
2. Combine what combines. Write the chain if there are three or more links.
3. Go to the choices and eliminate anything requiring information not present.
4. Among survivors, prefer the one you can support by pointing at text.

## Key takeaways

- No argument to attack — the task is deduction from given facts.
- Combine conditionals and quantifiers before reading choices; the answer is often that combination.
- *Must be true* is airtight; *most strongly supported* allows one small step; *cannot be true* inverts the task.
- Weak, modest answers win more often than strong ones.
- Point at the supporting text. If you cannot, the choice does not follow.
