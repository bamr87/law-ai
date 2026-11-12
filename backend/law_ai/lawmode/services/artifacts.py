"""Report artifacts for a lawmode review.

Ported from ``LawModeAgent.generate_artifacts`` in ``lawmode/lawmode/core.py``:
the same four files lawmode wrote under ``.lawmode/`` — ``review.json``,
``risks.yaml``, ``mitigations.md`` and ``DISCLAIMER.md``.

Differences from the original, all deliberate:

* ``risks.yaml`` is written without a YAML library. The backend has no direct
  YAML dependency and spec 057 adds none (NFR-DEP-1), and the file is a flat
  list of scalars, so :func:`_yaml_scalar` emits each string as a
  double-quoted scalar and nothing else is needed.
* The chain-history dump (``.lawmode/history/<id>_history.json``) is not
  ported. It copied the reviewed source code into a dot-directory; the audit
  record is the ``lawmode_review`` provenance event, which holds a SHA-256 of
  the code instead.
* There is no default output directory. lawmode wrote to ``.lawmode/`` under
  whatever the working directory happened to be; the caller says where.
* Model-written text is rendered on one line per field in ``mitigations.md``,
  so a finding cannot write report lines of its own (a second
  "**Human review:**" line, say).
* ``DISCLAIMER.md`` is written on every run from the one packaged
  ``disclaimer.md``, so a stale copy never sits next to a new report.
* A report with no findings says "no findings from these checks", and says
  that this is not compliance (spec 057 §2). A report with findings the model
  returned but this code could not read says it is incomplete instead.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from law_ai.lawmode.schemas import DISCLAIMER_NOTICE, ReviewResult, ReviewStatus, Risk

DISCLAIMER_PATH = Path(__file__).resolve().parents[1] / "disclaimer.md"

_REVIEW_NOTES = {
    ReviewStatus.UNREVIEWED: "required — no human has reviewed this finding yet",
    ReviewStatus.AWAITING_REVIEW: "required — awaiting human review",
    ReviewStatus.NOT_REQUIRED: "not required by the policy at this severity",
}

# Characters json.dumps leaves literal that a YAML reader would reject or read
# as a line break inside a double-quoted scalar: DEL and the C1 controls, the
# Unicode line/paragraph separators, lone surrogates, the BOM and the two
# non-characters.
_YAML_UNSAFE = re.compile(r"[\x7f-\x9f\u2028\u2029\ud800-\udfff\ufeff\ufffe\uffff]")


def load_disclaimer() -> str:
    """The full lawmode disclaimer, from the one packaged ``disclaimer.md``.

    >>> "NOT LEGAL ADVICE" in load_disclaimer()
    True
    """
    return DISCLAIMER_PATH.read_text(encoding="utf-8")


def _yaml_scalar(value: object) -> str:
    """One YAML scalar. Strings are always double-quoted, so no value can be
    re-read as a number, a boolean, a mapping key or a comment.

    >>> _yaml_scalar("GDPR Art. 32: security"), _yaml_scalar(None), _yaml_scalar(3)
    ('"GDPR Art. 32: security"', 'null', '3')
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    quoted = json.dumps(str(value), ensure_ascii=False)
    return _YAML_UNSAFE.sub(lambda match: f"\\u{ord(match.group()):04X}", quoted)


def _one_line(value: object) -> str:
    """Model-written text as a single line of Markdown.

    >>> _one_line("first" + chr(10) + chr(10) + "**Human review:** approved")
    'first **Human review:** approved'
    """
    return " ".join(str(value).split())


def _risk_fields(risk: Risk) -> list[tuple[str, object]]:
    return [
        ("id", risk.id),
        ("severity", risk.severity.value),
        ("review_status", risk.review_status.value),
        ("title", risk.title),
        ("law", risk.law),
        ("jurisdiction", risk.jurisdiction),
        ("citation", str(risk.citation) if risk.citation else None),
        ("description", risk.description),
        ("mitigation", risk.mitigation),
        ("file_path", risk.file_path),
        ("line_start", risk.line_start),
        ("line_end", risk.line_end),
    ]


