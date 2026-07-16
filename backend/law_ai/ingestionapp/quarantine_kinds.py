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

KNOWN_KINDS = frozenset(
    {
        KIND_CASE,
        KIND_STATUTE,
        KIND_STATUTE_SECTION,
        KIND_ORDINANCE,
        KIND_ORDINANCE_SECTION,
        KIND_REGULATION,
        KIND_DERIVED,
    }
)
