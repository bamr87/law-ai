"""Generation-plane executors — pluggable fulfillment of manifest jobs.

Spec 024 FR-6. Three ways to turn a :class:`GenerationJob` into drafts:

* :class:`ClaudeCodeExecutor` — tier-routed Claude generation. Maps the job's
  tier onto a Claude model id (bulk→Haiku, standard→Sonnet, premium→Opus,
  judge→Fable by default) and authenticates with the OAuth subscription token
  when present, falling back to ``ANTHROPIC_API_KEY``. Construction raises
  :class:`ExecutorUnavailable` when neither credential is configured.
* :class:`OllamaExecutor` — the local open-weights path; every tier maps to
  ``OLLAMA_DEFAULT_MODEL``.
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

import httpx
from pydantic import BaseModel

from law_ai.agents_runtime.crews.lsat_content_author import (
    _DRAFTS_RESPONSE_SCHEMA,
)
from law_ai.core import claude_code
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


class OllamaExecutor:
    """Local product-runtime generation; every tier → the Ollama default model."""

    name = "ollama"

    def __init__(self, config: FactoryConfig) -> None:
        self._config = config

    async def execute(self, job: GenerationJob) -> RawBatch:
        model = str(settings.OLLAMA_DEFAULT_MODEL)
        url = str(settings.OLLAMA_BASE_URL).rstrip("/") + "/api/generate"
        payload = {
            "model": model,
            "prompt": job.prompt,
            "stream": False,
            "options": {"temperature": 0.4},
            "format": "json",
        }
        timeout = httpx.Timeout(float(settings.OLLAMA_REQUEST_TIMEOUT_S))
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise ExecutionError(f"job {job.job_id}: Ollama error ({exc})") from exc
        latency_ms = (time.perf_counter() - started) * 1000.0
        raw = str(data.get("response") or "").strip()
        return RawBatch(
            job_id=job.job_id,
            payload=_parse_payload(raw, job.job_id),
            model_label=model,
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