def render_risks_yaml(review: ReviewResult) -> str:
    """``risks.yaml``: the findings as a flat YAML document.

    >>> print(render_risks_yaml(ReviewResult()).splitlines()[-1])
    risks: []
    """
    lines = [
        f"review_id: {_yaml_scalar(str(review.review_id))}",
        f"timestamp: {_yaml_scalar(review.timestamp.isoformat())}",
        f"human_approval_required: {_yaml_scalar(review.human_approval_required)}",
        f"unparsed_findings: {_yaml_scalar(review.unparsed_findings)}",
        "citations_verified: "
        + _yaml_scalar(bool(review.metadata.get("citations_verified", False))),
        f"disclaimer: {_yaml_scalar(review.disclaimer)}",
    ]
    if not review.risks:
        lines.append("risks: []")
    else:
        lines.append("risks:")
        for risk in review.risks:
            for position, (key, value) in enumerate(_risk_fields(risk)):
                prefix = "  - " if position == 0 else "    "
                lines.append(f"{prefix}{key}: {_yaml_scalar(value)}")
    return "\n".join(lines) + "\n"


def render_mitigations_md(review: ReviewResult) -> str:
    """``mitigations.md``: the findings for a person to read.

    >>> "No findings from these checks" in render_mitigations_md(ReviewResult())
    True
    """
    out = [
        "# Legal Risk Mitigations",
        "",
        f"**Review ID:** {review.review_id}",
        f"**Timestamp:** {review.timestamp.isoformat()}",
        "",
        f"> {DISCLAIMER_NOTICE} See DISCLAIMER.md.",
        "",
    ]
    if not review.metadata.get("citations_verified", False):
        out += [
            "> The authorities and links below were named by the model and have "
            "not been checked against the official text.",
            "",
        ]
    if review.unparsed_findings:
        out += [
            f"> **This report is incomplete.** {review.unparsed_findings} "
            "finding(s) in the model's reply could not be read and are not "
            "listed here. A human needs to look: re-run the review, or treat "
            "this code as not reviewed.",
            "",
        ]

    if not review.risks:
        out += [
            (
                "No readable findings. This is not a clean result — see the "
                "note above."
                if review.unparsed_findings
                else "No findings from these checks. This is not a statement "
                "that the code is compliant: it means this review raised "
                "nothing in the code it was given."
            ),
            "",
        ]
        return "\n".join(out)

    gated = len(review.risks_requiring_review())
    if gated:
        out += [
            f"**{gated} finding(s) need human review.** They are not a verdict "
            "on this change: nothing here blocks or approves it.",
            "",
        ]
    for risk in review.risks:
        out += [
            f"## {risk.id}: {_one_line(risk.title)}",
            "",
            f"**Severity:** {risk.severity.value}",
            "",
            f"**Human review:** {_REVIEW_NOTES[risk.review_status]}",
            "",
            f"**Law:** {_one_line(risk.law)}",
            "",
        ]
        if risk.jurisdiction:
            out += [f"**Jurisdiction:** {_one_line(risk.jurisdiction)}", ""]
        if risk.citation:
            out += [f"**Citation:** {risk.citation}", ""]
        out += [
            f"**Description:** {_one_line(risk.description)}",
            "",
            f"**Mitigation:** {_one_line(risk.mitigation)}",
            "",
        ]
        if risk.file_path:
            out.append(f"**File:** {_one_line(risk.file_path)}")
            if risk.line_start:
                out.append(
                    f"**Lines:** {risk.line_start}-{risk.line_end or risk.line_start}"
                )
            out.append("")
        out += ["---", ""]
    return "\n".join(out)


def generate_artifacts(
    review: ReviewResult, artifact_dir: Path | str
) -> dict[str, Path]:
    """Generate legal review artifacts.

    Writes ``review.json``, ``risks.yaml``, ``mitigations.md`` and
    ``DISCLAIMER.md`` into ``artifact_dir`` (created if missing) and returns
    their paths keyed by file name.

    >>> import tempfile
    >>> sorted(generate_artifacts(ReviewResult(), tempfile.mkdtemp()))
    ['DISCLAIMER.md', 'mitigations.md', 'review.json', 'risks.yaml']
    """
    directory = Path(artifact_dir)
    directory.mkdir(parents=True, exist_ok=True)

    contents = {
        "review.json": json.dumps(review.model_dump(mode="json"), indent=2) + "\n",
        "risks.yaml": render_risks_yaml(review),
        "mitigations.md": render_mitigations_md(review),
        "DISCLAIMER.md": load_disclaimer(),
    }
    artifacts: dict[str, Path] = {}
    for name, text in contents.items():
        path = directory / name
        # "replace": a report is still written if a field was built by hand
        # with a character UTF-8 cannot carry.
        path.write_text(text, encoding="utf-8", errors="replace")
        artifacts[name] = path
    return artifacts
