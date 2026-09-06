"""LSATSourceExtractor — turns a scanned page into LSAT question drafts.

The counterpart of :class:`~law_ai.agents_runtime.crews.lsat_content_author.LSATContentAuthor`:
that crew *invents* an item against a target, this one *transcribes* an item that
already exists on a page a camera photographed. The page text arrives from `ocrmd`
(https://github.com/bamr87/ocrmd), which reads every page twice — local OCR engines
and a vision model — and marks the disagreements rather than silently choosing.

Which is the whole reason this agent exists in the shape it does. The upstream tool
exists because a model once fabricated a table of contents for a page it could not
read; the same failure here would put an invented answer choice (E) into the question
bank with a photograph attached, and the photograph would make it look *more*
trustworthy, not less. So:

* the prompt is an extraction refusal, not an authoring brief (leave it empty rather
  than fill in what a page of this kind would probably say);
* every draft is scored for **grounding** — the share of its words that actually
  occur in the page text — and one below :data:`GROUNDING_FLOOR` is dropped here,
  before it can reach a reviewer wearing a page number;
* the answer key and the explanation each carry a ``printed`` / ``inferred`` source,
  because a prep book rarely prints the key beside the question, and a reviewer
  needs to know whether they are checking a transcription or a model's reasoning.

Nothing here writes to the live bank. Drafts land in the spec-019 proposal store as
``pending`` with the scan's provenance in ``meta`` (constitution §4/§5), which is
what :mod:`law_ai.lsat.services.ocr_intake` does with the output.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, model_validator

from law_ai.core import claude_code, llm
from law_ai.core.provenance import provenance
from law_ai.lsat.services.bank import (
    DIFFICULTY_ORDER,
    MCQ_SECTIONS,
    ChoiceLabel,
    Difficulty,
    Section,
    load_concepts,
)

from law_ai.agents_runtime.crews.lsat_content_author import (
    _MAX_EXPLANATION_CHARS,
    _MAX_STEM_CHARS,
    DraftChoice,
    DraftQuestion,
)

logger = logging.getLogger("law_ai.agents.lsat_source_extractor")

PROMPT_VERSION = "lsat_source_extractor/1"
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "lsat_source_extractor.v1.md"
)

_CHOICE_LABELS: tuple[ChoiceLabel, ...] = ("A", "B", "C", "D", "E")

#: Longest page text we forward. A two-page spread of dense LR runs ~6k chars;
#: past this the request is almost certainly a whole document, not a page.
MAX_SOURCE_CHARS = 24_000

#: Share of a draft's content words that must occur in the page text before the
#: draft is believed. Set from what the failure mode costs, not from a measured
#: distribution: a faithful transcription scores ~1.0 (it is a copy), and the only
#: things that pull it down are the model's own fixes to scanning damage. 0.75
#: leaves room for those while a fabricated choice — which shares only stopwords
#: and the topic's vocabulary with the page — lands far below.
GROUNDING_FLOOR = 0.75

#: Words that carry no evidence of copying: they are in every page and every
#: invention alike, so counting them would flatter a fabricated choice.
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "for",
        "with",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "which",
        "who",
        "whom",
        "whose",
        "what",
        "when",
        "where",
        "why",
        "how",
        "not",
        "no",
        "nor",
        "so",
        "than",
        "then",
        "there",
        "their",
        "they",
        "them",
        "he",
        "she",
        "his",
        "her",
        "him",
        "we",
        "us",
        "our",
        "you",
        "your",
        "i",
        "all",
        "any",
        "both",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "only",
        "own",
        "same",
        "too",
        "very",
        "can",
        "will",
        "just",
        "do",
        "does",
        "did",
        "done",
        "have",
        "has",
        "had",
        "having",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "about",
        "into",
        "over",
        "under",
        "again",
        "further",
        "once",
        "here",
        "also",
    ]
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# ocrmd's disagreement marks: `==word==[^ocrmd-3]`. The word between the equals signs
# is one of two candidate readings; the footnote body lists both. Strip the marks and
# keep the word — the reviewer has the page image, and `flagged_spans` in the request
# provenance already tells them how many there were.
_FLAG_RE = re.compile(r"==(.+?)==(?:\[\^ocrmd-\d+\])?")
_FOOTNOTE_RE = re.compile(r"^\[\^ocrmd-\d+\]:.*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Pydantic contracts
# ---------------------------------------------------------------------------

KeySource = Literal["printed", "inferred"]


class ExtractQuestionsInput(BaseModel):
    """One page (or one region of one) offered to the extractor."""

    source_text: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)
    #: Which item on the page to take, in the operator's words — "question 15".
    #: Empty means every complete item the page holds.
    hint: str = ""
    #: Caller's expectation, used only as a steer; the model reads the page and
    #: may disagree, and a mismatch is the reviewer's to settle rather than ours.
    section: Section | None = None
    difficulty: Difficulty | None = None
    max_items: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def _reject_writing_section(self) -> ExtractQuestionsInput:
        if self.section is not None and self.section not in MCQ_SECTIONS:
            raise ValueError(
                f"section {self.section!r} has no multiple-choice form "
                f"(expected one of {list(MCQ_SECTIONS)})"
            )
        return self


class ExtractedQuestion(BaseModel):
    """A :class:`DraftQuestion` plus where each part of it came from.

    The extra fields never reach the bank — :meth:`as_draft` strips them — but they
    ride into the proposal's ``meta`` so a reviewer opening the HITL queue can see
    at a glance whether the key was on the page or the model worked it out.
    """

    section: Section
    difficulty: Difficulty
    stem: str = Field(max_length=_MAX_STEM_CHARS)
    choices: list[DraftChoice] = Field(min_length=5, max_length=5)
    correct: ChoiceLabel
    key_source: KeySource = "inferred"
    explanation: str = Field(max_length=_MAX_EXPLANATION_CHARS)
    explanation_source: KeySource = "inferred"
    concepts: list[str] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    source_excerpt: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=1000)
    #: Filled in by :func:`_score_grounding`, not by the model — it is a check *on*
    #: the model's answer, so letting the model report it would defeat the point.
    grounding: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_choice_labels(self) -> ExtractedQuestion:
        labels = [c.label for c in self.choices]
        if labels != list(_CHOICE_LABELS):
            raise ValueError("choices must be labelled A,B,C,D,E in order")
        if self.correct not in labels:
            raise ValueError("correct label must be one of A..E")
        if self.section not in MCQ_SECTIONS:
            raise ValueError(f"{self.section!r} has no multiple-choice form")
        return self

    def as_draft(self) -> DraftQuestion:
        """The bank-shaped subset, for the spec-019 gates and the proposal store."""
        return DraftQuestion(
            section=self.section,
            difficulty=self.difficulty,
            stem=self.stem,
            choices=list(self.choices),
            correct=self.correct,
            explanation=self.explanation,
            concepts=list(self.concepts),
            confidence=self.confidence,
        )


class ExtractQuestionsOutput(BaseModel):
    drafts: list[ExtractedQuestion] = Field(default_factory=list)
    #: Drafts the model produced that failed the grounding check, as
    #: ``(source_excerpt, grounding)`` — reported so an operator can tell "the page
    #: had nothing on it" from "the model made something up and we caught it".
    ungrounded: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = ""
    model: str = "fallback/offline"
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    latency_ms: float = 0.0
    degraded: bool = Field(
        False, description="True when no provider answered; drafts is then empty."
    )
    trace_id: str | None = None


# ---------------------------------------------------------------------------
# Grounding: is this draft a copy of the page, or a story about it?
# ---------------------------------------------------------------------------


def _content_tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


def _grounding(candidate: str, source_tokens: frozenset[str]) -> float:
    """Share of ``candidate``'s content words that occur in the page text.

    Containment, not similarity: the page holds far more than any one choice, so a
    symmetric measure (Jaccard) would score a perfect copy near zero. Empty text is
    1.0 — there is nothing unsupported in it — and the schema keeps it from being
    empty anyway.
    """
    tokens = _content_tokens(candidate)
    if not tokens:
        return 1.0
    return sum(1 for t in tokens if t in source_tokens) / len(tokens)


def _score_grounding(draft: ExtractedQuestion, source_tokens: frozenset[str]) -> float:
    """The draft's weakest verbatim part.

    The minimum rather than the mean, because the failure this guards against is
    *one* invented choice on an otherwise faithful transcription — averaging over a
    correct stem and four correct choices would hide exactly that. The explanation is
    excluded: when ``explanation_source`` is ``inferred`` it is the model's own
    reasoning and is *supposed* to contain words the page does not have.
    """
    parts = [draft.stem] + [c.text for c in draft.choices]
    return round(min(_grounding(p, source_tokens) for p in parts), 4)


def clean_page_text(text: str) -> str:
    """ocrmd's page Markdown as plain prose: disagreement marks and footnotes gone.

    The marks are the scanner's honesty about what it could not settle; the model is
    told what they mean, but leaving them in the text would also leak `==` into every
    verbatim copy the model makes of a marked line, and from there into the bank.
    """
    text = _FOOTNOTE_RE.sub("", text)
    text = _FLAG_RE.sub(r"\1", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Prompt + provider plumbing
# ---------------------------------------------------------------------------


def _load_prompt_template() -> str:
    if not PROMPT_PATH.is_file():  # pragma: no cover - prompts ship with code
        raise FileNotFoundError(f"missing prompt file: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


_LLM_SYSTEM = (
    "You transcribe LSAT questions that already exist on a scanned page into "
    "structured JSON. You never invent a stem, a choice, or a question that is not "
    "on the page — if the page text is incomplete you return fewer drafts and say "
    "why. Respond with a single JSON object only, no preamble and no markdown "
    "code fences."
)

_EXTRACT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "drafts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "enum": list(MCQ_SECTIONS)},
                    "difficulty": {"type": "string", "enum": list(DIFFICULTY_ORDER)},
                    "stem": {"type": "string"},
                    "choices": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {
                                    "type": "string",
                                    "enum": list(_CHOICE_LABELS),
                                },
                                "text": {"type": "string"},
                            },
                            "required": ["label", "text"],
                            "additionalProperties": False,
                        },
                    },
                    "correct": {"type": "string", "enum": list(_CHOICE_LABELS)},
                    "key_source": {"type": "string", "enum": ["printed", "inferred"]},
                    "explanation": {"type": "string"},
                    "explanation_source": {
                        "type": "string",
                        "enum": ["printed", "inferred"],
                    },
                    "concepts": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "source_excerpt": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": [
                    "section",
                    "difficulty",
                    "stem",
                    "choices",
                    "correct",
                    "key_source",
                    "explanation",
                    "explanation_source",
                    "concepts",
                    "confidence",
                    "source_excerpt",
                    "notes",
                ],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["drafts", "notes"],
    "additionalProperties": False,
}


def _build_prompt(inp: ExtractQuestionsInput, *, catalog: list[dict[str, str]]) -> str:
    request: dict[str, Any] = {
        "wanted": inp.hint or "every complete question on the page",
        "max_items": inp.max_items,
        "expected_section": inp.section,
        "expected_difficulty": inp.difficulty,
        "concept_catalog": catalog,
    }
    return (
        _load_prompt_template()
        + "\n\n## Request\n\n```json\n"
        + json.dumps(request, indent=2)
        + "\n```\n\n## Page text\n\n"
        + clean_page_text(inp.source_text)[:MAX_SOURCE_CHARS]
        + "\n"
    )


def _normalize_choices(item: dict[str, Any]) -> None:
    """Coerce ``item['choices']`` to the canonical A-E set when possible.

    Same repair as the author crew's: structured outputs cannot cap array length, so
    a stray or duplicated label is a normal model slip rather than a fabrication.
    Note what this deliberately does *not* do — it never fills a missing label. A
    page that yielded only four choices must fail, not acquire a fifth here.
    """
    raw_choices = item.get("choices")
    if not isinstance(raw_choices, list):
        return
    by_label: dict[str, str] = {}
    for ch in raw_choices:
        if not isinstance(ch, dict):
            continue
        label, text = ch.get("label"), str(ch.get("text") or "").strip()
        if label in _CHOICE_LABELS and label not in by_label and text:
            by_label[label] = text
    if all(label in by_label for label in _CHOICE_LABELS):
        item["choices"] = [{"label": lb, "text": by_label[lb]} for lb in _CHOICE_LABELS]


def _parse(raw: str, inp: ExtractQuestionsInput) -> tuple[list[ExtractedQuestion], str]:
    try:
        obj = llm.loads_first_json(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response not JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError("LLM response is not a JSON object")
    notes = str(obj.get("notes") or "")[:1000]
    raw_drafts = obj.get("drafts")
    if not isinstance(raw_drafts, list):
        raise ValueError("LLM response missing a 'drafts' list")

    out: list[ExtractedQuestion] = []
    for item in raw_drafts:
        if not isinstance(item, dict):
            continue
        if inp.section is not None:
            item.setdefault("section", inp.section)
        item.setdefault("difficulty", inp.difficulty or "med")
        _normalize_choices(item)
        try:
            out.append(ExtractedQuestion.model_validate(item))
        except Exception as exc:
            # An incomplete item is the *expected* outcome on a page whose question
            # runs over the fold — info, not a warning, and never repaired.
            logger.info("LSATSourceExtractor: discarding malformed draft: %s", exc)
    return out[: inp.max_items], notes


# ---------------------------------------------------------------------------
# Public crew
# ---------------------------------------------------------------------------


class LSATSourceExtractor:
    """Transcribes LSAT items off a scanned page into HITL proposals.

    Unlike :class:`LSATContentAuthor` there is **no offline fallback draft**. A
    placeholder is a defensible answer when the job is "invent something for a
    reviewer to reject"; it is not one when the job is "tell me what is printed on
    this page", where the only honest answer with no provider is none at all. A
    degraded run returns ``drafts=[]`` and says so.
    """

    name = "LSATSourceExtractor"
    description = (
        "Transcribes an LSAT question off a scanned page (ocrmd) into a structured "
        "draft. Extraction only — never authors content. Every draft is HITL-gated "
        "and carries the page it came from."
    )
    human_approval_required = True

    async def run(self, input_data: dict[str, Any]) -> ExtractQuestionsOutput:
        inp = ExtractQuestionsInput.model_validate(input_data)
        started = time.perf_counter()

        catalog_all = load_concepts().values()
        wanted_sections = {inp.section} if inp.section else set(MCQ_SECTIONS)
        catalog = [
            {"id": c.id, "name": c.name, "summary": c.summary}
            for c in catalog_all
            if wanted_sections & set(c.sections)
        ][:25]

        drafts: list[ExtractedQuestion] = []
        ungrounded: list[dict[str, Any]] = []
        notes = ""
        degraded = False
        model_used = "fallback/offline"
        try:
            result = await llm.agenerate(
                _build_prompt(inp, catalog=catalog),
                system=_LLM_SYSTEM,
                response_schema=_EXTRACT_RESPONSE_SCHEMA,
                agent="lsat_source_extractor",
            )
            model_used = result.model_label
            drafts, notes = _parse(result.text, inp)
        except (
            TimeoutError,
            httpx.HTTPError,
            OSError,
            ValueError,
            claude_code.ClaudeCodeUnavailableError,
            llm.LLMUnavailableError,
        ) as exc:
            logger.info("LSATSourceExtractor: no usable provider response: %s", exc)
            degraded = True
            notes = f"extraction unavailable: {type(exc).__name__}: {str(exc)[:200]}"
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "LSATSourceExtractor unexpected error: %s", exc, exc_info=True
            )
            degraded = True
            notes = f"extraction failed: {type(exc).__name__}"

        # The check on the model's answer, run against the page it was given.
        source_tokens = frozenset(_content_tokens(clean_page_text(inp.source_text)))
        kept: list[ExtractedQuestion] = []
        for d in drafts:
            d.grounding = _score_grounding(d, source_tokens)
            if d.grounding < GROUNDING_FLOOR:
                logger.warning(
                    "LSATSourceExtractor: dropping ungrounded draft (%.2f < %.2f): %r",
                    d.grounding,
                    GROUNDING_FLOOR,
                    d.source_excerpt or d.stem[:80],
                )
                ungrounded.append(
                    {
                        "source_excerpt": d.source_excerpt or d.stem[:120],
                        "grounding": d.grounding,
                    }
                )
                continue
            kept.append(d)
        drafts = kept

        latency_ms = (time.perf_counter() - started) * 1000.0
        confidence = (
            round(sum(d.confidence for d in drafts) / len(drafts), 4) if drafts else 0.0
        )

        trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data={
                "hint": inp.hint,
                "source_chars": len(inp.source_text),
                "expected_section": inp.section,
                "expected_difficulty": inp.difficulty,
                "max_items": inp.max_items,
            },
            output_data={
                "draft_count": len(drafts),
                "ungrounded_count": len(ungrounded),
                "model": model_used,
                "confidence": confidence,
                "degraded": degraded,
                "key_sources": [d.key_source for d in drafts],
            },
            model=model_used,
            latency_ms=latency_ms,
            confidence=confidence,
            sources=[],
        )

        return ExtractQuestionsOutput(
            drafts=drafts,
            ungrounded=ungrounded,
            notes=notes,
            model=model_used,
            confidence=confidence,
            latency_ms=round(latency_ms, 2),
            degraded=degraded,
            trace_id=trace_id,
        )
