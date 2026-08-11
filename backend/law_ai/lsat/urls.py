"""LSAT Lab API (spec 005 → spec 011 FR-9 port)."""

from __future__ import annotations

import logging
import random
from typing import Any

from asgiref.sync import async_to_sync
from django.http import Http404
from django.urls import path
from pydantic import BaseModel, ValidationError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from law_ai.core import audit_jsonl as audit_store
from law_ai.core.auth import RequireLsat
from law_ai.lsat.services.bank import (
    ChoiceLabel,
    Difficulty,
    Section,
    load_bank,
    load_concepts,
    load_passages,
    load_sections,
    public_view,
)
from law_ai.lsat.services import proposals as proposals_store
from law_ai.lsat.services.tutor import TutorRequest, TutorResponse, tutor

logger = logging.getLogger("law_ai.lsat")


class GradeRequest(BaseModel):
    question_id: str
    choice: ChoiceLabel


class GradeResponse(BaseModel):
    question_id: str
    correct: bool
    correct_choice: ChoiceLabel
    explanation: str
    section: Section
    concepts: list[str] = []


def _bounded_int(raw: str | None, *, default: int, lo: int, hi: int) -> int:
    if raw is None:
        return default

    class _Unprocessable(APIException):
        status_code = 422
        default_code = "unprocessable_entity"

    try:
        value = int(raw)
    except ValueError as exc:
        raise _Unprocessable({"limit": "must be an integer"}) from exc
    if value < lo or value > hi:
        raise _Unprocessable({"limit": f"must be between {lo} and {hi}"})
    return value


class _Base(APIView):
    permission_classes = [RequireLsat]


class SectionsView(_Base):
    def get(self, request, *args, **kwargs):
        sections = load_sections()
        bank = load_bank()
        counts = {code: 0 for code in sections}
        for q in bank.values():
            counts[q.section] = counts.get(q.section, 0) + 1
        return Response(
            {
                "sections": [
                    {**s.model_dump(), "question_count": counts.get(s.code, 0)}
                    for s in sections.values()
                ],
                "count": len(sections),
            }
        )


class SectionDetailView(_Base):
    def get(self, request, code: str, *args, **kwargs):
        sections = load_sections()
        section = sections.get(code)
        if section is None:
            raise Http404("section not found")
        bank = load_bank()
        questions = [
            public_view(q).model_dump() for q in bank.values() if q.section == code
        ]
        return Response(
            {
                "section": section.model_dump(),
                "question_count": len(questions),
                "sample_question_ids": [q["id"] for q in questions[:5]],
            }
        )


class ConceptsView(_Base):
    def get(self, request, *args, **kwargs):
        section = request.query_params.get("section")
        items = list(load_concepts().values())
        if section:
            items = [c for c in items if section in c.sections]
        return Response(
            {"concepts": [c.model_dump() for c in items], "count": len(items)}
        )


class ConceptDetailView(_Base):
    def get(self, request, concept_id: str, *args, **kwargs):
        concept = load_concepts().get(concept_id)
        if concept is None:
            raise Http404("concept not found")
        bank = load_bank()
        used_in = [q.id for q in bank.values() if concept_id in q.concepts][:10]
        return Response({"concept": concept.model_dump(), "used_in_questions": used_in})


class PassagesView(_Base):
    def get(self, request, *args, **kwargs):
        section = request.query_params.get("section")
        items = list(load_passages().values())
        if section:
            items = [p for p in items if p.section == section]
        return Response(
            {"passages": [p.model_dump() for p in items], "count": len(items)}
        )


class PassageDetailView(_Base):
    def get(self, request, passage_id: str, *args, **kwargs):
        passage = load_passages().get(passage_id)
        if passage is None:
            raise Http404("passage not found")
        bank = load_bank()
        questions = [
            public_view(q).model_dump()
            for q in bank.values()
            if q.passage_id == passage_id
        ]
        questions.sort(key=lambda q: q["id"])
        return Response(
            {
                "passage": passage.model_dump(),
                "questions": questions,
                "count": len(questions),
            }
        )


