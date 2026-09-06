"""``manage.py seed_analysis_run`` — one deterministic, already-finished run.

The Analysis Studio browser spec (spec 051 / BL-20260429-27) has to assert the
*healthy* render: the IRAC brief, the precedent list and the trace-id copy
control only exist on that branch. The e2e sidecar is pinned to an unreachable
Ollama on purpose (no model bill, ever), so a live POST there can only produce
the honest degraded panel — a real end-to-end exchange, but not the one that
carries a brief.

A persisted run closes that gap without a model call. ``GET
/api/analysis/<id>`` (``AnalysisDetailView``, ``analysis`` scope) replays a
stored payload, and ``/analysis?id=…`` in the browser renders it through the
same ``ResultPanel`` a live run would. So the spec exercises the real proxy,
the real gated router and the real healthy render, and the api-auth spec
(BL-20260430-11) finally has an ``/analysis`` page visit that provokes a gated
request instead of nothing at all.

Idempotent: the row is rewritten in place under an obvious ``an-e2e-`` id, so
it can never be mistaken for a real run in a shared database.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

#: Stable id both browser specs navigate to. Matches the API's `an-` prefix.
ANALYSIS_ID = "an-e2e-demo"

#: Long enough that the spec's "the chip elides, the clipboard carries the
#: whole id" assertion is meaningful (the chip shows eight characters).
TRACE_ID = "e2e-trace-0123456789abcdef"

REQUEST: dict[str, Any] = {
    "text": (
        "A city ordinance bans door-to-door canvassing without a permit. "
        "A political group sues on First Amendment grounds."
    ),
    "jurisdiction": "US",
    "use_langgraph": False,
}

RESPONSE: dict[str, Any] = {
    "id": ANALYSIS_ID,
    "timestamp": "2026-01-15T12:00:00+00:00",
    "latency_ms": 1234,
    "confidence": 0.81,
    "requires_human_review": False,
    "irac": {
        "issue": (
            "Whether a permit requirement for door-to-door political "
            "canvassing is a valid time, place and manner restriction."
        ),
        "rule": (
            "Content-neutral restrictions on speech in a traditional public "
            "forum must be narrowly tailored to a significant government "
            "interest and leave open ample alternative channels."
        ),
        "application": (
            "The ordinance reaches all canvassing regardless of message, so "
            "it is content neutral, but a blanket permit precondition burdens "
            "anonymous political speech well beyond the stated fraud interest."
        ),
        "conclusion": (
            "The permit requirement is likely unconstitutional as applied to "
            "non-commercial political canvassing."
        ),
        "sources": [
            {
                "title": "Watchtower Bible v. Village of Stratton",
                "url": "https://example.test/opinions/e2e-watchtower",
                "verified": True,
            }
        ],
        "confidence": 0.81,
        "degraded": False,
        "requires_review": False,
    },
    "precedents": {
        "precedents": [
            {
                "case_id": "e2e-watchtower",
                "title": "Watchtower Bible v. Village of Stratton",
                "court": "Supreme Court of the United States",
                "year": 2002,
                "relevance_score": 0.92,
                "distinguishing_factors": [
                    "Concerned religious rather than partisan canvassing"
                ],
                "url": "https://example.test/opinions/e2e-watchtower",
                "retrieval_mode": "lexical",
                "source": "e2e",
                "graph_confidence": 0.9,
                "attribution": {},
            },
            {
                "case_id": "e2e-martin",
                "title": "Martin v. City of Struthers",
                "court": "Supreme Court of the United States",
                "year": 1943,
                "relevance_score": 0.74,
                "distinguishing_factors": ["Flat ban, not a permit scheme"],
                "url": "https://example.test/opinions/e2e-martin",
                "retrieval_mode": "citation_expansion",
                "source": "e2e",
                "graph_confidence": 0.8,
                "attribution": {},
            },
        ],
        "summary": "Two door-to-door canvassing decisions from the seeded corpus.",
        "confidence": 0.83,
        "degraded": False,
        "coverage_note": "Seeded e2e fixture — not a retrieval over a real corpus.",
        "trace_id": TRACE_ID,
    },
    "agent_trace": [
        {
            "agent": "LegalAnalyst",
            "trace_id": TRACE_ID,
            "latency_ms": 900.0,
            "confidence": 0.81,
        },
        {
            "agent": "PrecedentHunter",
            "trace_id": f"{TRACE_ID}-child",
            "latency_ms": 334.0,
            "confidence": 0.83,
        },
    ],
}


class Command(BaseCommand):
    help = "Seed one deterministic, already-finished AnalysisRun for the e2e specs."

    def handle(self, *args: object, **options: object) -> None:
        from law_ai.analysis.models import AnalysisRun

        run, created = AnalysisRun.objects.update_or_create(
            analysis_id=ANALYSIS_ID,
            defaults={
                "request": REQUEST,
                "response": RESPONSE,
                "trace_id": TRACE_ID,
                "child_trace_ids": [f"{TRACE_ID}-child"],
                "engine": AnalysisRun.ENGINE_DIRECT,
                "confidence": RESPONSE["confidence"],
                "requires_human_review": False,
                # A re-run must undo an archive, or the spec 404s forever.
                "archived_at": None,
                "shareable": True,
            },
        )
        verb = "created" if created else "refreshed"
        self.stdout.write(
            self.style.SUCCESS(f"seed_analysis_run: {verb} {run.analysis_id}")
        )
