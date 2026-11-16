"""Constants for the ``PendingReview.kind`` discriminator (spec 015 FR-6).

Adding a new kind is a code-only change (no migration) thanks to the
``CharField(max_length=32)`` discriminator decision in spec 015 OQ-1.
"""

from __future__ import annotations

KIND_CASE = "case"
KIND_STATUTE = "statute"
KIND_STATUTE_SECTION = "statute_section"
KIND_ORDINANCE = "ordinance"
KIND_ORDINANCE_SECTION = "ordinance_section"
KIND_REGULATION = "regulation"
KIND_DERIVED = "derived"
#: A critical, high or authority-less finding from the lawmode
#: ``code_legal_review`` graph (spec 057 FR-5, AC-3). Not a document: nothing
#: about it is written to the knowledge graph, so it is a decision-only kind.
KIND_LAWMODE_FINDING = "lawmode_finding"

KNOWN_KINDS = frozenset(
    {
        KIND_CASE,
        KIND_STATUTE,
        KIND_STATUTE_SECTION,
        KIND_ORDINANCE,
        KIND_ORDINANCE_SECTION,
        KIND_REGULATION,
        KIND_DERIVED,
        KIND_LAWMODE_FINDING,
    }
)

#: Kinds whose human decision is the whole outcome. Approving one records the
#: decision and stops there: there is no extractor to hand it to and nothing to
#: commit, so the approval sweep never picks one up (it would fail on every
#: tick and, at the head of the queue, crowd out the rows that can commit).
DECISION_ONLY_KINDS = frozenset({KIND_LAWMODE_FINDING})
