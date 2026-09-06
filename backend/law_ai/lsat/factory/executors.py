"""Generation-plane executors — pluggable fulfillment of manifest jobs.

Spec 024 FR-6, extended by spec 050. Five ways to turn a
:class:`GenerationJob` into drafts:

* :class:`ClaudeCodeExecutor` — tier-routed Claude generation. Maps the job's
  tier onto a Claude model id (bulk→Haiku, standard→Sonnet, premium→Opus,
  judge→Fable by default) and authenticates with the OAuth subscription token
  when present, falling back to ``ANTHROPIC_API_KEY``. Construction raises
  :class:`ExecutorUnavailable` when neither credential is configured.
* :class:`XaiExecutor` — xAI Grok over its subscription OAuth token, routed
  through ``law_ai.core.llm`` with the chain pinned to that one provider, so
  the run stays as attributable as the Claude path while keeping the call
  inside the constitution §4 choke point.
* :class:`OllamaExecutor` — the local open-weights path; every tier maps to
  ``OLLAMA_DEFAULT_MODEL``.
* :class:`SynthExecutor` — no network and no model: fulfills a job from the
  spec 049 synthesis engine, whose keys are proved by a finite-model checker
  rather than asserted. Drafts still pass every intake gate and still land in
  the HITL queue; the proof buys reviewer *confidence*, not a bypass (the
  bounded bypass lives in ``law_ai.lsat.synth.promote`` and is off by default).
* :class:`DraftFileExecutor` — no network at all: fulfills jobs from an
  externally produced JSONL of ``{"job_id": …, "drafts": […]}`` records,
  which is how out-of-process generation farms (or a Claude Code session
  fanning out subagents) hand results back to the pipeline.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from law_ai.agents_runtime.crews.lsat_content_author import (
    _DRAFTS_RESPONSE_SCHEMA,
)
from law_ai.core import claude_code, llm, xai_oauth
from law_ai.core.llm.base import LLMRequest, LLMUnavailableError
from law_ai.core.settings_proxy import settings_proxy as settings
from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.manifest import GenerationJob


class ExecutorUnavailable(RuntimeError):
    """The chosen executor cannot run in this environment/configuration."""


class ExecutionError(RuntimeError):
    """A job failed at the executor (transport, parse, or missing drafts)."""


class RawBatch(BaseModel):
    """One job's parsed generation output, ready for intake gating."""

    job_id: str
    payload: dict[str, Any]
    model_label: str
    latency_ms: float = 0.0


class Executor(Protocol):
    """Anything that can fulfill one manifest job."""

    name: str

    async def execute(self, job: GenerationJob) -> RawBatch:  # pragma: no cover
        ...


_SYSTEM = (
    "You are an expert LSAT item writer. Follow the instructions exactly and "
    "respond with a single JSON object only — no preamble, no markdown fences."
)

#: ``agent`` recorded on every ``llm_call`` provenance event the model-backed
#: executors write, so a factory batch is attributable in the audit trail.
FACTORY_AGENT = "lsat_factory"


def _parse_payload(raw: str, job_id: str) -> dict[str, Any]:
    try:
        obj = claude_code.loads_first_json(raw)
    except json.JSONDecodeError as exc:
        raise ExecutionError(f"job {job_id}: response is not JSON ({exc})") from exc
    if not isinstance(obj, dict) or not isinstance(obj.get("drafts"), list):
        raise ExecutionError(f"job {job_id}: response missing 'drafts' list")
    return obj


