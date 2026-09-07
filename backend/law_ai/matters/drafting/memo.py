"""Deterministic memo composition with a provenance footer (BL-20260817-03).

The drafting stage the item asks for has two halves. This is the half that
can ship without new runtime dependencies: composing a matter's artifacts
into a memo, with Bluebook-formatted authorities and a footer that says
exactly where the content came from.

The composition is **deterministic** — it arranges what is already stored and
never calls a model. That is what makes the provenance footer honest: every
line in the memo traces to an artifact row, and the footer lists those
artifacts' trace ids so a reader can pull the audit trail for each.

Markdown is the output format here. DOCX and PDF renderers are the remaining
half of the item and need `python-docx` plus a PDF engine in the backend
image; the composition seam is shaped so they render *this* structure rather
than re-deriving it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from law_ai.matters.drafting.bluebook import format_citation, format_table

DISCLAIMER = (
    "DRAFT — not legal advice. Assembled by Law AI from the artifacts recorded "
    "in this matter. Every citation must be verified against the issuing "
    "authority before use."
)


def _artifact_section(artifact: Any) -> list[str]:
    body = artifact.body if isinstance(artifact.body, dict) else {}
    lines = [f"### {artifact.title or artifact.kind}", ""]
    for key in ("issue", "rule", "application", "conclusion", "summary", "text"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            label = key.capitalize()
            lines.append(f"**{label}.** {value.strip()}")
            lines.append("")
    if len(lines) == 2:
        lines.append("_(no narrative content stored on this artifact)_")
        lines.append("")
    return lines


def compose_memo(matter: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Build the memo for ``matter`` as structure plus rendered Markdown."""
    moment = now or datetime.now(UTC)
    artifacts = [
        a
        for a in matter.artifacts.filter(archived_at__isnull=True)
        if a.kind in {"analysis", "research", "draft", "note"}
    ]
    authorities = list(matter.authorities.filter(archived_at__isnull=True))

    lines: list[str] = [
        f"# Memorandum — {matter.name}",
        "",
        f"**Matter:** {matter.slug}  ",
        f"**Prepared:** {moment.date().isoformat()}  ",
        f"**Jurisdiction:** {matter.jurisdiction or 'not stated'}  ",
        f"**Issues:** {', '.join(matter.issue_tags or []) or 'not stated'}",
        "",
        f"> {DISCLAIMER}",
        "",
        "## Discussion",
        "",
    ]
    for artifact in artifacts:
        lines.extend(_artifact_section(artifact))

    if not artifacts:
        lines.extend(["_(nothing filed under this matter yet)_", ""])

    verified = [a for a in authorities if a.verified_at is not None]
    unverified = [a for a in authorities if a.verified_at is None]
    lines.extend(["## Table of authorities", ""])
    if verified:
        for citation in format_table(
            [
                {
                    "node_label": a.node_label,
                    "title": a.title,
                    "citation": a.citation,
                }
                for a in verified
            ]
        ):
            lines.append(f"- {citation}")
    else:
        lines.append("_(no verified authorities)_")
    lines.append("")
    if unverified:
        # Unverified authorities are listed *separately* and labelled. Mixing
        # them into the table would let an unchecked citation read as checked.
        lines.extend(["### Recorded but not yet verified", ""])
        for authority in unverified:
            lines.append(
                f"- {format_citation({'node_label': authority.node_label, 'title': authority.title, 'citation': authority.citation})}"
            )
        lines.append("")

    lines.extend(["## Provenance", ""])
    for artifact in artifacts:
        trace = artifact.trace_id or "(no trace)"
        lines.append(
            f"- {artifact.title or artifact.kind} — trace `{trace}`"
            + (f", analysis `{artifact.analysis_id}`" if artifact.analysis_id else "")
        )
    if not artifacts:
        lines.append("- (nothing to attribute)")
    lines.append("")
    lines.append(
        f"_Composed deterministically from {len(artifacts)} artifact(s) "
        f"and {len(authorities)} authority record(s); no model wrote "
        "this document._"
    )

    return {
        "matter": matter.slug,
        "format": "markdown",
        "generated_at": moment.isoformat(),
        "disclaimer": DISCLAIMER,
        "artifact_count": len(artifacts),
        "authority_count": len(authorities),
        "trace_ids": [a.trace_id for a in artifacts if a.trace_id],
        "markdown": "\n".join(lines),
    }


__all__ = ["DISCLAIMER", "compose_memo"]