class QuestionsView(_Base):
    def get(self, request, *args, **kwargs):
        limit = _bounded_int(request.query_params.get("limit"), default=5, lo=1, hi=25)
        difficulty = request.query_params.get("difficulty")
        section = request.query_params.get("section")
        passage_id = request.query_params.get("passage_id")
        bank = load_bank()
        pool = [
            q
            for q in bank.values()
            if (difficulty is None or q.difficulty == difficulty)
            and (section is None or q.section == section)
            and (passage_id is None or q.passage_id == passage_id)
        ]
        if not pool:
            return Response({"questions": [], "count": 0})
        if passage_id:
            sample = sorted(pool, key=lambda q: q.id)[:limit]
        else:
            sample = random.sample(pool, min(limit, len(pool)))
        return Response(
            {
                "questions": [public_view(q).model_dump() for q in sample],
                "count": len(sample),
            }
        )


class QuestionDetailView(_Base):
    def get(self, request, question_id: str, *args, **kwargs):
        bank = load_bank()
        q = bank.get(question_id)
        if q is None:
            raise Http404("question not found")
        return Response(public_view(q).model_dump())


class GradeView(_Base):
    def post(self, request, *args, **kwargs):
        try:
            req = GradeRequest.model_validate(request.data)
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        bank = load_bank()
        q = bank.get(req.question_id)
        if q is None:
            raise Http404("question not found")
        is_correct = req.choice == q.correct
        body = GradeResponse(
            question_id=q.id,
            correct=is_correct,
            correct_choice=q.correct,
            explanation=q.explanation,
            section=q.section,
            concepts=list(q.concepts),
        )
        try:
            audit_store.record(
                {
                    "type": "lsat_grade",
                    "question_id": q.id,
                    "section": q.section,
                    "choice": req.choice,
                    "correct": is_correct,
                    "difficulty": q.difficulty,
                    "concepts": list(q.concepts),
                }
            )
        except Exception:
            logger.warning("audit_store.record failed for lsat_grade", exc_info=True)
        return Response(body.model_dump())


class StatsView(_Base):
    def get(self, request, *args, **kwargs):
        section = request.query_params.get("section")
        events = audit_store.tail(10_000)
        grades = [e for e in events if e.get("type") == "lsat_grade"]
        if section:
            grades = [e for e in grades if e.get("section") == section]
        attempts = len(grades)
        correct = sum(1 for e in grades if e.get("correct") is True)
        accuracy = (correct / attempts) if attempts else 0.0
        by_section: dict[str, dict[str, Any]] = {}
        for e in grades:
            sec = str(e.get("section") or "?")
            bucket = by_section.setdefault(sec, {"attempts": 0, "correct": 0})
            bucket["attempts"] += 1
            if e.get("correct"):
                bucket["correct"] += 1
        for bucket in by_section.values():
            a = bucket["attempts"] or 1
            bucket["accuracy"] = round(bucket["correct"] / a, 4)
        return Response(
            {
                "attempts": attempts,
                "correct": correct,
                "accuracy": round(accuracy, 4),
                "by_section": by_section,
            }
        )


class TutorView(_Base):
    # BL-20260810-11: the only LSAT endpoint that invokes an LLM.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "llm"

    def post(self, request, *args, **kwargs):
        try:
            req = TutorRequest.model_validate(request.data)
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        bank = load_bank()
        q = bank.get(req.question_id)
        if q is None:
            raise Http404("question not found")
        body: TutorResponse = async_to_sync(tutor)(req, q)
        return Response(body.model_dump())


# ---------------------------------------------------------------------------
# Authoring / proposal endpoints (spec 019 FR-7)
# ---------------------------------------------------------------------------


class _GenerateProposalsRequest(BaseModel):
    section: Section
    difficulty: Difficulty
    count: int = 1
    concepts: list[str] = []
    passage_id: str | None = None


class ProposalsView(_Base):
    """``GET /api/lsat/proposals`` — list proposals filtered by status."""

    def get(self, request, *args, **kwargs):
        status_q = request.query_params.get("status", "pending")
        limit = _bounded_int(
            request.query_params.get("limit"), default=200, lo=1, hi=1000
        )
        rows = proposals_store.list_proposals(status=status_q, limit=limit)
        return Response({"proposals": rows, "count": len(rows), "status": status_q})


