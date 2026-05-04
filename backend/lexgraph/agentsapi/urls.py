"""Agent operations endpoints (spec 003 → spec 011 FR-9 port).

DRF 3.17 lacks native async views, so each public method stays sync and
delegates to ``async_to_sync(...)`` for any I/O. The function-level
helpers (`_probe_ollama`, `_probe_checkpointer`, `_probe_phoenix`) are
deliberately exposed at module scope so existing tests that monkeypatch
them keep working.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from asgiref.sync import async_to_sync
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView

from lexgraph.agents_runtime.registry import AGENT_REGISTRY, register_all_agents
from lexgraph.core import audit_jsonl as audit_store
from lexgraph.core.auth import RequireAgent
from lexgraph.core.provenance import provenance  # re-export for tests

_BACKLOG_BULLET_RE = re.compile(
    r"^- \*\*(?P<id>BL-\d{8}-\d{2})\*\* — \*(?P<kind>[a-z-]+),\s*(?P<sev>low|med|high)\* — (?P<title>.+)$"
)
_SECTION_RE = re.compile(r"^## (Open|Claimed|Done)\s*$")
_SPEC_STATUS_RE = re.compile(r"^- \*\*Status\*\*:\s*(?P<status>.+)$", re.MULTILINE)

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKLOG_PATH = REPO_ROOT / "BACKLOG.md"
SPECS_DIR = REPO_ROOT / "specs"


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

    from lexgraph.agents_runtime.graphs.runtime import (
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
    permission_classes = [RequireAgent]


class AgentListView(_Base):
    def get(self, request, *args, **kwargs):  # noqa: ANN001
        registry = _ensure_registry()
        agents = [
            {"name": name, "module": cls.__module__}
            for name, cls in sorted(registry.items())
        ]
        return Response({"agents": agents, "count": len(agents)})


class AgentRunsView(_Base):
    def get(self, request, *args, **kwargs):  # noqa: ANN001
        limit = _parse_int_strict(
            request.query_params.get("limit"), default=50, lo=1, hi=200
        )
        runs = audit_store.tail(limit)
        return Response({"runs": runs, "count": len(runs)})


class AgentBacklogView(_Base):
    def get(self, request, *args, **kwargs):  # noqa: ANN001
        if not BACKLOG_PATH.is_file():
            return Response(
                {
                    "counts": {"open": 0, "claimed": 0, "done": 0, "total": 0},
                    "open": [],
                    "claimed": [],
                    "done": [],
                }
            )
        return Response(_parse_backlog(BACKLOG_PATH.read_text(encoding="utf-8")))


class AgentSpecsView(_Base):
    def get(self, request, *args, **kwargs):  # noqa: ANN001
        if not SPECS_DIR.is_dir():
            return Response({"specs": [], "count": 0})
        out: list[dict[str, str]] = []
        for entry in sorted(SPECS_DIR.iterdir()):
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


class LocalAIHealthView(_Base):
    def get(self, request, *args, **kwargs):  # noqa: ANN001
        async def _gather() -> dict[str, Any]:
            import asyncio as _asyncio

            ollama, checkpointer, phoenix = await _asyncio.gather(
                _probe_ollama(), _probe_checkpointer(), _probe_phoenix()
            )
            return {"ollama": ollama, "checkpointer": checkpointer, "phoenix": phoenix}

        return Response(async_to_sync(_gather)())


urlpatterns = [
    path("", AgentListView.as_view(), name="agents-list"),
    path("runs", AgentRunsView.as_view(), name="agents-runs"),
    path("backlog", AgentBacklogView.as_view(), name="agents-backlog"),
    path("specs", AgentSpecsView.as_view(), name="agents-specs"),
    path("health/local-ai", LocalAIHealthView.as_view(), name="agents-local-ai-health"),
]
