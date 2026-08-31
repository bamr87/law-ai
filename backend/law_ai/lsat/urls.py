"""LSAT Lab API (spec 005 → spec 011 FR-9 port)."""

from __future__ import annotations

import logging
import random
from typing import Any

from asgiref.sync import async_to_sync
from django.http import Http404
from django.urls import path
from pydantic import BaseModel, Field, ValidationError
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
from law_ai.lsat.services.crosscheck import CrossCheckResult, cross_check
from law_ai.lsat.services.guides import load_guides, public_guide_view
from law_ai.lsat.services.tutor import TutorRequest, TutorResponse, tutor
from law_ai.lsat.services.validation import validate_question_set

logger = logging.getLogger("law_ai.lsat")


class GradeRequest(BaseModel):
    question_id: str
    choice: ChoiceLabel
    # Spec 041 FR-5: how many solve-guide steps the client revealed before
    # answering. None = client predates the hint system.
    hints_used: int | None = Field(default=None, ge=0, le=20)


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


class GuideView(_Base):
    """``GET /api/lsat/questions/<id>/guide`` — progressive solve guide.

    Spec 041 FR-4. Spoiler-step content is withheld unless ``?spoilers=1``
    (the client asks only after grading — same soft protection level as the
    grade endpoint itself). 404 carries ``has_tutor`` so the UI can fall
    back to the AI tutor for guide-less questions.
    """

    def get(
        self, request: Any, question_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        q = load_bank().get(question_id)
        guide = load_guides().get(question_id)
        if q is None or guide is None:
            return Response(
                {
                    "detail": "no solve guide for this question",
                    "has_tutor": q is not None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        include_spoilers = request.query_params.get("spoilers") in ("1", "true")
        body = public_guide_view(guide, include_spoilers=include_spoilers)
        try:
            audit_store.record(
                {
                    "type": "lsat_guide",
                    "question_id": q.id,
                    "section": q.section,
                    "spoilers": include_spoilers,
                    "step_count": body["step_count"],
                }
            )
        except Exception:
            logger.warning("audit_store.record failed for lsat_guide", exc_info=True)
        return Response(body)


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
                    "hints_used": req.hints_used,
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

        def _assisted(e: dict[str, Any]) -> bool:
            hints = e.get("hints_used")
            return isinstance(hints, int) and hints > 0

        assisted = sum(1 for e in grades if _assisted(e))
        by_section: dict[str, dict[str, Any]] = {}
        for e in grades:
            sec = str(e.get("section") or "?")
            bucket = by_section.setdefault(
                sec, {"attempts": 0, "correct": 0, "assisted": 0}
            )
            bucket["attempts"] += 1
            if e.get("correct"):
                bucket["correct"] += 1
            if _assisted(e):
                bucket["assisted"] += 1
        for bucket in by_section.values():
            a = bucket["attempts"] or 1
            bucket["accuracy"] = round(bucket["correct"] / a, 4)
            bucket["unassisted"] = bucket["attempts"] - bucket["assisted"]
        return Response(
            {
                "attempts": attempts,
                "correct": correct,
                "accuracy": round(accuracy, 4),
                "assisted": assisted,
                "unassisted": attempts - assisted,
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


class _CrossCheckRequest(BaseModel):
    refresh: bool = False


class CrossCheckView(_Base):
    """``POST /api/lsat/questions/<id>/cross-check`` — spec 041 FR-14.

    Solves the question blind through the provider chain and compares the
    pick against the answer key. Verdicts are cached; ``refresh`` re-solves.
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "llm"

    def post(
        self, request: Any, question_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        try:
            req = _CrossCheckRequest.model_validate(request.data or {})
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        q = load_bank().get(question_id)
        if q is None:
            raise Http404("question not found")
        body: CrossCheckResult = async_to_sync(cross_check)(q, refresh=req.refresh)
        return Response(body.model_dump())


class ValidationView(_Base):
    """``GET /api/lsat/validation`` — spec 041 FR-15 accuracy report.

    Deterministic (no model calls): per-question integrity issues, answer-key
    distribution, and a roll-up of stored cross-check verdicts.
    """

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        section = request.query_params.get("section")
        if section is not None and section not in ("LR", "RC", "LG"):
            return Response(
                {"detail": {"section": "must be LR, RC, or LG"}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(validate_question_set(section))


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


class _GenerateGuideRequest(BaseModel):
    question_id: str


class GuideGenerateView(_Base):
    """``POST /api/lsat/guides/generate`` — draft one solve guide (spec 041 FR-9).

    Single-question by design (spec 041 resolved OQ-2). The draft lands in
    the HITL proposal queue as ``proposal_kind="guide"``; it never serves on
    the guide endpoint until a reviewer approves it.
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "llm"

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        try:
            req = _GenerateGuideRequest.model_validate(request.data)
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        if req.question_id not in load_bank():
            raise Http404("question not found")
        if req.question_id in load_guides():
            return Response(
                {"detail": "question already has a solve guide"},
                status=status.HTTP_409_CONFLICT,
            )
        from law_ai.agents_runtime.crews.lsat_solve_guide_author import (
            LSATSolveGuideAuthor,
        )

        agent = LSATSolveGuideAuthor()
        try:
            output = async_to_sync(agent.run)({"question_id": req.question_id})
        except Exception as exc:
            logger.exception("LSATSolveGuideAuthor.run failed: %s", exc)
            return Response(
                {"detail": f"guide generation failed: {type(exc).__name__}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        pid = proposals_store.record_proposal(
            output.guide.model_dump(by_alias=True),
            agent_trace_id=output.trace_id or "",
            model=output.model,
            confidence=output.confidence,
            proposal_kind="guide",
        )
        return Response(
            {
                "proposal": proposals_store.get_proposal(pid),
                "trace_id": output.trace_id,
                "model": output.model,
                "degraded": output.degraded,
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
        existing = proposals_store.get_proposal(proposal_id)
        if existing is None:
            raise Http404("proposal not found")
        # Spec 041 FR-9: guide drafts promote into guides.json, not the banks.
        promote = (
            proposals_store.promote_guide_to_bank
            if existing.get("proposal_kind") == "guide"
            else proposals_store.promote_to_bank
        )
        try:
            row = promote(
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
    path(
        "questions/<str:question_id>/guide",
        GuideView.as_view(),
        name="lsat-question-guide",
    ),
    path(
        "questions/<str:question_id>/cross-check",
        CrossCheckView.as_view(),
        name="lsat-question-cross-check",
    ),
    path("validation", ValidationView.as_view(), name="lsat-validation"),
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
        "guides/generate",
        GuideGenerateView.as_view(),
        name="lsat-guides-generate",
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
