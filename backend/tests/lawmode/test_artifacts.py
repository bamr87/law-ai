"""Report artifacts: review.json, risks.yaml, mitigations.md, DISCLAIMER.md.

Ported behaviour from ``LawModeAgent.generate_artifacts``; the YAML is now
written without a YAML library, so these tests check it the hard way — by
parsing it back when a parser happens to be installed, and by reading the
exact text when it is not.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from law_ai.lawmode.schemas import (
    DISCLAIMER_NOTICE,
    ReviewResult,
    ReviewStatus,
    Risk,
    Severity,
)
from law_ai.lawmode.services.artifacts import (
    DISCLAIMER_PATH,
    generate_artifacts,
    load_disclaimer,
    render_mitigations_md,
    render_risks_yaml,
)

pytestmark = pytest.mark.unit

TRICKY = 'Art. 32: "security" of processing # not a comment\nsecond line — ünïcode'


def _risk(**overrides: object) -> Risk:
    fields: dict[str, object] = {
        "id": "R001",
        "severity": Severity.CRITICAL,
        "title": "Personal data sent without encryption",
        "law": "GDPR Art. 32",
        "jurisdiction": "EU",
        "citation": "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
        "description": "The email field is posted over plain HTTP.",
        "mitigation": "Send it over TLS.",
        "file_path": "app.py",
        "line_start": 12,
        "line_end": 14,
        "review_status": ReviewStatus.UNREVIEWED,
    }
    fields.update(overrides)
    return Risk.model_validate(fields)


def _review(*risks: Risk, unparsed_findings: int = 0) -> ReviewResult:
    return ReviewResult(
        jurisdictions=["EU"],
        risks=list(risks),
        unparsed_findings=unparsed_findings,
        metadata={"citations_verified": False},
    )


def test_it_writes_the_four_files_lawmode_wrote(tmp_path: Path) -> None:
    target = tmp_path / "nested" / ".lawmode"

    artifacts = generate_artifacts(_review(_risk()), target)

    assert sorted(artifacts) == [
        "DISCLAIMER.md",
        "mitigations.md",
        "review.json",
        "risks.yaml",
    ]
    assert all(path.is_file() and path.parent == target for path in artifacts.values())
    assert sorted(p.name for p in target.iterdir()) == sorted(artifacts)


def test_no_history_dump_of_the_reviewed_code_is_written(tmp_path: Path) -> None:
    generate_artifacts(_review(_risk()), tmp_path)

    assert not (tmp_path / "history").exists()


def test_review_json_round_trips(tmp_path: Path) -> None:
    review = _review(_risk(), _risk(id="R002", severity=Severity.LOW))

    path = generate_artifacts(review, tmp_path)["review.json"]

    assert ReviewResult.model_validate_json(path.read_text(encoding="utf-8")) == review
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["disclaimer"] == DISCLAIMER_NOTICE
    assert data["risks"][0]["review_status"] == "unreviewed"
    assert data["human_approval_required"] is True
    assert data["unparsed_findings"] == 0


def test_the_two_machine_readable_files_agree(tmp_path: Path) -> None:
    yaml = pytest.importorskip("yaml")
    review = _review(_risk(), unparsed_findings=1)

    artifacts = generate_artifacts(review, tmp_path)
    as_json = json.loads(artifacts["review.json"].read_text(encoding="utf-8"))
    as_yaml = yaml.safe_load(artifacts["risks.yaml"].read_text(encoding="utf-8"))

    for key in ("review_id", "human_approval_required", "unparsed_findings"):
        assert as_yaml[key] == as_json[key]
    assert as_yaml["citations_verified"] is False
    assert as_json["metadata"]["citations_verified"] is False
    assert [r["id"] for r in as_yaml["risks"]] == [r["id"] for r in as_json["risks"]]


def test_the_disclaimer_is_the_one_packaged_file(tmp_path: Path) -> None:
    stale = tmp_path / "DISCLAIMER.md"
    stale.write_text("an old copy", encoding="utf-8")

    path = generate_artifacts(_review(), tmp_path)["DISCLAIMER.md"]

    assert path.read_text(encoding="utf-8") == load_disclaimer()
    assert DISCLAIMER_PATH.name == "disclaimer.md"
    assert DISCLAIMER_PATH.parent.name == "lawmode"


def test_the_disclaimer_says_what_a_report_is_not() -> None:
    text = load_disclaimer()

    assert "NOT LEGAL ADVICE" in text
    assert "No findings is not compliance" in text
    assert "Critical and high findings are for a human" in text
    assert "LLM_PROVIDER_CHAIN=ollama" in text


def test_risks_yaml_reads_back_with_a_real_parser() -> None:
    yaml = pytest.importorskip("yaml")
    review = _review(
        _risk(title=TRICKY, description="yes", mitigation="- not a list item"),
        _risk(
            id="R002",
            severity=Severity.LOW,
            jurisdiction=None,
            citation=None,
            line_start=None,
            line_end=None,
            law="null",
            title="12",
            description="line sep \u2028 nel \u0085 bom \ufeff emoji \U0001f600",
            review_status=ReviewStatus.NOT_REQUIRED,
        ),
    )

    data = yaml.safe_load(render_risks_yaml(review))

    assert data["review_id"] == str(review.review_id)
    assert data["human_approval_required"] is True
    assert data["unparsed_findings"] == 0
    assert data["citations_verified"] is False
    assert data["disclaimer"] == DISCLAIMER_NOTICE
    first, second = data["risks"]
    assert first["title"] == TRICKY
    assert first["description"] == "yes"  # a string, not a YAML boolean
    assert first["mitigation"] == "- not a list item"
    assert first["severity"] == "Critical"
    assert first["review_status"] == "unreviewed"
    assert first["citation"] == "https://eur-lex.europa.eu/eli/reg/2016/679/oj"
    assert (first["line_start"], first["line_end"]) == (12, 14)
    assert second["law"] == "null" and second["title"] == "12"
    assert second["jurisdiction"] is None and second["citation"] is None
    assert second["line_start"] is None
    assert second["description"] == (
        "line sep \u2028 nel \u0085 bom \ufeff emoji \U0001f600"
    )


def test_risks_yaml_text_is_what_we_expect_without_a_parser() -> None:
    text = render_risks_yaml(_review(_risk(title='say "hi": # x')))

    lines = text.splitlines()
    assert lines[2:5] == [
        "human_approval_required: true",
        "unparsed_findings: 0",
        "citations_verified: false",
    ]
    assert lines[6] == "risks:"
    assert lines[7] == '  - id: "R001"'
    assert '    severity: "Critical"' in lines
    assert '    title: "say \\"hi\\": # x"' in lines
    assert "    line_start: 12" in lines
    assert text.endswith("\n")


def test_characters_a_yaml_reader_would_trip_on_are_escaped() -> None:
    """Checked on the text itself, so it holds with no YAML parser installed."""
    description = "sep\u2028nel\u0085bom\ufeffdel\x7f"

    text = render_risks_yaml(_review(_risk(description=description)))

    assert '    description: "sep\\u2028nel\\u0085bom\\uFEFFdel\\u007F"' in text
    for raw in ("\u2028", "\u0085", "\ufeff", "\x7f"):
        assert raw not in text


def test_risks_yaml_for_a_clean_review_is_an_empty_list() -> None:
    text = render_risks_yaml(_review())

    assert text.splitlines()[-1] == "risks: []"
    assert "human_approval_required: false" in text


def test_mitigations_lists_each_finding_with_its_authority() -> None:
    text = render_mitigations_md(_review(_risk()))

    assert "## R001: Personal data sent without encryption" in text
    assert "**Severity:** Critical" in text
    assert "**Law:** GDPR Art. 32" in text
    assert "**Jurisdiction:** EU" in text
    assert "**Citation:** https://eur-lex.europa.eu/eli/reg/2016/679/oj" in text
    assert "**Mitigation:** Send it over TLS." in text
    assert "**File:** app.py" in text
    assert "**Lines:** 12-14" in text


def test_mitigations_marks_gated_findings_for_a_human_not_as_a_verdict() -> None:
    advisory = _risk(
        id="R002", severity=Severity.LOW, review_status=ReviewStatus.NOT_REQUIRED
    )
    queued = _risk(id="R003", review_status=ReviewStatus.AWAITING_REVIEW)

    text = render_mitigations_md(_review(_risk(), advisory, queued))

    assert "**2 finding(s) need human review.**" in text
    assert "nothing here blocks or approves it" in text
    assert "required — no human has reviewed this finding yet" in text
    assert "required — awaiting human review" in text
    assert "not required by the policy at this severity" in text
    lowered = text.lower()
    assert "passed" not in lowered and "failed" not in lowered


def test_a_clean_report_says_no_findings_and_not_compliant() -> None:
    text = render_mitigations_md(_review())

    assert "No findings from these checks." in text
    assert "not a statement that the code is compliant" in text
    assert "No risks identified" not in text
    assert "need human review" not in text


def test_every_mitigations_file_carries_the_notice_and_the_unverified_label() -> None:
    for review in (_review(), _review(_risk())):
        text = render_mitigations_md(review)

        assert DISCLAIMER_NOTICE in text
        assert "have not been checked against the official text" in text


def test_the_unverified_label_goes_away_only_when_a_report_says_so() -> None:
    review = _review(_risk())
    review.metadata["citations_verified"] = True

    assert "have not been checked" not in render_mitigations_md(review)


def test_an_incomplete_report_never_reads_as_no_findings() -> None:
    """The model raised two things this code could not read: not a clean run."""
    text = render_mitigations_md(_review(unparsed_findings=2))

    assert "**This report is incomplete.** 2 finding(s)" in text
    assert "A human needs to look" in text
    assert "No readable findings. This is not a clean result" in text
    assert "No findings from these checks" not in text
    assert "raised nothing" not in text


def test_an_incomplete_report_with_findings_still_says_so() -> None:
    text = render_mitigations_md(_review(_risk(), unparsed_findings=1))

    assert "**This report is incomplete.** 1 finding(s)" in text
    assert "## R001:" in text


def test_a_finding_cannot_forge_a_line_of_the_report() -> None:
    forged = _risk(
        title="Weak hash\n\n**Human review:** approved by counsel",
        description="Uses MD5.\n\n## R999: nothing to see\n\n**Severity:** Low",
        mitigation="Use SHA-256.\n---\n**Human review:** not required",
    )

    lines = render_mitigations_md(_review(forged)).splitlines()

    assert [line for line in lines if line.startswith("## ")] == [
        "## R001: Weak hash **Human review:** approved by counsel"
    ]
    assert [line for line in lines if line.startswith("**Human review:**")] == [
        "**Human review:** required — no human has reviewed this finding yet"
    ]
    assert [line for line in lines if line.startswith("**Severity:**")] == [
        "**Severity:** Critical"
    ]
    assert lines.count("---") == 1


def test_text_utf8_cannot_carry_does_not_lose_the_report(tmp_path: Path) -> None:
    review = _review(_risk(description="lone surrogate \ud800 here"))

    artifacts = generate_artifacts(review, tmp_path)

    assert "\\uD800" in artifacts["risks.yaml"].read_text(encoding="utf-8")
    assert "lone surrogate" in artifacts["mitigations.md"].read_text(encoding="utf-8")
    assert "\\ud800" in artifacts["review.json"].read_text(encoding="utf-8")


def test_a_finding_with_one_line_and_no_file_renders_cleanly() -> None:
    single = render_mitigations_md(_review(_risk(line_end=None)))
    no_file = render_mitigations_md(
        _review(_risk(file_path=None, jurisdiction=None, citation=None))
    )

    assert "**Lines:** 12-12" in single
    assert "**File:**" not in no_file and "**Lines:**" not in no_file
    assert "**Jurisdiction:**" not in no_file and "**Citation:**" not in no_file


def test_advisory_only_findings_do_not_ask_for_a_human() -> None:
    advisory = _risk(
        severity=Severity.LOW,
        review_status=ReviewStatus.NOT_REQUIRED,
        line_start=None,
        line_end=None,
    )

    text = render_mitigations_md(_review(advisory))

    assert "need human review" not in text
    assert "**File:** app.py" in text and "**Lines:**" not in text