class ClaudeCodeExecutor:
    """Tier-routed Claude generation (see module docstring).

    The factory pins a provider explicitly rather than running the chain, so
    that a manifest's tier→model routing is reproducible: a silent fallback to
    a different tier — or to the local model — would make a generated bank
    impossible to attribute. Use ``--executor ollama`` for the local path.
    """

    name = "claude_code"

    def __init__(self, config: FactoryConfig) -> None:
        self._auth: claude_code.AuthMode = (
            "oauth" if claude_code.oauth_token() is not None else "api_key"
        )
        if claude_code.credential(self._auth) is None:
            raise ExecutorUnavailable(
                "no Claude credential configured — set CLAUDE_CODE_OAUTH_TOKEN "
                "(`claude setup-token`) or ANTHROPIC_API_KEY"
            )
        self._config = config

    async def execute(self, job: GenerationJob) -> RawBatch:
        model_id = self._config.claude_tier_models[job.tier]
        # Structured outputs pin the items-mode response shape; passage sets
        # carry an extra top-level "passage" object, so they rely on the
        # defensive JSON parse instead.
        schema = _DRAFTS_RESPONSE_SCHEMA if job.target.mode == "items" else None
        started = time.perf_counter()
        raw = await claude_code.generate(
            job.prompt,
            system=_SYSTEM,
            model_id=model_id,
            max_tokens=int(getattr(settings, "LSAT_FACTORY_MAX_TOKENS", 8192)),
            response_schema=schema,
            auth=self._auth,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        return RawBatch(
            job_id=job.job_id,
            payload=_parse_payload(raw, job.job_id),
            model_label=f"{claude_code.PROVIDER_NAME}/{model_id}",
            latency_ms=round(latency_ms, 2),
        )


class XaiExecutor:
    """xAI Grok generation, pinned to that one tier (spec 050).

    Same reproducibility contract as :class:`ClaudeCodeExecutor` — a manifest
    must be attributable to the provider that actually wrote it, so a silent
    fall-through to another tier is unacceptable — but it gets there through
    ``law_ai.core.llm`` with ``providers=("xai",)`` rather than by calling a
    transport directly. Restricting the chain to a single provider pins the
    routing just as hard while keeping the call inside the sanctioned choke
    point, so the batch also lands in the ``llm_call`` audit trail
    (constitution §4).

    Grok is slow on this work (item authoring measured ~57-116s per job), so
    expect factory runs on this executor to take substantially longer than the
    Claude tiers.
    """

    name = "xai"

    def __init__(self, config: FactoryConfig) -> None:
        if not xai_oauth.is_configured():
            raise ExecutorUnavailable(
                xai_oauth.unconfigured_reason()
                or "no xAI credential configured — run `make xai-login`"
            )
        self._config = config

    async def execute(self, job: GenerationJob) -> RawBatch:
        schema = _DRAFTS_RESPONSE_SCHEMA if job.target.mode == "items" else None
        started = time.perf_counter()
        try:
            result = await llm.aroute(
                LLMRequest(
                    prompt=job.prompt,
                    system=_SYSTEM,
                    response_schema=schema,
                    max_tokens=int(getattr(settings, "LSAT_FACTORY_MAX_TOKENS", 8192)),
                    providers=(xai_oauth.PROVIDER_NAME,),
                ),
                agent=FACTORY_AGENT,
            )
        except LLMUnavailableError as exc:
            raise ExecutionError(f"job {job.job_id}: xAI unavailable ({exc})") from exc
        latency_ms = (time.perf_counter() - started) * 1000.0
        return RawBatch(
            job_id=job.job_id,
            payload=_parse_payload(result.text, job.job_id),
            model_label=result.model_label,
            latency_ms=round(latency_ms, 2),
        )


class OllamaExecutor:
    """Local product-runtime generation; every tier → the Ollama default model.

    Routed through ``law_ai.core.llm`` with the chain pinned to the Ollama
    provider (BL-20260810-05): the transport, its timeout, and its bounded
    retry/backoff live in :class:`~law_ai.core.llm.providers.OllamaProvider`,
    and every batch writes an ``llm_call`` provenance event like the hosted
    executors do (constitution §4). A pinned single-provider chain cannot fall
    through to a hosted tier, so a nightly local run never bills anyone.
    """

    name = "ollama"

    def __init__(self, config: FactoryConfig) -> None:
        self._config = config

    async def execute(self, job: GenerationJob) -> RawBatch:
        model = str(settings.OLLAMA_DEFAULT_MODEL)
        started = time.perf_counter()
        try:
            result = await llm.aroute(
                LLMRequest(
                    prompt=job.prompt,
                    system=_SYSTEM,
                    json_mode=True,
                    temperature=0.4,
                    models={llm.OLLAMA: model},
                    providers=(llm.OLLAMA,),
                ),
                agent=FACTORY_AGENT,
            )
        except LLMUnavailableError as exc:
            raise ExecutionError(f"job {job.job_id}: Ollama error ({exc})") from exc
        latency_ms = (time.perf_counter() - started) * 1000.0
        return RawBatch(
            job_id=job.job_id,
            payload=_parse_payload(result.text, job.job_id),
            model_label=result.model_label,
            latency_ms=round(latency_ms, 2),
        )


class DraftFileExecutor:
    """Fulfill jobs from an externally produced drafts JSONL (no network).

    File format — one JSON object per line::

        {"job_id": "mfst-…-job01", "drafts": [...],
         "passage": {...}?, "model": "claude_code/claude-haiku-4-5"?}

    Unknown job ids in the file are ignored; a job with no record raises
    :class:`ExecutionError` so the pipeline reports it as unfulfilled.
    """

    name = "drafts_file"

    def __init__(self, path: Path) -> None:
        if not path.is_file():
            raise ExecutorUnavailable(f"drafts file not found: {path}")
        self._by_job: dict[str, dict[str, Any]] = {}
        with path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ExecutorUnavailable(
                        f"drafts file {path} has a malformed line: {exc}"
                    ) from exc
                job_id = record.get("job_id")
                if isinstance(job_id, str):
                    self._by_job[job_id] = record

    def fulfilled_job_ids(self) -> set[str]:
        """Job ids the drafts file actually contains records for."""
        return set(self._by_job)

    async def execute(self, job: GenerationJob) -> RawBatch:
        record = self._by_job.get(job.job_id)
        if record is None:
            raise ExecutionError(f"job {job.job_id}: no record in drafts file")
        if not isinstance(record.get("drafts"), list):
            raise ExecutionError(f"job {job.job_id}: record missing 'drafts' list")
        payload: dict[str, Any] = {"drafts": record["drafts"]}
        if isinstance(record.get("passage"), dict):
            payload["passage"] = record["passage"]
        return RawBatch(
            job_id=job.job_id,
            payload=payload,
            model_label=str(record.get("model") or "external"),
            latency_ms=0.0,
        )


class SynthExecutor:
    """Fulfill a job deterministically from the spec 049 synthesis engine.

    The factory's plan is expressed in *archetypes*; the engine's schemas each
    declare the archetype they realize, so a job is fulfilled by finding the
    schemas that match and generating against whichever domain packs can supply
    the vocabulary. A job whose archetype no schema covers is a legitimate
    miss — the LLM executors exist for exactly those — and it reports so rather
    than substituting something else.

    Seeds are derived from the job id, so re-running a manifest reproduces the
    same drafts instead of flooding the queue with near-duplicates.
    """

    name = "synth"

    def __init__(self, *, domain: str | None = None) -> None:
        self._domain = domain

    async def execute(self, job: GenerationJob) -> RawBatch:
        import time

        from law_ai.lsat.synth import ENGINE_VERSION
        from law_ai.lsat.synth.generate import generate_batch
        from law_ai.lsat.synth.lexicon import load_domains
        from law_ai.lsat.synth.schemas import all_schemas

        started = time.perf_counter()
        target = job.target
        matching = [
            s
            for s in all_schemas()
            if s.meta.archetype_id == target.archetype_id
            and s.meta.section == target.section
        ]
        if not matching:
            raise ExecutionError(
                f"no synthesis schema covers archetype {target.archetype_id!r} — "
                "this target needs an LLM executor"
            )

        domains = load_domains()
        if self._domain:
            candidates = [domains[self._domain]] if self._domain in domains else []
        else:
            candidates = list(domains.values())
        if not candidates:
            raise ExecutionError(
                f"no domain pack available (asked for {self._domain!r})"
            )

        # A stable seed per job: the same manifest replays to the same drafts.
        base_seed = abs(hash(job.job_id)) % 100_000
        drafts: list[dict[str, Any]] = []
        for index in range(target.count):
            schema = matching[index % len(matching)]
            usable = [d for d in candidates if d.supports(schema.meta.capability)]
            if not usable:
                continue
            domain = usable[index % len(usable)]
            item = generate_batch(
                schema.meta.id, domain.id, count=1, start_seed=base_seed + index
            )[0]
            payload = item.question.model_dump(mode="json")
            # The intake gates read a draft, not a bank row: no id, and a
            # confidence the gates can threshold on. 1.0 here means "a checker
            # proved this", which is a different claim from a model's own score.
            payload.pop("id", None)
            payload.pop("source", None)
            payload.pop("type", None)
            payload.pop("references", None)
            payload["confidence"] = (
                1.0 if item.provenance.proof_kind == "logical" else 0.5
            )
            drafts.append(payload)

        if not drafts:
            raise ExecutionError(
                f"no domain pack could supply content for archetype "
                f"{target.archetype_id!r}"
            )
        return RawBatch(
            job_id=job.job_id,
            payload={"drafts": drafts},
            model_label=f"deterministic/{ENGINE_VERSION}",
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )
