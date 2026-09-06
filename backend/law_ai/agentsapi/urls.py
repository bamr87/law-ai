"""Agent operations endpoints (spec 003 → spec 011 FR-9 port).

DRF 3.17 lacks native async views, so each public method stays sync and
delegates to ``async_to_sync(...)`` for any I/O. The function-level
helpers (`_probe_ollama`, `_probe_checkpointer`, `_probe_phoenix`) are
deliberately exposed at module scope so existing tests that monkeypatch
them keep working.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from asgiref.sync import async_to_sync
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView

from law_ai.agents_runtime.registry import AGENT_REGISTRY, register_all_agents
from law_ai.core import audit_jsonl as audit_store
from law_ai.core.auth import RequireAgent
from law_ai.core.throttling import ScopedActorRateThrottle

_BACKLOG_BULLET_RE = re.compile(
    r"^- \*\*(?P<id>BL-\d{8}-\d{2})\*\* — \*(?P<kind>[a-z-]+),\s*(?P<sev>low|med|high)\* — (?P<title>.+)$"
)
_SECTION_RE = re.compile(r"^## (Open|Claimed|Done)\s*$")
_SPEC_STATUS_RE = re.compile(r"^- \*\*Status\*\*:\s*(?P<status>.+)$", re.MULTILINE)


def _repo_root() -> Path:
    """Return the repository root.

    Reads ``settings.REPO_ROOT`` (backed by the ``REPO_ROOT`` env var) so
    that the correct path is available whether running on the host or in a
    Docker container where only ``./backend`` is mounted at ``/app``.
    Falls back to four ``parents`` above this file for host/venv runs.
    """
    from django.conf import settings as _s  # local import to avoid circular

    val: str = getattr(_s, "REPO_ROOT", "") or ""
    return Path(val) if val else Path(__file__).resolve().parents[3]


def _ensure_registry() -> dict[str, type]:
    if not AGENT_REGISTRY:
        register_all_agents()
    return AGENT_REGISTRY


def _parse_int_strict(raw: str | None, *, default: int, lo: int, hi: int) -> int:
    """Return ``int(raw)`` clamped to ``[lo, hi]`` or raise a 422-mapped error."""
    if raw is None:
        return default
    from rest_framework.exceptions import APIException

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


def _parse_backlog(text: str) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, str]]] = {"open": [], "claimed": [], "done": []}
    current: str | None = None
    for line in text.splitlines():
        section = _SECTION_RE.match(line)
        if section:
            current = section.group(1).lower()
            continue
        if not current:
            continue
        match = _BACKLOG_BULLET_RE.match(line)
        if match:
            buckets[current].append(
                {
                    "id": match.group("id"),
                    "kind": match.group("kind"),
                    "severity": match.group("sev"),
                    "title": match.group("title"),
                }
            )
    counts = {key: len(value) for key, value in buckets.items()}
    counts["total"] = sum(counts.values())
    return {"counts": counts, **buckets}


def _parse_spec_status(text: str) -> str:
    match = _SPEC_STATUS_RE.search(text)
    return match.group("status").strip() if match else "unknown"


# ---------------------------------------------------------------------------
# Local-AI health probes (spec 010) — module-level so tests can patch.
# ---------------------------------------------------------------------------


async def _probe_ollama() -> dict[str, Any]:
    import httpx
    from django.conf import settings

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
            models = [m.get("name") for m in resp.json().get("models", [])]
            return {"reachable": True, "models": [m for m in models if m]}
    except Exception as exc:
        return {"reachable": False, "models": [], "error": str(exc)[:200]}


async def _probe_checkpointer() -> dict[str, Any]:
    from django.conf import settings

    from law_ai.agents_runtime.graphs.runtime import (
        CheckpointerUnavailableError,
        build_checkpointer,
    )

    kind = settings.LANGGRAPH_CHECKPOINTER
    try:
        cm_or_saver = build_checkpointer()
    except CheckpointerUnavailableError as exc:
        return {"kind": kind, "reachable": False, "error": str(exc)[:200]}
    if hasattr(cm_or_saver, "__aenter__"):
        try:
            async with cm_or_saver:
                return {"kind": kind, "reachable": True}
        except Exception as exc:
            return {"kind": kind, "reachable": False, "error": str(exc)[:200]}
    return {"kind": kind, "reachable": True}


async def _probe_claude_code() -> dict[str, Any]:
    """Claude-over-OAuth reachability (tier 1 of the chain).

    Delegates to :func:`law_ai.core.claude_code.probe`, which reports inline
    rather than raising so one dead provider cannot fail the health response.
    """
    from law_ai.core import claude_code

    return await claude_code.probe(auth="oauth")


async def _probe_llm_chain() -> list[dict[str, Any]]:
    """Every provider in ``LLM_PROVIDER_CHAIN``, in the order it is tried.

    This is the probe that matters operationally: it answers "which provider
    is actually going to serve the next request, and why" in one payload.
    """
    from law_ai.core import llm

    return await llm.chain_status()


async def _probe_phoenix() -> dict[str, Any]:
    from urllib.parse import urlsplit

    import httpx
    from django.conf import settings

    endpoint = settings.PHOENIX_COLLECTOR_ENDPOINT
    ui_url = settings.PHOENIX_UI_URL
    if not endpoint:
        return {"reachable": False, "ui_url": ui_url, "enabled": False}
    parts = urlsplit(endpoint)
    probe_url = f"{parts.scheme}://{parts.netloc}/"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(probe_url)
            return {
                "reachable": resp.status_code < 500,
                "ui_url": ui_url,
                "enabled": True,
            }
    except Exception as exc:
        return {
            "reachable": False,
            "ui_url": ui_url,
            "enabled": True,
            "error": str(exc)[:200],
        }


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class _Base(APIView):
    """The gate and the quota every ``/api/agents/*`` read shares.

    The throttle is BL-20260430-09's half of BL-20260503-12: these are cheap
    reads, but ``runs``/``runs/<trace_id>``/``metrics`` serve the provenance
    log, so a leaked key must not be able to scrape it at line speed.
    ``ScopedActorRateThrottle`` buckets per ``ApiToken.key_hash`` (then per
    user, then per IP), so one abusive key cannot starve anyone else — which
    is why this is a quota rather than a second auth check.
    """

    permission_classes = [RequireAgent]
    throttle_classes = [ScopedActorRateThrottle]
    throttle_scope = "audit"


class AgentListView(_Base):
    def get(self, request, *args, **kwargs):
        registry = _ensure_registry()
        agents = [
            {"name": name, "module": cls.__module__}
            for name, cls in sorted(registry.items())
        ]
        return Response({"agents": agents, "count": len(agents)})


class AgentRunsView(_Base):
    def get(self, request, *args, **kwargs):
        limit = _parse_int_strict(
            request.query_params.get("limit"), default=50, lo=1, hi=200
        )
        runs = audit_store.tail(limit)
        return Response({"runs": runs, "count": len(runs)})


class AgentRunDetailView(_Base):
    """Return all audit events sharing ``trace_id`` (parent + children).

    Used by the agent ops UI to drill into a single run and see every
    LLM call, graph query, and HTTP request emitted under one trace.
    """

    def get(self, request, trace_id: str, *args, **kwargs):
        events = audit_store.by_trace(trace_id)
        if not events:
            return Response({"trace_id": trace_id, "events": [], "count": 0})
        return Response({"trace_id": trace_id, "events": events, "count": len(events)})


class AgentMetricsView(_Base):
    """Aggregate per-agent metrics from the last N audit events."""

    def get(self, request, *args, **kwargs):
        limit = _parse_int_strict(
            request.query_params.get("limit"), default=500, lo=10, hi=5000
        )
        events = audit_store.tail(limit)
        per_agent: dict[str, dict[str, Any]] = {}
        errors_total = 0
        for ev in events:
            if ev.get("type") != "agent_call":
                continue
            name = str(ev.get("agent") or "unknown")
            entry = per_agent.setdefault(
                name,
                {
                    "agent": name,
                    "count": 0,
                    "error_count": 0,
                    "latencies": [],
                    "confidences": [],
                    "last_seen": None,
                    "last_trace_id": None,
                    "last_model": None,
                },
            )
            entry["count"] += 1
            inp = ev.get("input") or {}
            if isinstance(inp, dict) and inp.get("error"):
                entry["error_count"] += 1
                errors_total += 1
            lat = ev.get("latency_ms")
            if isinstance(lat, (int, float)) and lat >= 0:
                entry["latencies"].append(float(lat))
            conf = ev.get("confidence")
            if isinstance(conf, (int, float)):
                entry["confidences"].append(float(conf))
            ts = ev.get("timestamp")
            if ts and (entry["last_seen"] is None or str(ts) > str(entry["last_seen"])):
                entry["last_seen"] = ts
                entry["last_trace_id"] = ev.get("trace_id")
                entry["last_model"] = ev.get("model")

        def _percentile(values: list[float], pct: float) -> float | None:
            if not values:
                return None
            ordered = sorted(values)
            idx = max(0, min(len(ordered) - 1, round(pct * (len(ordered) - 1))))
            return round(ordered[idx], 2)

        out = []
        for entry in per_agent.values():
            lats = entry.pop("latencies")
            confs = entry.pop("confidences")
            entry["latency_p50_ms"] = _percentile(lats, 0.5)
            entry["latency_p95_ms"] = _percentile(lats, 0.95)
            entry["avg_confidence"] = (
                round(sum(confs) / len(confs), 3) if confs else None
            )
            entry["success_rate"] = (
                round((entry["count"] - entry["error_count"]) / entry["count"], 3)
                if entry["count"]
                else None
            )
            out.append(entry)
        out.sort(key=lambda x: x["count"], reverse=True)
        return Response(
            {
                "agents": out,
                "window_size": len(events),
                "errors_total": errors_total,
            }
        )


class AgentBacklogView(_Base):
    def get(self, request, *args, **kwargs):
        backlog_path = _repo_root() / "BACKLOG.md"
        if not backlog_path.is_file():
            return Response(
                {
                    "counts": {"open": 0, "claimed": 0, "done": 0, "total": 0},
                    "open": [],
                    "claimed": [],
                    "done": [],
                }
            )
        return Response(_parse_backlog(backlog_path.read_text(encoding="utf-8")))


class AgentSpecsView(_Base):
    def get(self, request, *args, **kwargs):
        specs_dir = _repo_root() / "specs"
        if not specs_dir.is_dir():
            return Response({"specs": [], "count": 0})
        out: list[dict[str, str]] = []
        for entry in sorted(specs_dir.iterdir()):
            if not entry.is_dir() or entry.name == "_template":
                continue
            spec_md = entry / "spec.md"
            if not spec_md.is_file():
                continue
            out.append(
                {
                    "id": entry.name,
                    "status": _parse_spec_status(spec_md.read_text(encoding="utf-8")),
                }
            )
        return Response({"specs": out, "count": len(out)})


#: Where ``TestSynthesizer`` writes its proposals. Fixed, never a request
#: parameter: this view lists a directory, and a caller-supplied path would
#: turn that into an arbitrary-file-listing primitive.
_PROPOSED_TESTS_DIR = ("backend", "tests", "autonomy", "proposed")
_PROPOSED_SUFFIX = "__autonomy.proposed.py"


class AgentProposedTestsView(_Base):
    """Tests the autonomy loop has drafted and no human has ruled on yet.

    Read-only by constitution I1/I5: proposed files are skip-decorated and
    never run in CI, and nothing here promotes, un-skips, edits or deletes
    one. Reviewers move a proposal by hand, in a PR.
    """

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        directory = _repo_root().joinpath(*_PROPOSED_TESTS_DIR)
        if not directory.is_dir():
            return Response({"count": 0, "files": [], "available": False})

        files: list[dict[str, Any]] = []
        for entry in sorted(directory.glob("*.proposed.py")):
            if not entry.is_file():
                continue
            try:
                text = entry.read_text(encoding="utf-8", errors="replace")
                stat = entry.stat()
            except OSError:  # pragma: no cover - unreadable file on disk
                continue
            name = entry.name
            # TestSynthesizer names files `<module with dots as underscores>`
            # + the suffix, and that mapping is lossy (`law_ai.eval` and
            # `law.ai.eval` collide), so the stem is reported as-is rather
            # than guessed back into a dotted path.
            module = (
                name[: -len(_PROPOSED_SUFFIX)]
                if name.endswith(_PROPOSED_SUFFIX)
                else entry.stem
            )
            files.append(
                {
                    "name": name,
                    # Repo-relative: the absolute container path ("/repo/…")
                    # means nothing to a reviewer reading it on their laptop.
                    "path": "/".join((*_PROPOSED_TESTS_DIR, name)),
                    "module": module,
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                    "skip_marked": "autonomy-proposed" in text,
                }
            )
        files.sort(key=lambda f: f["mtime"], reverse=True)
        return Response({"count": len(files), "files": files, "available": True})


class LocalAIHealthView(_Base):
    def get(self, request, *args, **kwargs):
        async def _gather() -> dict[str, Any]:
            import asyncio as _asyncio

            ollama, checkpointer, phoenix, claude, chain = await _asyncio.gather(
                _probe_ollama(),
                _probe_checkpointer(),
                _probe_phoenix(),
                _probe_claude_code(),
                _probe_llm_chain(),
            )
            return {
                "ollama": ollama,
                "checkpointer": checkpointer,
                "phoenix": phoenix,
                "claude_code": claude,
                "llm_chain": chain,
            }

        return Response(async_to_sync(_gather)())


urlpatterns = [
    path("", AgentListView.as_view(), name="agents-list"),
    path("runs", AgentRunsView.as_view(), name="agents-runs"),
    path("runs/<str:trace_id>", AgentRunDetailView.as_view(), name="agents-run-detail"),
    path("metrics", AgentMetricsView.as_view(), name="agents-metrics"),
    path("backlog", AgentBacklogView.as_view(), name="agents-backlog"),
    path("specs", AgentSpecsView.as_view(), name="agents-specs"),
    path("health/local-ai", LocalAIHealthView.as_view(), name="agents-local-ai-health"),
    # BL-20260511-17: what the autonomy loop has drafted and is waiting on a
    # human for.
    path(
        "proposed-tests",
        AgentProposedTestsView.as_view(),
        name="agents-proposed-tests",
    ),
]

# BL-20260511-03: the read-only autonomy dashboard panels live in their own
# module (this one is already long) and are appended here so they share the
# /api/agents prefix and the RequireAgent gate. `autonomy_views` imports
# nothing from this module, so the dependency is one-way.
from law_ai.agentsapi.autonomy_views import (  # noqa: E402
    urlpatterns as _autonomy_urlpatterns,
)

urlpatterns += _autonomy_urlpatterns
