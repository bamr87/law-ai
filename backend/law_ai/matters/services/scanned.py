"""A scanned page filed on a matter — the matter half of the ocrmd plug-in (spec 053).

A page a scanner has read becomes a ``document`` artifact on the user's matter: the
reconciled text, the scanner's provenance and the book's catalogue entry in ``body``,
``source="ocrmd"``, ``confidence`` = the scanner's own agreement score. Nothing is
analysed and nothing reaches the graph; the artifact is the user's, on the user's matter,
which is why the door is signed-in only like every other matter route.

Filing twice is safe: a page id already filed on this matter (same region, when one was
boxed) answers with the artifact it already made, so "did that go through?" is answered
by pressing the button again — the contract ocrmd's sinks are written against.
"""

from __future__ import annotations

from typing import Any

from law_ai.core.provenance import provenance
from law_ai.ingestionapp.services.ocrmd_plugin import (
    TOOL,
    Envelope,
    descriptor,
    option,
)
from law_ai.matters.models import Matter, MatterArtifact


def matter_descriptor(matter: Matter) -> dict[str, Any]:
    return descriptor(
        f"Law AI — matter: {matter.name}",
        "Files the page as a source document on this matter. Nothing is analysed or "
        "published; the scanner's provenance travels with the text.",
        [
            option(
                "title",
                "string",
                label="title",
                help_="defaults to the book and printed page",
            ),
            option("note", "string", label="note"),
        ],
    )


def find_filed(matter: Matter, env: Envelope) -> MatterArtifact | None:
    """The artifact this page (and region) already became on this matter, if any."""
    prov = env.provenance
    if not prov.page_id:
        return None
    rows = matter.artifacts.filter(
        archived_at__isnull=True,
        kind=MatterArtifact.KIND_DOCUMENT,
        source=TOOL,
        body__provenance__page_id=prov.page_id,
    )
    for artifact in rows:
        body = artifact.body or {}
        filed_bbox = (body.get("provenance") or {}).get("bbox")
        if filed_bbox == prov.bbox:
            return artifact
    return None


def file_page(matter: Matter, env: Envelope, user: Any) -> tuple[MatterArtifact, bool]:
    """File the envelope as a document artifact. Returns ``(artifact, created)``."""
    existing = find_filed(matter, env)
    if existing is not None:
        return existing, False
    prov = env.provenance
    title = str(env.options.get("title") or "").strip() or env.default_title()
    artifact = MatterArtifact.objects.create(
        matter=matter,
        kind=MatterArtifact.KIND_DOCUMENT,
        title=title[:200],
        body={
            "text": env.text,
            "kind": env.kind,
            "provenance": prov.model_dump(),
            "document": env.document.model_dump(),
            "note": str(env.options.get("note") or ""),
            "sink_contract": env.ocrmd,
        },
        source=TOOL,
        confidence=float(prov.agreement or 0.0),
        created_by=user if getattr(user, "pk", None) else None,
    )
    provenance.log_event(
        "matter.artifact_added",
        {
            "matter_id": matter.pk,
            "artifact_id": artifact.pk,
            "kind": artifact.kind,
            "trace_id": artifact.trace_id,
            "source": TOOL,
        },
    )
    provenance.log_event(
        "ocrmd_intake",
        {
            "door": "matter",
            "matter_id": matter.pk,
            "artifact_id": artifact.pk,
            "document": prov.document,
            "page": prov.page,
            "page_id": prov.page_id,
            "traceable": prov.is_traceable(),
            "chars": len(env.text),
            "agreement": prov.agreement,
            "status": prov.status,
        },
    )
    return artifact, True


def delivery(
    matter: Matter, artifact: MatterArtifact, created: bool, env: Envelope
) -> dict[str, Any]:
    """The answer in the sink contract's terms: a summary, one item, the scanner's caveats."""
    verb = "filed" if created else "already filed"
    return {
        "summary": f"{verb} as document #{artifact.pk} on {matter.name}",
        "items": [
            {
                "id": artifact.pk,
                "title": artifact.title,
                "detail": f"document · confidence {artifact.confidence:.2f}",
                "status": "filed",
            }
        ],
        "warnings": env.provenance.caveats(),
        "artifact": artifact.as_payload(),
        "created": created,
    }
