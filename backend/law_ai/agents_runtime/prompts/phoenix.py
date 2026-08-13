"""One-way sync of local prompt files into Arize Phoenix (spec 036).

Mirrors every :class:`~law_ai.agents_runtime.prompts.registry.LocalPrompt`
into the self-hosted Phoenix container's prompt store over its REST API.
The repo files stay canonical: sync only ever writes *to* Phoenix, and an
unchanged file never creates a new Phoenix version.

Phoenix 12.9.0 only accepts ``CHAT`` prompt templates, so each markdown
file is published verbatim as a single ``system`` message with
``template_format: NONE`` (our prompts contain literal braces and JSON
examples that MUSTACHE/F_STRING parsing would mangle).

No LLM is ever called here; this is metadata plumbing, so it deliberately
does not touch ``law_ai.core.llm``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx
from django.conf import settings

from law_ai.agents_runtime.prompts.registry import LocalPrompt, iter_local_prompts
from law_ai.core.provenance import ProvenanceLogger

__all__ = ["PromptSyncResult", "SyncReport", "phoenix_base_url", "sync_prompts"]

_TIMEOUT_SECONDS = 10.0
_TRANSPORT_RETRIES = 2
_TRACES_SUFFIX = "/v1/traces"
# Phoenix requires model metadata on every prompt version (playground
# defaults only — the runtime model is still chosen by law_ai.core.llm).
_ANTHROPIC_FALLBACK_MODEL = "claude-sonnet-5"
_ANTHROPIC_MAX_TOKENS = 4096


@dataclass(frozen=True)
class PromptSyncResult:
    name: str
    tag: str | None
    sha256: str
    outcome: str
    """``created`` | ``updated`` | ``skipped`` | ``error``."""
    detail: str = ""


@dataclass(frozen=True)
class SyncReport:
    base_url: str
    dry_run: bool
    results: list[PromptSyncResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.outcome != "error" for r in self.results)

    def count(self, outcome: str) -> int:
        return sum(1 for r in self.results if r.outcome == outcome)


def phoenix_base_url() -> str | None:
    """Resolve the Phoenix REST base URL from settings.

    ``PHOENIX_BASE_URL`` wins; otherwise it is derived from
    ``PHOENIX_COLLECTOR_ENDPOINT`` by stripping the ``/v1/traces`` suffix.
    ``None`` means Phoenix is not configured and the sync must not run.
    """
    explicit = str(getattr(settings, "PHOENIX_BASE_URL", "") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    collector = str(getattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", "") or "").strip()
    if not collector:
        return None
    base = collector.rstrip("/")
    if base.endswith(_TRACES_SUFFIX):
        base = base[: -len(_TRACES_SUFFIX)]
    return base.rstrip("/") or None


def _model_metadata() -> tuple[str, str, dict[str, Any]]:
    """Provider/model/invocation metadata mirroring the runtime chain head."""
    chain = str(getattr(settings, "LLM_PROVIDER_CHAIN", "") or "")
    head = chain.split(",", maxsplit=1)[0].strip().lower() if chain else ""
    if head in {"claude_code", "anthropic_api"}:
        model = str(getattr(settings, "ANTHROPIC_MODEL", "") or "").strip()
        return (
            "ANTHROPIC",
            model or _ANTHROPIC_FALLBACK_MODEL,
            {"type": "anthropic", "anthropic": {"max_tokens": _ANTHROPIC_MAX_TOKENS}},
        )
    model = str(getattr(settings, "OLLAMA_DEFAULT_MODEL", "") or "").strip()
    return ("OLLAMA", model or "llama3", {"type": "ollama", "ollama": {}})


def _template_text(version_data: dict[str, Any]) -> str | None:
    """Extract the message text from a Phoenix prompt-version payload."""
    template = version_data.get("template") or {}
    messages = template.get("messages") or []
    if not messages:
        return None
    content = messages[0].get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return None


def _existing_text(client: httpx.Client, prompt: LocalPrompt) -> str | None:
    """Current Phoenix content for ``prompt`` (by tag, else latest), or None."""
    if prompt.tag is not None:
        url = f"/v1/prompts/{prompt.name}/tags/{prompt.tag}"
    else:
        url = f"/v1/prompts/{prompt.name}/latest"
    response = client.get(url)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    data: dict[str, Any] = response.json().get("data") or {}
    return _template_text(data)


def _push(client: httpx.Client, prompt: LocalPrompt, text: str) -> None:
    provider, model, invocation = _model_metadata()
    body: dict[str, Any] = {
        "prompt": {"name": prompt.name, "description": prompt.description},
        "version": {
            "description": f"{prompt.tag or 'untagged'} sha256:{prompt.sha256[:12]}",
            "model_provider": provider,
            "model_name": model,
            "template": {
                "type": "chat",
                "messages": [{"role": "system", "content": text}],
            },
            "template_type": "CHAT",
            "template_format": "NONE",
            "invocation_parameters": invocation,
        },
    }
    response = client.post("/v1/prompts", json=body)
    response.raise_for_status()
    version_id = str(response.json()["data"]["id"])
    if prompt.tag is not None:
        tag_response = client.post(
            f"/v1/prompt_versions/{version_id}/tags",
            json={"name": prompt.tag, "description": f"file {prompt.path.name}"},
        )
        tag_response.raise_for_status()


def _sync_one(
    client: httpx.Client, prompt: LocalPrompt, *, dry_run: bool
) -> PromptSyncResult:
    text = prompt.text
    sha = prompt.sha256
    try:
        existing = _existing_text(client, prompt)
        if existing == text:
            return PromptSyncResult(prompt.name, prompt.tag, sha, "skipped")
        outcome = "created" if existing is None else "updated"
        if not dry_run:
            _push(client, prompt, text)
        return PromptSyncResult(prompt.name, prompt.tag, sha, outcome)
    except httpx.HTTPError as exc:
        return PromptSyncResult(prompt.name, prompt.tag, sha, "error", str(exc))


def sync_prompts(
    *,
    base_url: str | None = None,
    dry_run: bool = False,
    client: httpx.Client | None = None,
) -> SyncReport:
    """Mirror every local prompt into Phoenix. Idempotent (see spec 036 FR-3).

    Raises :class:`RuntimeError` when no Phoenix base URL is configured.
    ``client`` is injectable for tests; callers otherwise get a fresh
    ``httpx.Client`` with timeout + connect retries (NFR-SEC-1).
    """
    resolved = (base_url or "").strip().rstrip("/") or phoenix_base_url()
    if not resolved:
        raise RuntimeError(
            "Phoenix is not configured: set PHOENIX_BASE_URL (or "
            "PHOENIX_COLLECTOR_ENDPOINT) to enable prompt sync"
        )
    report = SyncReport(base_url=resolved, dry_run=dry_run)
    owns_client = client is None
    http = client or httpx.Client(
        base_url=resolved,
        timeout=_TIMEOUT_SECONDS,
        transport=httpx.HTTPTransport(retries=_TRANSPORT_RETRIES),
    )
    try:
        for prompt in iter_local_prompts():
            report.results.append(_sync_one(http, prompt, dry_run=dry_run))
    finally:
        if owns_client:
            http.close()
    if not dry_run:
        ProvenanceLogger.log_event(
            "prompt_sync",
            {
                "phoenix_base_url": resolved,
                "created": report.count("created"),
                "updated": report.count("updated"),
                "skipped": report.count("skipped"),
                "errors": report.count("error"),
                "prompts": [
                    {
                        "name": r.name,
                        "tag": r.tag,
                        "sha256": r.sha256[:12],
                        "outcome": r.outcome,
                    }
                    for r in report.results
                ],
            },
        )
    return report
