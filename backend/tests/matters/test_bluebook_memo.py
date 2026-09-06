"""Bluebook forms and the deterministic memo (BL-20260817-03, first half).

Citation formatting is a professional-liability surface, so the tests that
matter most are the *negative* ones: a missing reporter must produce a short
citation, never an invented one, and an unverified authority must never
appear in the table of authorities as though it had been checked.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from law_ai.matters.drafting.bluebook import (
    UNKNOWN,
    case_citation,
    format_citation,
    format_table,
    regulation_citation,
    statute_citation,
)
from law_ai.matters.drafting.memo import compose_memo
from law_ai.matters.models import Matter, MatterArtifact, MatterAuthority

pytestmark = [pytest.mark.unit]


class TestCaseForm:
    def test_full_form(self) -> None:
        assert (
            case_citation(
                {
                    "title": "Marbury v. Madison",
                    "reporter_volume": "5",
                    "reporter": "U.S.",
                    "reporter_page": "137",
                    "decided_at": "1803-02-24",
                    "court": "us-supreme",
                }
            )
            == "Marbury v. Madison, 5 U.S. 137 (1803)"
        )

    def test_a_lower_court_keeps_its_parenthetical(self) -> None:
        assert (
            case_citation(
                {
                    "title": "Doe v. Roe",
                    "reporter_volume": "12",
                    "reporter": "F.3d",
                    "reporter_page": "44",
                    "decided_at": "1994-01-01",
                    "court_abbrev": "10th Cir.",
                }
            )
            == "Doe v. Roe, 12 F.3d 44 (10th Cir. 1994)"
        )

    def test_missing_reporter_shortens_rather_than_invents(self) -> None:
        assert (
            case_citation({"title": "Doe v. Roe", "decided_at": "1994-05-05"})
            == "Doe v. Roe (1994)"
        )

    def test_no_name_is_unavailable_not_a_guess(self) -> None:
        assert case_citation({"decided_at": "1994"}) == UNKNOWN


class TestStatuteAndRegulation:
    def test_statute_full_form(self) -> None:
        assert (
            statute_citation(
                {
                    "title_number": "42",
                    "code": "U.S.C.",
                    "section": "1983",
                    "effective_at": "2018-01-01",
                }
            )
            == "42 U.S.C. § 1983 (2018)"
        )

    def test_a_stored_citation_string_is_used_verbatim(self) -> None:
        assert (
            statute_citation({"citation": "Colo. Rev. Stat. § 13-21-115"})
            == "Colo. Rev. Stat. § 13-21-115"
        )

    def test_regulation_defaults_to_cfr(self) -> None:
        assert (
            regulation_citation(
                {"title_number": "29", "section": "1630.2", "year": "2024"}
            )
            == "29 C.F.R. § 1630.2 (2024)"
        )

    def test_an_unmodelled_kind_falls_back_to_the_stored_string(self) -> None:
        assert (
            format_citation({"node_label": "Ordinance", "citation": "Denver § 1-2"})
            == "Denver § 1-2"
        )

    def test_the_table_is_unique_and_sorted(self) -> None:
        rows = [
            {"node_label": "Case", "title": "B v. C", "decided_at": "2000"},
            {"node_label": "Case", "title": "A v. B", "decided_at": "1999"},
            {"node_label": "Case", "title": "A v. B", "decided_at": "1999"},
            {"node_label": "Case"},
        ]
        assert format_table(rows) == ["A v. B (1999)", "B v. C (2000)"]


@pytest.mark.django_db
class TestMemo:
    @pytest.fixture
    def matter(self) -> Matter:
        owner = get_user_model().objects.create_user(
            username="ada", password="pw-12345678"
        )
        row = Matter.objects.create(
            owner=owner,
            slug="lease",
            name="Smith lease",
            jurisdiction="co",
            issue_tags=["landlord-tenant"],
        )
        MatterArtifact.objects.create(
            matter=row,
            kind="analysis",
            title="Habitability",
            trace_id="tr-1",
            analysis_id="an-1",
            body={
                "issue": "Was the unit habitable?",
                "conclusion": "Likely not.",
            },
        )
        MatterAuthority.objects.create(
            matter=row,
            node_id="case:1",
            node_label="Case",
            title="Javins v. First Nat'l Realty Corp.",
            citation="428 F.2d 1071",
            verified_at=timezone.now(),
        )
        MatterAuthority.objects.create(
            matter=row,
            node_id="case:2",
            node_label="Case",
            title="Unchecked v. Guess",
        )
        return row

    def test_the_memo_is_composed_from_the_artifacts(self, matter: Matter) -> None:
        memo = compose_memo(matter)
        assert "Memorandum — Smith lease" in memo["markdown"]
        assert "Was the unit habitable?" in memo["markdown"]
        assert memo["artifact_count"] == 1

    def test_the_provenance_footer_lists_the_trace_ids(self, matter: Matter) -> None:
        memo = compose_memo(matter)
        assert memo["trace_ids"] == ["tr-1"]
        assert "trace `tr-1`" in memo["markdown"]
        assert "analysis `an-1`" in memo["markdown"]
        assert "no model wrote" in memo["markdown"]

    def test_unverified_authorities_are_listed_apart(self, matter: Matter) -> None:
        body = compose_memo(matter)["markdown"]
        table, rest = body.split("### Recorded but not yet verified")
        assert "Javins" in table
        assert "Unchecked v. Guess" not in table
        assert "Unchecked v. Guess" in rest

    def test_it_carries_the_draft_disclaimer(self, matter: Matter) -> None:
        assert "not legal advice" in compose_memo(matter)["disclaimer"]

    def test_an_empty_matter_says_so_rather_than_inventing(self, matter: Matter):
        matter.artifacts.all().delete()
        body = compose_memo(matter)["markdown"]
        assert "nothing filed under this matter yet" in body

    def test_the_endpoint_serves_markdown_and_refuses_docx(
        self, matter: Matter
    ) -> None:
        client = APIClient()
        client.force_authenticate(user=matter.owner)
        res = client.get("/api/matters/lease/memo")
        assert res.status_code == 200
        assert res.json()["format"] == "markdown"
        # The remaining half of the item is declared, not faked.
        pending = client.get("/api/matters/lease/memo?output=docx")
        assert pending.status_code == 501
        assert "BL-20260817-03" in pending.json()["detail"]

    def test_the_memo_is_owner_scoped(self, matter: Matter) -> None:
        client = APIClient()
        client.force_authenticate(
            user=get_user_model().objects.create_user(
                username="mallory", password="pw-12345678"
            )
        )
        assert client.get("/api/matters/lease/memo").status_code == 404
