# Law AI — Philosophy

> What we believe law *is*, what that makes a legal-intelligence system responsible for, and which of those beliefs are binding rules rather than opinions.
>
> [AGENTS.md](../AGENTS.md) states the mission and the coding principles. [constitution.md](constitution.md) states the rules a spec or PR must satisfy. **This file states the reasoning underneath both.** The rules derived here are enforced as [constitution.md](constitution.md) §13; amendments follow the ADR process — see [adr/0004-jurisprudential-stance.md](adr/0004-jurisprudential-stance.md).

---

## 1. The premise we start from

> "Justice is nothing else than the interest of the stronger."
>
> — Thrasymachus, in Plato, *Republic* I.338c (Jowett)

Thrasymachus is not saying that justice is a lie or that nothing matters. He is making a structural claim: in every regime, the ruling party makes the laws to its own advantage and *names* that arrangement justice. What subjects then experience as "being just" is compliance with someone else's advantage (I.338d–339a). Pressed further, he generalizes it — the just person, everywhere, comes out behind the unjust one, because the rules were not written for them (I.343b–344c).

We take this claim **descriptively, as an engineering premise about our data**, and we reject it **normatively, as a design goal for our system**. Both halves are load-bearing. Keeping only the first produces a cynical tool; keeping only the second produces a naive one.

---

## 2. Descriptively: the corpus is the record of the stronger

Law AI's inputs are opinions, statutes, regulations, and citation networks. Every one of them is an artifact of power, in ways that are concrete and measurable — not merely a matter of interpretation:

- **Opinions are written by the side that won.** The losing argument survives only as characterized by the judge who rejected it. Dissents survive but do not bind. Every `:Case` node in our graph is a victor's summary of a dispute.
- **The published record is a selected sample, not a census.** Disputes settle, and they settle non-randomly (Priest & Klein, 1984). Well-resourced repeat players litigate strategically — settling the cases likely to make bad precedent, appealing the ones likely to make good precedent — so the body of published doctrine drifts toward their interests over time (Galanter, 1974). What reaches an appellate reporter is what someone could afford to take there.
- **Citation frequency measures resources before it measures correctness.** A heavily cited case is one that many well-funded litigants found *useful*. Any centrality measure over a citation graph — in-degree, PageRank, HITS — is, first, a measure of who could afford to litigate, and only second a proxy for authority. This is the single most dangerous confusion available to a graph-native legal system, because the graph makes it so easy to compute.
- **Statutes encode the coalition that passed them**, and enforcement discretion re-encodes that coalition downstream, where almost nothing is published at all.
- **Coverage gaps are themselves power facts.** Which jurisdictions, courts, languages, claim types, and party types are missing from a corpus is legal information about who has been able to get their disputes recorded.
- **Law is backed by force, not by agreement.** "Legal interpretation takes place in a field of pain and death" (Cover, 1986). A holding is not a proposition that became true; it is a proposition someone can enforce.

None of this makes the corpus useless. It makes it **evidence of what the stronger have gotten courts to say** — which is exactly what a practitioner needs, and is close to Holmes' prediction theory of law (1897): the "law" worth knowing is a forecast of what officials will in fact do, and officials are situated people inside that structure.

The failure mode is not using the corpus. The failure mode is **re-labelling it**. A retrieval system that reports corpus consensus as ground truth is not neutral; it is an amplifier with a neutral-sounding voice. Everything in §4 follows from refusing to be that.

---

## 3. Normatively: the craft serves its subject, not its ruler

Socrates does not answer Thrasymachus by denying that rulers behave this way. He answers that no craft, *qua* craft, seeks its own advantage: medicine seeks the patient's health, navigation the sailors' safety, and "no art or science considers the interest of the superior or stronger, but of the subject and weaker" (*Republic* I.341c–342e). A physician who optimizes for the physician is not practicing better medicine; they are practicing something else.

Law AI is a craft in exactly that sense, and its subject is its user: the law student, the solo practitioner, the pro se litigant, the public-interest lawyer facing an opponent with fifty times the research budget. The instant the platform optimizes for its operator, its host, its vendor, or its own persistence, it has stopped being the thing described in the mission and become one more instrument of the stronger.

So the stance in one line:

> **The record encodes the interest of the stronger; the system's job is to make that visible and contestable, never to launder it and never to exploit it.**

This is why "justice is the interest of the stronger" cannot simply be pasted in as a project value. As a *norm* it would license building a tool that serves whoever holds it — and a legal AI is exactly the kind of artifact that, working as designed, redistributes capability toward whoever controls it. Adopted as a *premise*, it produces the opposite: a standing obligation to ask, of every feature, **"who is the stronger here, and what does this feature do for them?"**

---

## 4. What this obligates in code

These are the checkable commitments. Constitution §13 turns them into review gates.

### P1 — Authority is a power measure. Label it as one.

Citation counts, centrality scores, and "leading case" rankings may be computed and displayed, but must be presented as *what they measure* — how often and how successfully a proposition has been invoked — never as a correctness score. No agent may assert a holding on the strength of citation volume alone.

### P2 — Name the ruler behind every rule.

Every surfaced proposition carries its issuing authority: which court, which jurisdiction, which date, binding or persuasive, majority or dissent. `:Case` nodes already carry `court`, `source`, `source_url`, and `confidence` ([data-model.md](data-model.md)); a rule stated without them is an unattributed claim about what "the law" says, which is precisely the laundering §2 warns about.