class ProposalGenerateView(_Base):
    """``POST /api/lsat/proposals/generate`` — synchronously draft N questions."""

    def post(self, request, *args, **kwargs):
        try:
            req = _GenerateProposalsRequest.model_validate(request.data)
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        from law_ai.agents_runtime.crews.lsat_content_author import (
            GenerateQuestionsInput,
            LSATContentAuthor,
        )

        agent = LSATContentAuthor()
        try:
            output = async_to_sync(agent.run)(
                GenerateQuestionsInput(**req.model_dump()).model_dump()
            )
        except Exception as exc:
            logger.exception("LSATContentAuthor.run failed: %s", exc)
            return Response(
                {"detail": f"draft generation failed: {type(exc).__name__}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        persisted: list[dict[str, Any]] = []
        for draft in output.drafts:
            pid = proposals_store.record_proposal(
                draft.model_dump(),
                agent_trace_id=output.trace_id or "",
                model=output.model,
                confidence=output.confidence,
                source_concept_ids=req.concepts,
            )
            row = proposals_store.get_proposal(pid)
            if row is not None:
                persisted.append(row)
        return Response(
            {
                "proposals": persisted,
                "trace_id": output.trace_id,
                "model": output.model,
                "degraded": output.degraded,
                "count": len(persisted),
            }
        )


class _StatusUpdateRequest(BaseModel):
    note: str | None = None
    reviewer: str | None = None


class ProposalApproveView(_Base):
    """``POST /api/lsat/proposals/<id>/approve`` — promote draft to bank."""

    def post(self, request, proposal_id: str, *args, **kwargs):
        try:
            req = _StatusUpdateRequest.model_validate(request.data or {})
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        try:
            row = proposals_store.promote_to_bank(
                proposal_id,
                reviewer=req.reviewer or "anonymous",
                note=req.note,
            )
        except KeyError as exc:
            raise Http404("proposal not found") from exc
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(row)


class ProposalRejectView(_Base):
    """``POST /api/lsat/proposals/<id>/reject`` — mark draft rejected."""

    def post(self, request, proposal_id: str, *args, **kwargs):
        try:
            req = _StatusUpdateRequest.model_validate(request.data or {})
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        existing = proposals_store.get_proposal(proposal_id)
        if existing is None:
            raise Http404("proposal not found")
        if existing.get("status") != "pending":
            return Response(
                {"detail": f"already {existing.get('status')}"},
                status=status.HTTP_409_CONFLICT,
            )
        row = proposals_store.set_status(
            proposal_id,
            "rejected",
            reviewer=req.reviewer or "anonymous",
            note=req.note,
        )
        return Response(row)


class GapsView(_Base):
    """``GET /api/lsat/gaps`` — weakest `(section, concept)` pairs."""

    def get(self, request, *args, **kwargs):
        limit = _bounded_int(
            request.query_params.get("limit"), default=10, lo=1, hi=100
        )
        gaps = proposals_store.gap_analysis(limit=limit)
        return Response({"gaps": gaps, "count": len(gaps), "limit": limit})


urlpatterns = [
    path("sections", SectionsView.as_view(), name="lsat-sections"),
    path(
        "sections/<str:code>", SectionDetailView.as_view(), name="lsat-section-detail"
    ),
    path("concepts", ConceptsView.as_view(), name="lsat-concepts"),
    path(
        "concepts/<str:concept_id>",
        ConceptDetailView.as_view(),
        name="lsat-concept-detail",
    ),
    path("passages", PassagesView.as_view(), name="lsat-passages"),
    path(
        "passages/<str:passage_id>",
        PassageDetailView.as_view(),
        name="lsat-passage-detail",
    ),
    path("questions", QuestionsView.as_view(), name="lsat-questions"),
    path(
        "questions/<str:question_id>",
        QuestionDetailView.as_view(),
        name="lsat-question-detail",
    ),
    path("grade", GradeView.as_view(), name="lsat-grade"),
    path("stats", StatsView.as_view(), name="lsat-stats"),
    path("tutor", TutorView.as_view(), name="lsat-tutor"),
    # Authoring / HITL proposal queue (spec 019 FR-7)
    path("proposals", ProposalsView.as_view(), name="lsat-proposals"),
    path(
        "proposals/generate",
        ProposalGenerateView.as_view(),
        name="lsat-proposals-generate",
    ),
    path(
        "proposals/<str:proposal_id>/approve",
        ProposalApproveView.as_view(),
        name="lsat-proposals-approve",
    ),
    path(
        "proposals/<str:proposal_id>/reject",
        ProposalRejectView.as_view(),
        name="lsat-proposals-reject",
    ),
    path("gaps", GapsView.as_view(), name="lsat-gaps"),
]
