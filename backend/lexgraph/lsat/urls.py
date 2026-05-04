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
from rest_framework.views import APIView

from lexgraph.core import audit_jsonl as audit_store
from lexgraph.core.auth import RequireLsat
from lexgraph.lsat.services.bank import (
    ChoiceLabel,
    Difficulty,  # noqa: F401  re-exported for tests
    Section,
    load_bank,
    load_concepts,
    load_passages,
    load_sections,
    public_view,
)
from lexgraph.lsat.services.tutor import TutorRequest, TutorResponse, tutor

logger = logging.getLogger("lexgraph.lsat")


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
    def get(self, request, *args, **kwargs):  # noqa: ANN001
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
    def get(self, request, code: str, *args, **kwargs):  # noqa: ANN001
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
    def get(self, request, *args, **kwargs):  # noqa: ANN001
        section = request.query_params.get("section")
        items = list(load_concepts().values())
        if section:
            items = [c for c in items if section in c.sections]
        return Response(
            {"concepts": [c.model_dump() for c in items], "count": len(items)}
        )


class ConceptDetailView(_Base):
    def get(self, request, concept_id: str, *args, **kwargs):  # noqa: ANN001
        concept = load_concepts().get(concept_id)
        if concept is None:
            raise Http404("concept not found")
        bank = load_bank()
        used_in = [q.id for q in bank.values() if concept_id in q.concepts][:10]
        return Response(
            {"concept": concept.model_dump(), "used_in_questions": used_in}
        )


class PassagesView(_Base):
    def get(self, request, *args, **kwargs):  # noqa: ANN001
        section = request.query_params.get("section")
        items = list(load_passages().values())
        if section:
            items = [p for p in items if p.section == section]
        return Response(
            {"passages": [p.model_dump() for p in items], "count": len(items)}
        )


class PassageDetailView(_Base):
    def get(self, request, passage_id: str, *args, **kwargs):  # noqa: ANN001
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
    def get(self, request, *args, **kwargs):  # noqa: ANN001
        limit = _bounded_int(
            request.query_params.get("limit"), default=5, lo=1, hi=25
        )
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
    def get(self, request, question_id: str, *args, **kwargs):  # noqa: ANN001
        bank = load_bank()
        q = bank.get(question_id)
        if q is None:
            raise Http404("question not found")
        return Response(public_view(q).model_dump())


class GradeView(_Base):
    def post(self, request, *args, **kwargs):  # noqa: ANN001
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
    def get(self, request, *args, **kwargs):  # noqa: ANN001
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
    def post(self, request, *args, **kwargs):  # noqa: ANN001
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


urlpatterns = [
    path("sections", SectionsView.as_view(), name="lsat-sections"),
    path("sections/<str:code>", SectionDetailView.as_view(), name="lsat-section-detail"),
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
]
