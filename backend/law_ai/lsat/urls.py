"""LSAT Lab API (spec 005 → spec 011 FR-9 port)."""

from __future__ import annotations

import logging
import random
from typing import Any

from asgiref.sync import async_to_sync
from django.conf import settings
from django.http import Http404
from django.urls import path
from pydantic import BaseModel, Field, ValidationError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from law_ai.core import audit_jsonl as audit_store
from law_ai.core.throttling import ScopedActorRateThrottle
from law_ai.core.auth import RequireLsat
from law_ai.core.auth import is_signed_in
from law_ai.core.reviewer import attributed, reviewer_from_request
from law_ai.lsat.services.bank import (
    DIFFICULTY_ORDER,
    ChoiceLabel,
    Difficulty,
    Section,
    load_bank,
    load_concepts,
    load_passages,
    load_sections,
    public_view,
)
from law_ai.lsat.services import attempts as attempts_store
from law_ai.lsat.services import proposals as proposals_store
from law_ai.lsat.services import writing as writing_store
from law_ai.lsat.services.crosscheck import CrossCheckResult, cross_check
from law_ai.lsat.services.guides import load_guides, public_guide_view
from law_ai.lsat.services.shuffle import (
    ShuffleError,
    display_mapping,
    order_from_token,
    permute,
    remap_labels,
    to_canonical,
    to_display,
)
from law_ai.lsat.services.ocr_intake import IngestScanRequest, ingest_scan
from law_ai.lsat.services.library import (
    articles_teaching,
    inbound_links,
    library_audit,
    load_library,
    load_tracks,
    public_article_view,
    public_track_view,
    search_library,
)
from law_ai.lsat.services.tutor import TutorRequest, TutorResponse, tutor
from law_ai.lsat.services.validation import validate_question_set

logger = logging.getLogger("law_ai.lsat")