### P3 — Surface who prevailed.

Where the underlying record supports it, case-level output should identify the disposition and the party type that won — not as a moral judgment, but because "who this rule was made for" is the single most compressed piece of context a reader can have. Where the record does not support it, say nothing rather than guess.

### P4 — Absence is a finding, not silence.

Retrieval that returns thin or jurisdictionally lopsided results must say so. "No cases found" and "no cases published" are different claims, and the system must never let the first imply the second. The autonomy loop's corpus-growth pillar ([adr/0003-autonomy-orchestrator.md](adr/0003-autonomy-orchestrator.md)) already prioritizes under-covered jurisdictions; under this stance that is an equity objective, not just a completeness metric.

### P5 — Never launder a majority into a truth.

Grounding and citation requirements get *stronger* under this premise, not weaker. Agreement across many retrieved sources is reported as agreement across many retrieved sources, with the count and the sources named. A consensus is a fact about a corpus, and our corpus is the one described in §2.

### P6 — The human is the stronger, by design.

HITL gates ([constitution.md](constitution.md) §5) are not merely a safety feature; they are the deliberate placement of power. The reviewer approves, the model proposes, and no autonomous path may invert that ([constitution.md](constitution.md) §12 I1). "The model was confident" is never a reason to skip a gate.

### P7 — Do not become the stronger.

A closed model that only its vendor can inspect, that a user cannot leave, and whose answers cannot be traced to a named provider *is* the Thrasymachean ruler in the relevant sense: it defines what counts as a correct answer and cannot be audited on that definition. [constitution.md](constitution.md) §1 (amended 2026-08-11) answers that risk without banning closed models outright — Claude is now the *default* product runtime, and the trade is named there rather than hidden. What §1 still forbids is a *locked* interpreter, not a closed one: the fully local, open-weights tier (`LLM_PROVIDER_CHAIN=ollama`) must stay permanently reachable, and is mandatory rather than optional for any matter under a confidentiality obligation that forbids third-party processing; every call is provenance-logged with which provider actually served it, so the system can never answer from behind an anonymous "the model said so"; and no second closed vendor may be added to the chain without amending the constitution in the open. P7 forbids the lock, not the vendor — an interpreter a user can always leave, and can always name, is not yet the ruler Thrasymachus described.

---

## 5. How this maps onto the existing non-negotiables

The stance is not new machinery bolted onto the repo. It is the reason the machinery already there is shaped the way it is:

| Existing rule | Reads, under this stance, as |
|---|---|
| §4 Provenance on every call and node | Every claim is traceable to *whose* assertion it was |
| §4 `source` + `confidence` on all nodes | No proposition floats free of the party that produced it |
| §4 Soft-delete, never hard-delete | The record of what was once claimed cannot be quietly rewritten by whoever holds the database |
| §5 HITL on ingestion + high-stakes output | Decision power stays with a human (P6) |
| §1 Provider chain: local-first stays reachable, no vendor lock without amendment | The interpreter of the law is never locked to one unaccountable party (P7) |
| §3 Source-grounded outputs + LegalBench | Skepticism about the corpus raises the evidentiary bar; it does not lower it (P5) |
| §12 I1 No auto-merge | Autonomy proposes; humans dispose |

---

## 6. What this stance does *not* license

Stated explicitly, because each of these is a plausible misreading:

- **Not nihilism about legal accuracy.** Admitting the record is partisan makes grounding, citation, and evaluation *more* important, not less. "The corpus is biased anyway" is never an argument for shipping an unevaluated model.
- **Not editorializing.** The system reports structural facts — who decided, who prevailed, what is missing, how heavily cited. It does not assign moral scores to parties, judges, or jurisdictions.
- **Not a political filter.** We do not down-rank sources by ideology, and we do not curate the corpus toward a preferred outcome. Doing so would just install a different stronger party. We label provenance and let the reader weigh it.
- **Not advice to game the system.** "Understand who the rules were written for" is research context for a reader. It is not a strategy engine for exploiting asymmetry, and features whose primary value is exploiting an opponent's lack of resources are out of scope.
- **Not a settled question.** Plato spends nine more books arguing Thrasymachus is wrong about what justice *is*. We are not adjudicating that. We are making an engineering commitment about what our *data* is, and a design commitment about whom our *tool* serves.

---

## 7. Sources

- Plato, *Republic*, Book I, 338c (the thesis), 341c–342e (the craft rebuttal), 343b–344c (the shepherd).
- Marc Galanter, "Why the 'Haves' Come Out Ahead: Speculations on the Limits of Legal Change," *Law & Society Review* 9(1):95–160 (1974).
- George L. Priest & Benjamin Klein, "The Selection of Disputes for Litigation," *Journal of Legal Studies* 13(1):1–55 (1984).
- Oliver Wendell Holmes Jr., "The Path of the Law," *Harvard Law Review* 10:457 (1897).
- Robert M. Cover, "Violence and the Word," *Yale Law Journal* 95:1601 (1986).

---

**This document is the philosophical source of record for Law AI. Changes require an ADR in [adr/](adr/) and human maintainer review, on the same terms as the constitution.**
