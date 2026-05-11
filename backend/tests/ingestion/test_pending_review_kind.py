"""``PendingReview.kind`` discriminator tests (spec 015 T-006, AC-3)."""

from __future__ import annotations

import pytest
from django.db import connection

from lawgraph.ingestionapp.models import PendingReview
from lawgraph.ingestionapp.quarantine_kinds import (
    KIND_CASE,
    KIND_DERIVED,
    KIND_STATUTE,
    KNOWN_KINDS,
)


@pytest.mark.django_db
def test_default_kind_is_case() -> None:
    pr = PendingReview.objects.create(
        id="case-default",
        source="courtlistener",
        payload={"id": "case-default"},
        confidence=0.4,
        reason="low",
    )
    assert pr.kind == KIND_CASE


@pytest.mark.django_db
def test_explicit_kind_persisted() -> None:
    PendingReview.objects.create(
        id="statute-1",
        source="crs",
        payload={"id": "us-co/crs/18-3-102"},
        confidence=0.5,
        reason="parser low conf",
        kind=KIND_STATUTE,
    )
    PendingReview.objects.create(
        id="derived-1",
        source="legal_analyst",
        payload={"trace_id": "abc"},
        confidence=0.6,
        kind=KIND_DERIVED,
    )

    by_kind = {row.kind for row in PendingReview.objects.all()}
    assert {KIND_STATUTE, KIND_DERIVED}.issubset(by_kind)


@pytest.mark.django_db
def test_kind_has_database_index() -> None:
    """The ``kind`` column must be indexed (FR-6) so admin filtering scales."""
    constraints = connection.introspection.get_constraints(
        connection.cursor(), "pending_review"
    )
    indexed_columns = {
        tuple(meta["columns"]) for meta in constraints.values() if meta.get("index")
    }
    # Either a standalone (kind,) index or the composite (kind, created_at) index counts.
    assert any(
        cols and cols[0] == "kind" for cols in indexed_columns
    ), f"no index starts with `kind`; got {indexed_columns}"


@pytest.mark.django_db
def test_known_kinds_are_disjoint_constants() -> None:
    """Cheap guard against duplicate string values among the constants."""
    assert KIND_CASE in KNOWN_KINDS
    assert KIND_STATUTE in KNOWN_KINDS
    assert KIND_DERIVED in KNOWN_KINDS
    assert len(KNOWN_KINDS) == 7