class GradeRequest(BaseModel):
    question_id: str
    choice: ChoiceLabel
    # Spec 045 FR-5: how many solve-guide steps the client revealed before
    # answering. None = client predates the hint system.
    hints_used: int | None = Field(default=None, ge=0, le=20)
    # BL-20260606-01: the signed permutation the question was served under.
    # Absent means the client saw the stored order, which is still a valid way
    # to take a question — the shuffle is opt-in per serve.
    remap: str | None = Field(default=None, max_length=64)


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
        # Spec 047 FR-5: WS holds writing prompts, not keyed questions. Report
        # them in their own field rather than overloading question_count, so a
        # client can tell an empty MCQ bank from a section that has no MCQ form.
        writing_counts = {"WS": len(writing_store.load_writing_prompts())}
        return Response(
            {
                "sections": [
                    {
                        **s.model_dump(),
                        "question_count": counts.get(s.code, 0),
                        "writing_prompt_count": writing_counts.get(s.code, 0),
                    }
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
        used_in = [q.id for q in bank.values() if concept_id in q.concepts]
        return Response(
            {
                "concept": concept.model_dump(),
                # Capped, because a popular concept's whole id list is not what
                # a reader came for — but the *count* is, so it ships beside
                # the sample the way the article endpoint pairs
                # `drill_question_ids` with `drill_question_count`. Without it
                # a concept entry could only ever say "10+ questions" while an
                # article beside it named the exact number (BL-20260905-06).
                "used_in_questions": used_in[:10],
                "used_in_count": len(used_in),
                # Spec 048 FR-7: the inverse of Article.concepts. A learner who
                # misses a concept-tagged question needs a route from the tag to
                # the material, not only from the material to the tag.
                "taught_in": articles_teaching(concept_id),
            }
        )


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
        # BL-20260606-01: RC and LG are served from here, and they are the
        # majority of the bank — without ``?shuffle=1`` their keys sat in the
        # same position on every attempt while LR's moved. Same contract as
        # ``QuestionsView``: a ``remap`` token per question, echoed back at
        # grade time.
        shuffle = _wants_shuffle(request)
        questions = [
            _served(q, shuffle=shuffle)
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


def _served(question: Any, *, shuffle: bool) -> dict[str, Any]:
    """One question as the client receives it, shuffled when asked.

    The payload is an ordinary question — choices labelled A-E top to bottom —
    plus a ``remap`` token when the order is not the stored one. A client that
    ignores the token simply gets a question it can render; one that echoes it
    back at grade time gets its answer read in the order it actually saw.
    """
    if not shuffle:
        return public_view(question).model_dump(exclude={"remap"})
    shown, token, _order = permute(question.choices, question.id)
    served = public_view(question).model_copy(update={"choices": shown, "remap": token})
    return served.model_dump()


def _wants_shuffle(request: Any) -> bool:
    return request.query_params.get("shuffle") in ("1", "true", "yes")


class QuestionsView(_Base):
    def get(self, request, *args, **kwargs):
        limit = _bounded_int(request.query_params.get("limit"), default=5, lo=1, hi=25)
        difficulty = request.query_params.get("difficulty")
        section = request.query_params.get("section")
        passage_id = request.query_params.get("passage_id")
        # BL-20260905-01: the library's concept catalog says "drill them in the
        # lab", and the lab could only open on Overview and leave the learner to
        # re-find the section and re-filter by hand. Questions have carried
        # ``concepts`` since the bank shipped; this is the filter that lets a
        # tag link straight through to practice.
        concept = request.query_params.get("concept")
        bank = load_bank()
        pool = [
            q
            for q in bank.values()
            if (difficulty is None or q.difficulty == difficulty)
            and (section is None or q.section == section)
            and (passage_id is None or q.passage_id == passage_id)
            and (concept is None or concept in q.concepts)
        ]
        if not pool:
            return Response({"questions": [], "count": 0})
        if passage_id:
            sample = sorted(pool, key=lambda q: q.id)[:limit]
        else:
            sample = random.sample(pool, min(limit, len(pool)))
        shuffle = _wants_shuffle(request)
        return Response(
            {
                "questions": [_served(q, shuffle=shuffle) for q in sample],
                "count": len(sample),
            }
        )


class QuestionDetailView(_Base):
    def get(self, request, question_id: str, *args, **kwargs):
        bank = load_bank()
        q = bank.get(question_id)
        if q is None:
            raise Http404("question not found")
        return Response(_served(q, shuffle=_wants_shuffle(request)))


def _remap_guide(body: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """A guide payload with every label reference moved to its display letter."""
    out = dict(body)
    steps = out.get("steps")
    if isinstance(steps, list):
        out["steps"] = [
            (
                {
                    key: (
                        remap_labels(value, mapping)
                        if isinstance(value, str)
                        else value
                    )
                    for key, value in step.items()
                }
                if isinstance(step, dict)
                else step
            )
            for step in steps
        ]
    return out


class GuideView(_Base):
    """``GET /api/lsat/questions/<id>/guide`` — progressive solve guide.

    Spec 045 FR-4. Spoiler-step content is withheld unless ``?spoilers=1``
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
        # A guide that says "eliminate (B)" beside a shuffled board would
        # contradict the screen, so the same remap the grade path applies to
        # the explanation applies here (BL-20260606-01).
        token = request.query_params.get("remap")
        if token:
            try:
                mapping = display_mapping(order_from_token(q.id, token))
            except ShuffleError as exc:
                return Response(
                    {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
                )
            body = _remap_guide(body, mapping)
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
        # BL-20260606-01: when the question was served shuffled, the label the
        # learner picked is a *display* label. Read it back through the signed
        # order before comparing, and put the key back where they saw it.
        answered: ChoiceLabel = req.choice
        correct_choice: ChoiceLabel = q.correct
        explanation = q.explanation
        if req.remap:
            try:
                order = order_from_token(q.id, req.remap)
            except ShuffleError as exc:
                return Response(
                    {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
                )
            answered = to_canonical(req.choice, order)
            correct_choice = to_display(q.correct, order)
            explanation = remap_labels(q.explanation, display_mapping(order))
        is_correct = answered == q.correct
        body = GradeResponse(
            question_id=q.id,
            correct=is_correct,
            correct_choice=correct_choice,
            explanation=explanation,
            section=q.section,
            concepts=list(q.concepts),
        )
        try:
            audit_store.record(
                {
                    "type": "lsat_grade",
                    "question_id": q.id,
                    "section": q.section,
                    # The stored label, so answer-distribution analysis is not
                    # a measure of the shuffle.
                    "choice": answered,
                    "shuffled": bool(req.remap),
                    "correct": is_correct,
                    "difficulty": q.difficulty,
                    "concepts": list(q.concepts),
                    "hints_used": req.hints_used,
                }
            )
        except Exception:
            logger.warning("audit_store.record failed for lsat_grade", exc_info=True)
        # BL-20260503-05: a signed-in learner also gets a durable, attributed
        # attempt row so /api/lsat/stats can answer "how am *I* doing" and
        # schedule a review. Anonymous grading is byte-identical to before.
        if is_signed_in(request):
            attempts_store.record_attempt(
                request.user,
                question_id=q.id,
                section=q.section,
                difficulty=q.difficulty,
                choice=answered,
                correct=is_correct,
                hints_used=req.hints_used or 0,
                shuffled=bool(req.remap),
                concepts=list(q.concepts),
            )
        return Response(body.model_dump())


def _fold_reading(
    request: Any, body: dict[str, Any], section: str | None
) -> dict[str, Any]:
    """Add library reading progress to a stats payload (BL-20260903-05).

    Reading is practice too, and it lived only in each browser's
    ``localStorage`` — so "articles read" was invisible next to drill accuracy,
    the one half of the library's own loop no surface could report. Folded into
    *both* readings of stats (the signed-in learner's and the instance-wide
    audit tail) so the response shape stays the same either way.
    """
    out = dict(body)
    library = load_library()
    by_section: dict[str, dict[str, Any]] = dict(out.get("by_section") or {})
    articles_read = 0
    for article_id in _read_article_ids(_reader_id(request)):
        article = library.get(article_id)
        if article is None:
            # A read event for an article that has since been retired: it
            # happened, but it can no longer be attributed to a section.
            continue
        secs = [str(sec) for sec in article.sections]
        if section and section not in secs:
            continue
        articles_read += 1
        for sec in secs:
            bucket = dict(
                by_section.get(sec)
                or {
                    "attempts": 0,
                    "correct": 0,
                    "assisted": 0,
                    "unassisted": 0,
                    "accuracy": 0.0,
                }
            )
            bucket["articles_read"] = int(bucket.get("articles_read", 0)) + 1
            by_section[sec] = bucket
    for sec, bucket in by_section.items():
        bucket.setdefault("articles_read", 0)
        by_section[sec] = bucket
    out["by_section"] = by_section
    # Cross-cutting articles carry no section, so this is not the sum of the
    # per-section counts and was never meant to be.
    out["articles_read"] = articles_read
    out["articles_total"] = len(library)
    return out


def _fold_writing(body: dict[str, Any], section: str | None) -> dict[str, Any]:
    """Add Argumentative Writing practice to a stats payload (BL-20260831-27).

    ``LSATWritingEvaluator`` has always *persisted* — every evaluation is an
    ``lsat_writing_evaluate`` event in the same append-only store ``lsat_grade``
    uses. What was missing is that nothing read them back, so a learner could
    not see writing progress across attempts the way the MCQ stats surface
    shows drill accuracy.

    Bands are a study instrument, not a score: the LSAT writing section is
    unscored, and every band here was produced by a model, so ``model`` and
    ``prompt_version`` ride along to be shown at the point of display
    (NFR-PROV-1).
    """
    if section and section != "WS":
        # Asking for one keyed section is asking about keyed questions.
        return body
    events = [
        e for e in audit_store.tail(10_000) if e.get("type") == "lsat_writing_evaluate"
    ]
    out = dict(body)
    # `tail` is newest-first; the trend reads forward in time.
    ordered = list(reversed(events))
    bands = [
        float(e["weighted_band"])
        for e in ordered
        if isinstance(e.get("weighted_band"), (int, float))
    ]
    by_prompt: dict[str, int] = {}
    for e in ordered:
        pid = e.get("prompt_id")
        if isinstance(pid, str):
            by_prompt[pid] = by_prompt.get(pid, 0) + 1
    latest = ordered[-1] if ordered else {}
    out["writing"] = {
        "attempts": len(ordered),
        "by_prompt": by_prompt,
        "latest_band": bands[-1] if bands else None,
        "best_band": max(bands) if bands else None,
        "band_trend": [round(b, 4) for b in bands],
        "degraded": sum(1 for e in ordered if e.get("degraded") is True),
        # Named so the UI can mark these bands as machine-derived rather than
        # letting them read like a graded score.
        "model": latest.get("model"),
        "prompt_version": latest.get("prompt_version"),
    }
    return out


def _fold_hints(body: dict[str, Any], section: str | None) -> dict[str, Any]:
    """Add per-reveal hint depth to a stats payload (BL-20260830-13).

    ``hints_used`` on a grade can only ever say "assisted": a one-hint nudge
    and a five-hint walkthrough read the same, and hints taken on a question
    that was never submitted are not in it at all. ``lsat_hint`` events are,
    so the deepest reveal per question is recoverable — which is the number
    that distinguishes a nudge from a walkthrough.
    """
    out = dict(body)
    events = [e for e in audit_store.tail(10_000) if e.get("type") == "lsat_hint"]
    if section:
        events = [e for e in events if e.get("section") == section]
    depth_by_question: dict[str, int] = {}
    for e in events:
        qid = e.get("question_id")
        depth = e.get("revealed_count")
        if not isinstance(qid, str) or not isinstance(depth, int):
            continue
        depth_by_question[qid] = max(depth_by_question.get(qid, 0), depth)
    depths = sorted(depth_by_question.values())
    out["hints"] = {
        "reveals": len(events),
        "questions_hinted": len(depth_by_question),
        "max_depth": depths[-1] if depths else 0,
        # The mean is the honest summary of "how much help" — the median of a
        # handful of questions is almost always 1 and says nothing.
        "mean_depth": round(sum(depths) / len(depths), 2) if depths else 0.0,
        "spoiler_reveals": sum(1 for e in events if e.get("spoiler") is True),
    }
    return out


def _fold_extras(
    request: Any, body: dict[str, Any], section: str | None
) -> dict[str, Any]:
    """Everything practice is, beyond a keyed question.

    Applied to *both* readings of stats — the signed-in learner's and the
    instance-wide audit tail — so the response shape is the same either way.
    """
    folded = _fold_reading(request, body, section)
    folded = _fold_hints(folded, section)
    return _fold_writing(folded, section)


class StatsView(_Base):
    """``GET /api/lsat/stats`` — how practice is going.

    Two readings of the same question. A signed-in learner gets **their**
    history out of :class:`~law_ai.lsat.models.LsatAttempt`, with an accuracy
    trend and a spaced-repetition queue (BL-20260503-05). Everyone else gets
    the original instance-wide audit-log totals; the response shape is the
    same either way, with ``scope`` naming which reading answered and
    ``review_queue`` empty when there is no learner to schedule for.
    """

    def get(self, request, *args, **kwargs):
        section = request.query_params.get("section")
        if is_signed_in(request):
            return Response(
                _fold_extras(
                    request,
                    attempts_store.user_stats(request.user, section=section),
                    section,
                )
            )
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
            _fold_extras(
                request,
                {
                    "attempts": attempts,
                    "correct": correct,
                    "accuracy": round(accuracy, 4),
                    "assisted": assisted,
                    "unassisted": attempts - assisted,
                    "by_section": by_section,
                    # Stable shape: the anonymous reading has no learner, so no
                    # trend and nothing to schedule.
                    "accuracy_over_time": [],
                    "review_queue": [],
                    "scope": "instance",
                },
                section,
            )
        )


class TutorView(_Base):
    # BL-20260810-11: the only LSAT endpoint that invokes an LLM.
    throttle_classes = [ScopedActorRateThrottle]
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


class _HintRevealRequest(BaseModel):
    """One reveal, as the client reports it."""

    #: Zero-based index of the step just exposed.
    step_index: int = Field(ge=0, le=50)
    #: How many steps are revealed after this one — the running depth.
    revealed_count: int = Field(ge=1, le=51)
    #: True when the reveal unlocked spoiler content (post-grade only).
    spoiler: bool = False


class HintRevealView(_Base):
    """``POST /api/lsat/questions/<id>/hint`` — one revealed step (FR-6).

    Only grade-time ``hints_used`` was recorded (BL-20260830-13), which can say
    "assisted" and nothing else: a one-hint nudge and a five-hint walkthrough
    look identical, and hints taken on a question the learner never submitted
    leave no trace at all. Each reveal is its own event, written through the
    same audit store as ``lsat_grade`` and ``lsat_guide``.

    Unauthenticated like grade and guide, so the static-parity story holds. The
    client calls it fire-and-forget: a hint must never wait on this.
    """

    def post(
        self, request: Any, question_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        q = load_bank().get(question_id)
        guide = load_guides().get(question_id)
        if q is None or guide is None:
            # Same shape the guide endpoint 404s with, for the same reason:
            # there is nothing to reveal, and the caller already knows why.
            return Response(
                {
                    "detail": "no solve guide for this question",
                    "has_tutor": q is not None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            req = _HintRevealRequest.model_validate(request.data or {})
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        if req.step_index >= len(guide.steps):
            return Response(
                {"detail": {"step_index": "beyond the end of this guide"}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        step = guide.steps[req.step_index]
        try:
            audit_store.record(
                {
                    "type": "lsat_hint",
                    "question_id": q.id,
                    "section": str(q.section),
                    "step_index": req.step_index,
                    "step_kind": str(step.kind),
                    "revealed_count": req.revealed_count,
                    "spoiler": req.spoiler,
                    "step_count": len(guide.steps),
                }
            )
        except Exception:
            logger.warning("audit_store.record failed for lsat_hint", exc_info=True)
        return Response({"recorded": True}, status=status.HTTP_202_ACCEPTED)


class CrossCheckView(_Base):
    """``POST /api/lsat/questions/<id>/cross-check`` — spec 045 FR-14.

    Solves the question blind through the provider chain and compares the
    pick against the answer key. Verdicts are cached; ``refresh`` re-solves.
    """

    throttle_classes = [ScopedActorRateThrottle]
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


# ---------------------------------------------------------------------------
# Knowledge library (spec 048 FR-12)
# ---------------------------------------------------------------------------


class LibraryIndexView(_Base):
    """``GET /api/lsat/library`` — the contents rail.

    Returns index rows only. Article bodies are 700 words apiece; shipping
    35 of them to render a list of 35 titles is the difference between a
    fast rail and a 900 KB one (NFR-PERF-1).
    """

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        articles = list(load_library().values())
        params = request.query_params
        if kind := params.get("kind"):
            articles = [a for a in articles if a.kind == kind]
        if level := params.get("level"):
            articles = [a for a in articles if a.level == level]
        if section := params.get("section"):
            articles = [a for a in articles if section in a.sections]
        if tag := params.get("tag"):
            articles = [a for a in articles if tag in a.tags]
        if concept := params.get("concept"):
            teaching = set(articles_teaching(concept))
            articles = [a for a in articles if a.id in teaching]
        if track_id := params.get("track"):
            track = load_tracks().get(track_id)
            if track is None:
                raise Http404("track not found")
            # Track order is the curriculum, so preserve it rather than
            # re-sorting alphabetically like every other filter.
            order = {a: i for i, a in enumerate(track.article_ids)}
            articles = [a for a in articles if a.id in order]
            articles.sort(key=lambda a: order[a.id])
        else:
            articles.sort(key=lambda a: a.id)
        return Response(
            {
                "articles": [
                    public_article_view(a).model_dump(mode="json") for a in articles
                ],
                "count": len(articles),
            }
        )


class LibraryArticleView(_Base):
    """``GET /api/lsat/library/<id>`` — one article with its cross-references resolved."""

    def get(self, request: Any, article_id: str, *args: Any, **kwargs: Any) -> Response:
        articles = load_library()
        article = articles.get(article_id)
        if article is None:
            raise Http404("article not found")
        concepts = load_concepts()
        bank = load_bank()
        related_ids = sorted(set(article.related) | set(inbound_links(article.id)))
        drills = sorted(
            q.id
            for q in bank.values()
            if any(c in article.concepts for c in q.concepts)
        )
        return Response(
            {
                "article": article.model_dump(mode="json"),
                "concepts": [
                    concepts[c].model_dump(mode="json")
                    for c in article.concepts
                    if c in concepts
                ],
                "prerequisites": [
                    public_article_view(articles[p]).model_dump(mode="json")
                    for p in article.prerequisites
                    if p in articles
                ],
                "related": [
                    public_article_view(articles[r]).model_dump(mode="json")
                    for r in related_ids
                    if r in articles
                ],
                "tracks": [
                    {"id": t.id, "name": t.name}
                    for t in load_tracks().values()
                    if article.id in t.article_ids
                ],
                "drill_question_ids": drills[:25],
                "drill_question_count": len(drills),
            }
        )


def _reader_id(request: Any) -> str:
    """Who this reading progress belongs to.

    A signed-in account is the identity when there is one (spec 036 FR-2).
    Otherwise the whole deployment is one reader — which is what every other
    number on ``/api/lsat/stats`` already assumes, because the audit tail it
    reads has never been per-user. "Cross-device" therefore means "cross-device
    for this deployment" until LSAT surfaces get real per-user scoping, and
    saying so here is better than implying more (BL-20260903-05).
    """
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return f"user:{user.pk}"
    return "instance"


def _read_article_ids(reader: str) -> list[str]:
    """Article ids this reader has marked read, newest event wins.

    Read *and* unread are recorded as events — the store is append-only, so
    unmarking is a later event rather than a deletion, and the current state is
    the last thing said about each article.
    """
    state: dict[str, bool] = {}
    # `tail` is newest-first, so the first mention of an article is the latest.
    for e in audit_store.tail(10_000):
        if e.get("type") != "lsat_article_read":
            continue
        if e.get("reader") != reader:
            continue
        article_id = e.get("article_id")
        if isinstance(article_id, str) and article_id not in state:
            state[article_id] = bool(e.get("read", True))
    return sorted(a for a, read in state.items() if read)


class LibraryReadView(_Base):
    """``GET|POST /api/lsat/library/read`` — which articles have been read.

    Reading progress was per-browser ``localStorage`` on both products, so a
    learner who read half the library on a laptop started again on a phone, and
    "articles read" was invisible next to drill accuracy (BL-20260903-05).

    Recorded through the same append-only audit store that carries
    ``lsat_grade``, for the same reason: it is provenance, not user data with a
    lifecycle. ``localStorage`` stays the offline fallback on the client, and
    ``lsat-static`` keeps it as its only store — a serverless bundle has nothing
    to sync with.
    """

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        ids = _read_article_ids(_reader_id(request))
        return Response({"read": ids, "count": len(ids)})

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        data = request.data or {}
        article_id = data.get("article_id")
        if not isinstance(article_id, str) or not article_id:
            return Response(
                {"detail": {"article_id": "required"}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        article = load_library().get(article_id)
        if article is None:
            raise Http404("article not found")
        read = data.get("read", True)
        if not isinstance(read, bool):
            return Response(
                {"detail": {"read": "must be a boolean"}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        try:
            audit_store.record(
                {
                    "type": "lsat_article_read",
                    "article_id": article.id,
                    "sections": [str(sec) for sec in article.sections],
                    "kind": str(article.kind),
                    "read": read,
                    "reader": _reader_id(request),
                }
            )
        except Exception:
            logger.warning(
                "audit_store.record failed for lsat_article_read", exc_info=True
            )
        ids = _read_article_ids(_reader_id(request))
        return Response({"read": ids, "count": len(ids)})


class LibraryTracksView(_Base):
    """``GET /api/lsat/library/tracks`` — curated reading paths."""

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        tracks = [public_track_view(t) for t in load_tracks().values()]
        return Response({"tracks": tracks, "count": len(tracks)})


class LibrarySearchView(_Base):
    """``GET /api/lsat/library/search?q=`` — ranked hits with snippets."""

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        query = (request.query_params.get("q") or "").strip()
        if len(query) < 2 or len(query) > 100:
            return Response(
                {"detail": {"q": "must be between 2 and 100 characters"}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        limit = _bounded_int(request.query_params.get("limit"), default=20, lo=1, hi=50)
        results = search_library(query, limit=limit)
        return Response({"query": query, "results": results, "count": len(results)})


class LibraryHealthView(_Base):
    """``GET /api/lsat/library/health`` — the deterministic audit (FR-14).

    No model call. This is the number behind the claim that the library is
    being maintained, so it must not depend on the thing it measures.
    """

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        return Response(library_audit())


class ValidationView(_Base):
    """``GET /api/lsat/validation`` — spec 045 FR-15 accuracy report.

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
# Argumentative Writing (spec 047 FR-5)
# ---------------------------------------------------------------------------


class WritingPromptsView(_Base):
    """``GET /api/lsat/writing/prompts`` — the prompt library, model-free.

    Every payload goes through ``public_prompt_view``: reading the annotated
    model response before drafting destroys the exercise, so it is withheld
    here the same way ``public_view`` withholds an answer key.
    """

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        difficulty = request.query_params.get("difficulty")
        if difficulty is not None and difficulty not in DIFFICULTY_ORDER:
            return Response(
                {
                    "detail": {
                        "difficulty": f"must be one of {', '.join(DIFFICULTY_ORDER)}"
                    }
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        prompts = [
            writing_store.public_prompt_view(p).model_dump()
            for p in sorted(
                writing_store.load_writing_prompts().values(), key=lambda p: p.id
            )
            if difficulty is None or p.difficulty == difficulty
        ]
        return Response({"prompts": prompts, "count": len(prompts)})


class WritingPromptDetailView(_Base):
    """``GET /api/lsat/writing/prompts/<id>`` — one prompt plus its rubric.

    ``?model_response=1`` adds the annotated worked example. The client asks
    for it only after the learner has drafted — the same soft protection level
    the solve-guide endpoint applies to spoiler steps.
    """

    def get(self, request: Any, prompt_id: str, *args: Any, **kwargs: Any) -> Response:
        prompt = writing_store.load_writing_prompts().get(prompt_id)
        if prompt is None:
            raise Http404("writing prompt not found")
        rubric = writing_store.rubric_for(prompt)
        include_model = request.query_params.get("model_response") in ("1", "true")
        body: dict[str, Any] = {
            "prompt": writing_store.public_prompt_view(prompt).model_dump(),
            "rubric": rubric.model_dump(),
        }
        if include_model:
            body["model_response"] = prompt.model_response.model_dump()
        return Response(body)


class WritingRubricView(_Base):
    """``GET /api/lsat/writing/rubric`` — the rubric, for offline self-scoring."""

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        rubric_id = request.query_params.get("id")
        if rubric_id:
            rubric = writing_store.load_writing_rubrics().get(rubric_id)
        else:
            rubric = writing_store.default_rubric()
        if rubric is None:
            raise Http404("rubric not found")
        return Response({"rubric": rubric.model_dump()})


class WritingEvaluateView(_Base):
    """``POST /api/lsat/writing/evaluate`` — rubric-scored feedback (FR-4).

    Formative feedback for one learner; nothing here is promoted into the
    bank. The response carries ``model`` and ``prompt_version`` so the UI can
    label machine-derived bands at the point of display (NFR-PROV-1).
    """

    throttle_classes = [ScopedActorRateThrottle]
    throttle_scope = "llm"

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        from law_ai.agents_runtime.crews.lsat_writing_evaluator import (
            EvaluateWritingInput,
            LSATWritingEvaluator,
        )

        try:
            req = EvaluateWritingInput.model_validate(request.data or {})
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        if req.prompt_id not in writing_store.load_writing_prompts():
            raise Http404("writing prompt not found")

        agent = LSATWritingEvaluator()
        try:
            output = async_to_sync(agent.run)(req.model_dump())
        except Exception as exc:
            logger.exception("LSATWritingEvaluator.run failed: %s", exc)
            return Response(
                {"detail": f"evaluation failed: {type(exc).__name__}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            audit_store.record(
                {
                    "type": "lsat_writing_evaluate",
                    "prompt_id": req.prompt_id,
                    "section": "WS",
                    "response_chars": len(req.response),
                    "weighted_band": output.evaluation.weighted_band,
                    "model": output.model,
                    "degraded": output.degraded,
                    # Provenance the stats fold labels bands with, and the
                    # criterion detail that makes criterion-level progress
                    # possible later without a second schema change
                    # (BL-20260831-27).
                    "prompt_version": output.prompt_version,
                    "rubric_id": output.evaluation.rubric_id,
                    "criteria": {
                        c.criterion_id: c.band for c in output.evaluation.criteria
                    },
                }
            )
        except Exception:
            logger.warning(
                "audit_store.record failed for lsat_writing_evaluate", exc_info=True
            )
        return Response(output.model_dump())


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
        # BL-20260606-02: an A-E skew in the batch is flagged onto every
        # proposal so the HITL queue shows it; the drafts are not rejected.
        base_meta: dict[str, Any] = (
            {"balance_flag": output.balance_flag} if output.balance_flag else {}
        )
        # BL-20260527-04: blind pre-review rides along in the proposal meta so
        # the HITL queue can surface borderline drafts. Advisory only.
        from law_ai.agents_runtime.crews.lsat_content_reviewer import (
            review_drafts,
        )

        reviews = async_to_sync(review_drafts)([d.model_dump() for d in output.drafts])
        for draft, review in zip(output.drafts, reviews, strict=True):
            meta: dict[str, Any] = dict(base_meta)
            if review is not None:
                meta["review"] = review
            pid = proposals_store.record_proposal(
                draft.model_dump(),
                agent_trace_id=output.trace_id or "",
                model=output.model,
                confidence=output.confidence,
                source_concept_ids=req.concepts,
                meta=meta or None,
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
                "balance_flag": output.balance_flag,
                "count": len(persisted),
            }
        )


class _GenerateGuideRequest(BaseModel):
    question_id: str


class GuideGenerateView(_Base):
    """``POST /api/lsat/guides/generate`` — draft one solve guide (spec 045 FR-9).

    Single-question by design (spec 045 resolved OQ-2). The draft lands in
    the HITL proposal queue as ``proposal_kind="guide"``; it never serves on
    the guide endpoint until a reviewer approves it.
    """

    throttle_classes = [ScopedActorRateThrottle]
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

        # BL-20260830-15: the deterministic lint has already run inside the
        # author; the judge tier adds pedagogical soundness and rides along in
        # meta.review. Advisory — the draft is filed either way, and only a
        # human promotes it.
        from law_ai.agents_runtime.crews.lsat_guide_reviewer import review_guide

        review = async_to_sync(review_guide)(output.guide)
        pid = proposals_store.record_proposal(
            output.guide.model_dump(by_alias=True),
            agent_trace_id=output.trace_id or "",
            model=output.model,
            confidence=output.confidence,
            proposal_kind="guide",
            meta={"review": review} if review is not None else None,
        )
        return Response(
            {
                "proposal": proposals_store.get_proposal(pid),
                "trace_id": output.trace_id,
                "model": output.model,
                "degraded": output.degraded,
                "review": review,
            }
        )


class _StatusUpdateRequest(BaseModel):
    note: str | None = None
    reviewer: str | None = None


class _PassageApproveRequest(BaseModel):
    """Which parked passage to promote: its path, or the job that wrote it."""

    pending_passage_path: str | None = None
    job_id: str | None = None
    note: str | None = None
    reviewer: str | None = None


class ProposalPassageApproveView(_Base):
    """``POST /api/lsat/proposals/passages/approve`` — promote a parked passage.

    BL-20260702-07. A ``passage_set`` factory job invents its own context,
    which intake parks rather than writing to the live data. Promoting it
    appends the passage to ``passages.json`` and links every pending draft
    from that job to the new ``passage_id``, so approving those drafts then
    carries the linkage into the bank instead of leaving it to the reviewer.
    """

    def post(self, request, *args, **kwargs):
        try:
            req = _PassageApproveRequest.model_validate(request.data or {})
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        pending_path = req.pending_passage_path
        if not pending_path and req.job_id:
            pending_path = str(
                proposals_store.pending_passages_dir() / f"{req.job_id}.passage.json"
            )
        if not pending_path:
            return Response(
                {"detail": "pending_passage_path or job_id is required"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        identity = reviewer_from_request(request, claimed=req.reviewer)
        try:
            with attributed(identity):
                result = proposals_store.promote_passage(
                    pending_path,
                    reviewer=identity.name,
                    note=req.note,
                )
        except KeyError as exc:
            raise Http404("parked passage not found") from exc
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(result)


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
        # Spec 045 FR-9: guide drafts promote into guides.json, not the banks.
        # BL-20260831-21: a cross-check disagreement is a report — approving it
        # records "the key is right after all" and writes nothing to the bank.
        # BL-20260831-28: a writing draft writes to writing_prompts.json, so
        # the factory's writing loop ends at the same Approve button as the
        # MCQ loop instead of dead-ending in the queue with a 409.
        promoters = {
            "guide": proposals_store.promote_guide_to_bank,
            "crosscheck": proposals_store.promote_crosscheck,
            "writing_prompt": proposals_store.promote_writing_prompt,
        }
        promote = promoters.get(
            str(existing.get("proposal_kind") or ""),
            proposals_store.promote_to_bank,
        )
        identity = reviewer_from_request(request, claimed=req.reviewer)
        try:
            with attributed(identity):
                row = promote(
                    proposal_id,
                    reviewer=identity.name,
                    note=req.note,
                )
        except KeyError as exc:
            raise Http404("proposal not found") from exc
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        # BL-20260527-06: pin a fresh blind-solve verdict to the new bank item
        # so later cross-checks can be compared against it (regression.py).
        if row.get("proposal_kind", "question") == "question" and getattr(
            settings, "LSAT_CROSS_CHECK_ON_APPROVE", True
        ):
            verdict = proposals_store.cross_check_on_approval(proposal_id)
            if verdict is not None:
                row = {**row, "cross_check": verdict}
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
        identity = reviewer_from_request(request, claimed=req.reviewer)
        with attributed(identity):
            row = proposals_store.set_status(
                proposal_id,
                "rejected",
                reviewer=identity.name,
                note=req.note,
            )
        return Response(row)


class ScanIntakeView(_Base):
    """``POST /api/lsat/intake/ocr`` — a scanned page becomes pending proposals.

    The ingestion door for `ocrmd`, the camera-to-Markdown scanner: it reads a book
    page twice (local OCR + a vision model), reconciles the two readings, and posts
    the result here with the page's provenance attached. The text is transcribed
    into question drafts, gated exactly as factory-generated ones are, and parked in
    the HITL queue — this endpoint has no path to the live bank.

    Rate-limited on the ``llm`` scope: every call runs an extraction through the
    provider chain, and the caller is a button on a scanner UI.
    """

    throttle_classes = [ScopedActorRateThrottle]
    throttle_scope = "llm"

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        try:
            req = IngestScanRequest.model_validate(request.data)
        except ValidationError as exc:
            return Response(
                {"detail": exc.errors()}, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        try:
            result = ingest_scan(req)
        except Exception as exc:
            logger.exception("lsat ocr intake failed: %s", exc)
            return Response(
                {"detail": f"scan intake failed: {type(exc).__name__}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        try:
            audit_store.record(
                "lsat_intake_ocr",
                {
                    "tool": req.provenance.tool,
                    "document": req.provenance.document,
                    "page": req.provenance.page,
                    "page_id": req.provenance.page_id,
                    "hint": req.hint,
                    "accepted": len(result.accepted),
                    "rejected": len(result.rejected),
                    "ungrounded": len(result.ungrounded),
                    "model": result.model,
                    "degraded": result.degraded,
                },
            )
        except Exception:
            logger.warning(
                "audit_store.record failed for lsat_intake_ocr", exc_info=True
            )
        # 202: drafts were taken in and are waiting for a reviewer, not published.
        return Response(result.model_dump(), status=status.HTTP_202_ACCEPTED)


class FactoryStatusView(_Base):
    """``GET /api/lsat/factory/status`` — what the next batch will target.

    ``factory.status()`` has answered this for the CLI since spec 024
    (``manage.py lsat_factory status``), but nothing exposed it over HTTP, so
    the reviewer working the Authoring queue could see the proposals in front
    of them and not the coverage holes that produced them (BL-20260702-06).

    Read-only, and deliberately not cheap: it loads the whole bank and lists up
    to 500 proposals. A reviewer surface, not something to poll on a timer.
    """

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        from law_ai.lsat import factory

        body: dict[str, Any] = dict(factory.status())
        # The manifest itself, summarised: "the last batch was 12 jobs across
        # these tiers" is the fact a reviewer wants, and the path alone is not
        # it. Never fatal — a status page must not 500 because a manifest on
        # disk is from an older schema.
        body["latest_manifest_summary"] = None
        if body.get("latest_manifest"):
            try:
                manifest = factory.load_manifest()
            except Exception:
                logger.warning("factory.load_manifest failed", exc_info=True)
            else:
                tiers: dict[str, int] = {}
                archetypes: dict[str, int] = {}
                for job in manifest.jobs:
                    tiers[str(job.tier)] = tiers.get(str(job.tier), 0) + 1
                    aid = str(job.target.archetype_id)
                    archetypes[aid] = archetypes.get(aid, 0) + 1
                body["latest_manifest_summary"] = {
                    "manifest_id": manifest.manifest_id,
                    "created_at": manifest.created_at,
                    "jobs": len(manifest.jobs),
                    "by_tier": tiers,
                    "by_archetype": archetypes,
                }

        # Gate stats: what the pending factory drafts came through. Read off
        # the proposals' own `meta.factory`, so this reports what is actually
        # in the queue rather than what a run once logged.
        by_executor: dict[str, int] = {}
        by_tier: dict[str, int] = {}
        flagged = 0
        for row in proposals_store.list_proposals(status="pending", limit=500):
            meta = row.get("meta")
            if not isinstance(meta, dict):
                continue
            fac = meta.get("factory")
            if not isinstance(fac, dict):
                continue
            ex = str(fac.get("executor") or "unknown")
            by_executor[ex] = by_executor.get(ex, 0) + 1
            tier = str(fac.get("tier") or "unknown")
            by_tier[tier] = by_tier.get(tier, 0) + 1
            if fac.get("balance_flag"):
                flagged += 1
        body["pending_gates"] = {
            "by_executor": by_executor,
            "by_tier": by_tier,
            "answer_balance_flagged": flagged,
        }
        return Response(body)


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
        "questions/<str:question_id>/hint",
        HintRevealView.as_view(),
        name="lsat-question-hint",
    ),
    path(
        "questions/<str:question_id>/cross-check",
        CrossCheckView.as_view(),
        name="lsat-question-cross-check",
    ),
    path("validation", ValidationView.as_view(), name="lsat-validation"),
    # Knowledge library (spec 048). Static segments precede the catch-all id
    # route so /library/tracks is never read as an article called "tracks".
    path("library", LibraryIndexView.as_view(), name="lsat-library"),
    path("library/read", LibraryReadView.as_view(), name="lsat-library-read"),
    path("library/tracks", LibraryTracksView.as_view(), name="lsat-library-tracks"),
    path("library/search", LibrarySearchView.as_view(), name="lsat-library-search"),
    path("library/health", LibraryHealthView.as_view(), name="lsat-library-health"),
    path(
        "library/<str:article_id>",
        LibraryArticleView.as_view(),
        name="lsat-library-article",
    ),
    path("writing/prompts", WritingPromptsView.as_view(), name="lsat-writing-prompts"),
    path(
        "writing/prompts/<str:prompt_id>",
        WritingPromptDetailView.as_view(),
        name="lsat-writing-prompt-detail",
    ),
    path("writing/rubric", WritingRubricView.as_view(), name="lsat-writing-rubric"),
    path(
        "writing/evaluate",
        WritingEvaluateView.as_view(),
        name="lsat-writing-evaluate",
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
        "guides/generate",
        GuideGenerateView.as_view(),
        name="lsat-guides-generate",
    ),
    # BL-20260702-07: static segment before the <proposal_id> catch-all, or
    # "passages" would be read as a proposal id.
    path(
        "proposals/passages/approve",
        ProposalPassageApproveView.as_view(),
        name="lsat-proposals-passage-approve",
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
    # Scanned-page intake (ocrmd → HITL queue)
    path("intake/ocr", ScanIntakeView.as_view(), name="lsat-intake-ocr"),
    path(
        "factory/status",
        FactoryStatusView.as_view(),
        name="lsat-factory-status",
    ),
    path("gaps", GapsView.as_view(), name="lsat-gaps"),
]
