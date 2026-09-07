"""Matter export bundle (BL-20260817-01, half one).

Once a user-owned matter holds client facts, "let me have my data" stops
being a feature request and becomes a privacy obligation. The bundle is a
single self-describing JSON document: the matter, every artifact with its
provenance ids, every authority, every task, the persisted analyses the
artifacts point at, and a timeline that merges all of it into one ordered
narrative of what happened.

Two deliberate properties:

* **Provenance ids travel with the data.** Each artifact carries its
  ``trace_id``, so an exported bundle can still be joined back to the audit
  log — an export that dropped them would be a copy the user could not verify.
* **Archived rows are included, and marked.** A soft-deleted artifact is still
  the user's data (§5 says nothing is hard-deleted); hiding it from their own
  export would make the export a lie.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

#: Bumped when the bundle's shape changes incompatibly.
BUNDLE_VERSION = 1


def _analysis_payloads(analysis_ids: list[str]) -> list[dict[str, Any]]:
    if not analysis_ids:
        return []
    try:
        from law_ai.analysis.models import AnalysisRun
    except Exception:  # pragma: no cover - app not installed
        return []
    rows = AnalysisRun.objects.filter(analysis_id__in=analysis_ids)
    return [row.as_payload() for row in rows]


def _timeline(matter: Any) -> list[dict[str, Any]]:
    """Everything that happened in this matter, oldest first."""
    events: list[dict[str, Any]] = [
        {
            "at": matter.created_at.isoformat() if matter.created_at else None,
            "kind": "matter.created",
            "label": matter.name,
        }
    ]
    for artifact in matter.artifacts.all():
        events.append(
            {
                "at": (
                    artifact.created_at.isoformat() if artifact.created_at else None
                ),
                "kind": f"artifact.{artifact.kind}",
                "label": artifact.title or artifact.kind,
                "trace_id": artifact.trace_id,
                "archived": artifact.archived_at is not None,
            }
        )
    for authority in matter.authorities.all():
        events.append(
            {
                "at": (
                    authority.created_at.isoformat() if authority.created_at else None
                ),
                "kind": "authority.recorded",
                "label": authority.citation or authority.node_id,
                "verified": authority.verified_at is not None,
            }
        )
    for task in matter.tasks.all():
        events.append(
            {
                "at": task.created_at.isoformat() if task.created_at else None,
                "kind": "task.created",
                "label": task.title,
                "due_at": task.due_at.isoformat() if task.due_at else None,
                "status": task.status,
            }
        )
        if task.completed_at:
            events.append(
                {
                    "at": task.completed_at.isoformat(),
                    "kind": "task.completed",
                    "label": task.title,
                }
            )
    events.sort(key=lambda e: (e["at"] or ""))
    return events


def export_matter(matter: Any, *, log: bool = True) -> dict[str, Any]:
    """Build the portability bundle for one matter."""
    artifacts = list(matter.artifacts.all())
    bundle = {
        "bundle_version": BUNDLE_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "matter": matter.as_payload(),
        "artifacts": [
            {**a.as_payload(), "archived": a.archived_at is not None} for a in artifacts
        ],
        "authorities": [
            {**a.as_payload(), "archived": a.archived_at is not None}
            for a in matter.authorities.all()
        ],
        "tasks": [
            {**t.as_payload(), "archived": t.archived_at is not None}
            for t in matter.tasks.all()
        ],
        "analyses": _analysis_payloads(
            [a.analysis_id for a in artifacts if a.analysis_id]
        ),
        "timeline": _timeline(matter),
        "disclaimer": (
            "Exported from Law AI. AI-generated content in this bundle is not "
            "legal advice and may be incomplete or wrong."
        ),
    }
    if log:
        from law_ai.core.provenance import provenance

        provenance.log_event(
            "matter.exported",
            {
                "matter_id": matter.pk,
                "slug": matter.slug,
                "artifacts": len(bundle["artifacts"]),
                "authorities": len(bundle["authorities"]),
                "tasks": len(bundle["tasks"]),
            },
        )
    return bundle


__all__ = ["BUNDLE_VERSION", "export_matter"]
