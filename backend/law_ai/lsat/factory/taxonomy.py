"""LSAT question-archetype taxonomy — the exam's patterns as data.

Spec 024 FR-1. Each :class:`Archetype` captures one recurring LSAT question
pattern: which section it belongs to, which concept-catalog entries it
exercises, how difficulty distributes on the real exam, item-writing guidance
(stem formula + distractor craft) injected into generation prompts, and an
optional model-tier hint for jobs that are disproportionately hard to author
well (e.g. parallel reasoning, net-new game setups).

The registry is validated against :func:`law_ai.lsat.services.bank.load_concepts`
so an archetype can never reference a concept id the catalog doesn't define —
generation prompts only ever tag drafts with real, tutorable concepts.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field

from law_ai.lsat.factory.config import ModelTier
from law_ai.lsat.services.bank import Difficulty, Section, load_concepts


class Archetype(BaseModel):
    """One recurring LSAT question pattern (see module docstring)."""

    id: str = Field(pattern=r"^[a-z]{2}-[a-z0-9-]+$")
    section: Section
    name: str
    concepts: list[str] = Field(
        min_length=1,
        description="Concept-catalog ids this archetype exercises; the first "
        "is the primary tag used for coverage matching.",
    )
    difficulty_weights: dict[Difficulty, float] = Field(
        description="Relative frequency of each difficulty on the real exam; "
        "used to spread generated items realistically.",
    )
    guidance: str = Field(
        description="Item-writing craft injected verbatim into prompts: stem "
        "formula, what the credited answer must do, distractor design.",
    )
    tier_hint: ModelTier | None = Field(
        default=None,
        description="Force a generation tier regardless of difficulty (e.g. "
        "'premium' for archetypes that are hard to author well).",
    )
    requires_passage: bool = Field(
        default=False,
        description="True when items need a PassageContext (RC passages, LG "
        "game setups).",
    )


# ---------------------------------------------------------------------------
# Registry — Logical Reasoning
# ---------------------------------------------------------------------------

_LR: tuple[Archetype, ...] = (
    Archetype(
        id="lr-conditional-inference",
        section="LR",
        name="Conditional Inference (modus ponens)",
        concepts=["modus-ponens", "conditional-reasoning"],
        difficulty_weights={"easy": 0.5, "med": 0.4, "hard": 0.1},
        guidance=(
            "State one or two conditionals plus a fact that triggers them; ask "
            "what must be true. The credited answer applies the chain validly. "
            "Distractors: the converse, the inverse, a probabilistic hedge, and "
            "an out-of-scope claim."
        ),
    ),
    Archetype(
        id="lr-contrapositive-inference",
        section="LR",
        name="Contrapositive Inference (modus tollens)",
        concepts=["modus-tollens", "contrapositive", "conditional-reasoning"],
        difficulty_weights={"easy": 0.4, "med": 0.4, "hard": 0.2},
        guidance=(
            "Give 'if P then Q' plus not-Q; the credited answer concludes "
            "not-P. Distractors affirm the consequent, deny the antecedent, "
            "restate a premise, or claim nothing follows."
        ),
    ),
    Archetype(
        id="lr-must-be-true",
        section="LR",
        name="Must Be True / Inference",
        concepts=["must-be-true", "conditional-reasoning"],
        difficulty_weights={"easy": 0.3, "med": 0.5, "hard": 0.2},
        guidance=(
            "Provide 2-3 compatible statements (quantified or conditional); ask "
            "which must also be true. The credited answer is a strict logical "
            "consequence — never new information. Distractors are plausible "
            "but unsupported strengthenings, reversals, or 'most/some' swaps."
        ),
    ),
    Archetype(
        id="lr-main-conclusion",
        section="LR",
        name="Main Conclusion Identification",
        concepts=["main-conclusion"],
        difficulty_weights={"easy": 0.5, "med": 0.4, "hard": 0.1},
        guidance=(
            "Bury the conclusion mid-argument behind a premise indicator trap "
            "('since', 'because') and include a concession clause. The credited "
            "answer paraphrases the conclusion; distractors quote premises, the "
            "concession, or an implication the argument never draws."
        ),
    ),
    Archetype(
        id="lr-necessary-assumption",
        section="LR",
        name="Necessary Assumption",
        concepts=["necessary-assumption"],
        difficulty_weights={"easy": 0.2, "med": 0.5, "hard": 0.3},
        guidance=(
            "Build an argument with a quiet gap between premise-terms and "
            "conclusion-terms. The credited answer must pass the negation test "
            "(negate it and the argument collapses) and should be modest in "
            "scope. Distractors are stronger-than-needed claims that merely "
            "help, or requirements of a different argument."
        ),
    ),
    Archetype(
        id="lr-sufficient-assumption",
        section="LR",
        name="Sufficient Assumption",
        concepts=["sufficient-assumption", "conditional-reasoning"],
        difficulty_weights={"easy": 0.1, "med": 0.5, "hard": 0.4},
        guidance=(
            "Leave one named logical gap (premise mentions X, conclusion "
            "mentions Y). The credited answer is a conditional bridging X→Y "
            "that guarantees the conclusion. Distractors bridge the wrong "
            "direction (Y→X), bridge irrelevant terms, or are necessary-but-"
            "insufficient hedges."
        ),
    ),
    Archetype(
        id="lr-strengthen",
        section="LR",
        name="Strengthen",
        concepts=["strengthen", "causation-vs-correlation"],
        difficulty_weights={"easy": 0.3, "med": 0.5, "hard": 0.2},
        guidance=(
            "Use an inductive argument (often causal or sample-based); ask "
            "which answer most supports it. The credited answer rules out an "
            "alternative cause, confirms the mechanism, or validates the "
            "sample. Distractors are irrelevant costs/benefits, appeals to "
            "authority, or weakeners in disguise."
        ),
    ),
    Archetype(
        id="lr-weaken",
        section="LR",
        name="Weaken",
        concepts=["weaken", "alternative-cause"],
        difficulty_weights={"easy": 0.3, "med": 0.5, "hard": 0.2},
        guidance=(
            "Use a causal or analogical argument; ask which answer most "
            "undermines it. The credited answer supplies a confound, reverse "
            "causation, or a disanalogy that attacks the premise→conclusion "
            "link — never merely contradicts a premise. Distractors attack "
            "irrelevancies (cost, popularity) or restate the conclusion."
        ),
    ),
    Archetype(
        id="lr-causal-flaw",
        section="LR",
        name="Causal Flaw (correlation → causation)",
        concepts=["causation-vs-correlation", "flaw-in-reasoning"],
        difficulty_weights={"easy": 0.4, "med": 0.4, "hard": 0.2},
        guidance=(
            "Present a correlation and conclude causation; ask how the "
            "reasoning is flawed. The credited answer names the failure to "
            "rule out confounders/reverse causation. Distractors name flaws "
            "the argument didn't commit (sampling, equivocation, ad hominem)."
        ),
    ),
    Archetype(
        id="lr-flaw-general",
        section="LR",
        name="Flaw in the Reasoning (general)",
        concepts=["flaw-in-reasoning"],
        difficulty_weights={"easy": 0.2, "med": 0.5, "hard": 0.3},
        guidance=(
            "Commit exactly one classic flaw (circularity, part-whole, false "
            "dichotomy, hasty generalization…). The credited answer describes "
            "that flaw abstractly — match the abstraction level of real LSAT "
            "answers ('takes for granted that…', 'infers X merely because Y'). "
            "Distractors describe other named flaws precisely enough to tempt."
        ),
    ),
    Archetype(
        id="lr-equivocation",
        section="LR",
        name="Equivocation Flaw",
        concepts=["equivocation", "flaw-in-reasoning"],
        difficulty_weights={"easy": 0.2, "med": 0.5, "hard": 0.3},
        guidance=(
            "Shift one key term's meaning between premise and conclusion "
            "(scope, sense, or measure — e.g. 'volume' of complaints vs. "
            "seriousness). The credited answer pinpoints the shifted term. "
            "Distractors allege unrelated flaws or a shift in the wrong term."
        ),
    ),
    Archetype(
        id="lr-appeal-to-ignorance",
        section="LR",
        name="Appeal to Ignorance",
        concepts=["appeal-to-ignorance", "flaw-in-reasoning"],
        difficulty_weights={"easy": 0.4, "med": 0.4, "hard": 0.2},
        guidance=(
            "Conclude falsity from absence of proof (or truth from absence of "
            "disproof). The credited answer states that lack of evidence "
            "settles nothing. Distractors: ad hominem, sample-size complaints, "
            "or 'fails to define terms'."
        ),
    ),
    Archetype(
        id="lr-parallel-reasoning",
        section="LR",
        name="Parallel Reasoning",
        concepts=["parallel-reasoning", "universal-instantiation"],
        difficulty_weights={"easy": 0.2, "med": 0.4, "hard": 0.4},
        tier_hint="premium",
        guidance=(
            "Write a short valid argument with a crisp form (e.g. all-P-are-Q "
            "instantiation, chained conditionals). The credited answer "
            "replicates the FORM in a different domain with matching validity. "
            "Each distractor breaks the form one way: quantifier downgrade "
            "('most'), converse, negation slip, or added premise. Diagram every "
            "choice before finalizing the key."
        ),
    ),
    Archetype(
        id="lr-parallel-flaw",
        section="LR",
        name="Parallel Flaw",
        concepts=["parallel-reasoning", "flaw-in-reasoning"],
        difficulty_weights={"easy": 0.1, "med": 0.4, "hard": 0.5},
        tier_hint="premium",
        guidance=(
            "Write an argument committing one specific formal flaw (affirming "
            "the consequent works well). The credited answer commits the SAME "
            "flaw in new content. Trap: include one VALID argument with similar "
            "surface content, plus arguments with different flaws."
        ),
    ),
    Archetype(
        id="lr-resolve-paradox",
        section="LR",
        name="Resolve the Paradox",
        concepts=["resolve-paradox"],
        difficulty_weights={"easy": 0.3, "med": 0.5, "hard": 0.2},
        guidance=(
            "State two findings that appear to conflict ('X rose, yet Y "
            "fell'); ask which answer most helps explain the discrepancy. The "
            "credited answer supplies a fact making both true simultaneously. "
            "Distractors deepen the paradox, explain only one side, or are "
            "out of scope."
        ),
    ),
    Archetype(
        id="lr-method-of-reasoning",
        section="LR",
        name="Method of Reasoning",
        concepts=["method-of-reasoning"],
        difficulty_weights={"easy": 0.3, "med": 0.5, "hard": 0.2},
        guidance=(
            "Write a two-speaker exchange or a single argument using an "
            "identifiable technique (counterexample, analogy, reductio, "
            "eliminating alternatives). Ask how the argument proceeds. The "
            "credited answer describes the technique abstractly; distractors "
            "describe techniques not used."
        ),
    ),
    Archetype(
        id="lr-principle-apply",
        section="LR",
        name="Principle Application",
        concepts=["principle-application"],
        difficulty_weights={"easy": 0.3, "med": 0.5, "hard": 0.2},
        guidance=(
            "State a general principle (often conditional, legal-flavored); "
            "ask which concrete scenario conforms to (or is justified by) it. "
            "The credited answer satisfies every trigger condition. Distractors "
            "meet only some conditions, trip an exception, or invert the "
            "principle."
        ),
    ),
)

# ---------------------------------------------------------------------------
# Registry — Reading Comprehension
# ---------------------------------------------------------------------------

_RC: tuple[Archetype, ...] = (
    Archetype(
        id="rc-main-point",
        section="RC",
        name="Main Point",
        concepts=["main-point", "rc-structure"],
        difficulty_weights={"easy": 0.3, "med": 0.5, "hard": 0.2},
        requires_passage=True,
        guidance=(
            "Ask for the statement best expressing the passage's main point. "
            "The credited answer covers the WHOLE arc including the author's "
            "stance. Distractors are too narrow (one paragraph), too strong "
            "('always', 'proves'), or contradict a qualification."
        ),
    ),
    Archetype(
        id="rc-detail",
        section="RC",
        name="Explicit Detail",
        concepts=["detail-question"],
        difficulty_weights={"easy": 0.6, "med": 0.3, "hard": 0.1},
        requires_passage=True,
        guidance=(
            "Ask 'according to the passage…' about a stated fact. The credited "
            "answer paraphrases one specific sentence. Distractors reuse "
            "passage vocabulary in unstated combinations, or state facts about "
            "the wrong entity/date."
        ),
    ),
    Archetype(
        id="rc-inference",
        section="RC",
        name="Inference from the Passage",
        concepts=["rc-inference"],
        difficulty_weights={"easy": 0.1, "med": 0.5, "hard": 0.4},
        requires_passage=True,
        guidance=(
            "Ask what can most reasonably be inferred (often about a named "
            "party's beliefs). The credited answer follows from combining two "
            "passage statements without new assumptions. Distractors are "
            "real-world-plausible but textually unsupported, or overstate a "
            "hedged claim."
        ),
    ),
    Archetype(
        id="rc-attitude",
        section="RC",
        name="Author's Attitude / Tone",
        concepts=["author-attitude", "rc-tone"],
        difficulty_weights={"easy": 0.2, "med": 0.5, "hard": 0.3},
        requires_passage=True,
        guidance=(
            "Ask for the author's attitude toward a specific target. Calibrate "
            "the credited answer to the passage's hedging (e.g. 'qualified "
            "approval', 'measured skepticism'). Distractors are polarity flips "
            "and intensity overshoots ('unqualified', 'hostile', "
            "'indifferent')."
        ),
    ),
    Archetype(
        id="rc-function",
        section="RC",
        name="Function of a Statement / Reference",
        concepts=["rc-structure"],
        difficulty_weights={"easy": 0.2, "med": 0.5, "hard": 0.3},
        requires_passage=True,
        guidance=(
            "Ask why the author mentions a specific example, case, or study "
            "('primarily in order to…'). The credited answer names its "
            "argumentative role (illustrate, concede, rebut). Distractors "
            "assign roles serving claims the passage never makes."
        ),
    ),
    Archetype(
        id="rc-organization",
        section="RC",
        name="Passage Organization",
        concepts=["rc-structure"],
        difficulty_weights={"easy": 0.2, "med": 0.5, "hard": 0.3},
        requires_passage=True,
        guidance=(
            "Ask which answer best describes the passage's organization as an "
            "abstract sequence ('a view is introduced, criticized, and "
            "revised…'). The credited answer matches paragraph roles in order. "
            "Distractors permute the sequence or import a move (e.g. 'proposes "
            "a solution') that never happens."
        ),
    ),
)

# ---------------------------------------------------------------------------
# Registry — Logic Games (Analytical Reasoning)
# ---------------------------------------------------------------------------

_LG: tuple[Archetype, ...] = (
    Archetype(
        id="lg-acceptability",
        section="LG",
        name="Acceptability / Orientation",
        concepts=["elimination-grid", "sequencing"],
        difficulty_weights={"easy": 0.8, "med": 0.2, "hard": 0.0},
        requires_passage=True,
        guidance=(
            "Ask which option could be a complete, rule-abiding arrangement. "
            "Design the four wrong options so each violates exactly one "
            "different rule — the standard rule-by-rule elimination drill."
        ),
    ),
    Archetype(
        id="lg-must-be-true",
        section="LG",
        name="Global Must Be True",
        concepts=["must-be-true", "sequencing"],
        difficulty_weights={"easy": 0.2, "med": 0.5, "hard": 0.3},
        requires_passage=True,
        guidance=(
            "With no extra supposition, ask what must be true across ALL valid "
            "arrangements. Verify by enumerating the full solution set. "
            "Distractors hold in most-but-not-all arrangements — cite a "
            "counterexample arrangement for each in the explanation."
        ),
    ),
    Archetype(
        id="lg-could-be-true-except",
        section="LG",
        name="Could Be True EXCEPT / Cannot Be True",
        concepts=["could-be-true-except", "must-be-true"],
        difficulty_weights={"easy": 0.1, "med": 0.5, "hard": 0.4},
        requires_passage=True,
        guidance=(
            "Four options are each realizable in some valid arrangement; "
            "exactly one is impossible. The explanation must exhibit a "
            "witness arrangement for every 'could' option and derive the "
            "contradiction for the credited impossible one."
        ),
    ),
    Archetype(
        id="lg-local-conditional",
        section="LG",
        name="Local Conditional ('If X, then…')",
        concepts=["sequencing", "conditional-reasoning"],
        difficulty_weights={"easy": 0.3, "med": 0.5, "hard": 0.2},
        requires_passage=True,
        guidance=(
            "Add one supposition ('If H is third…') that meaningfully "
            "constrains the board, then ask what must/could be true. Choose "
            "suppositions that force a small solvable chain (2-3 inferences) "
            "rather than brute enumeration."
        ),
    ),
    Archetype(
        id="lg-grouping",
        section="LG",
        name="Grouping Game Question",
        concepts=["grouping-game", "must-be-true"],
        difficulty_weights={"easy": 0.2, "med": 0.5, "hard": 0.3},
        tier_hint="premium",
        requires_passage=True,
        guidance=(
            "For selection/distribution setups (in/out, or teams), write "
            "questions turning on conditional membership rules ('If J is "
            "selected, K is not'). The credited answer follows from chaining "
            "the contrapositives of membership rules."
        ),
    ),
)

_ALL: tuple[Archetype, ...] = _LR + _RC + _LG


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------


def all_archetypes() -> tuple[Archetype, ...]:
    """Every registered archetype, LR then RC then LG."""
    return _ALL


def archetypes_for(section: Section) -> tuple[Archetype, ...]:
    return tuple(a for a in _ALL if a.section == section)


@lru_cache(maxsize=1)
def by_id() -> dict[str, Archetype]:
    return {a.id: a for a in _ALL}


def get_archetype(archetype_id: str) -> Archetype:
    try:
        return by_id()[archetype_id]
    except KeyError as exc:
        raise KeyError(f"unknown archetype {archetype_id!r}") from exc


def validate_taxonomy() -> None:
    """Raise ``ValueError`` when the registry is internally inconsistent.

    Checks: unique ids, and every referenced concept id exists in the concept
    catalog (spec 024 FR-1). Called by the planner and by tests so a taxonomy
    edit can never silently produce drafts tagged with unknown concepts.
    """
    seen: set[str] = set()
    catalog = set(load_concepts().keys())
    problems: list[str] = []
    for arch in _ALL:
        if arch.id in seen:
            problems.append(f"duplicate archetype id {arch.id!r}")
        seen.add(arch.id)
        missing = [c for c in arch.concepts if c not in catalog]
        if missing:
            problems.append(
                f"archetype {arch.id!r} references unknown concept(s): {missing}"
            )
        if not abs(sum(arch.difficulty_weights.values()) - 1.0) < 1e-6:
            problems.append(f"archetype {arch.id!r} difficulty_weights must sum to 1.0")
    if problems:
        raise ValueError("taxonomy validation failed: " + "; ".join(problems))
