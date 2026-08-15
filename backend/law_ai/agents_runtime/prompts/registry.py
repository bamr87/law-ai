"""Local prompt-template registry (spec 036).

Enumerates every prompt file the project ships so tooling — chiefly the
Arize Phoenix sync in :mod:`law_ai.agents_runtime.prompts.phoenix` — can
treat them uniformly. Three families are discovered:

* ``runtime`` versioned: ``backend/law_ai/agents_runtime/prompts/<name>.v<N>.md``
* ``runtime`` unversioned: ``backend/law_ai/agents_runtime/prompts/legal_workflow/<node>.md``
  published as ``legal_workflow_<node>``
* ``sdlc``: the repo-root AO-SDLC prompt chain ``prompts/*.md`` published
  with an ``sdlc_`` prefix

The files remain the single source of truth; this module only *reads* them.
Consumers (crews/graphs) still load their own prompt files directly — the
registry is additive metadata, not a loading indirection.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["IDENTIFIER_RE", "LocalPrompt", "iter_local_prompts"]

# Phoenix prompt identifiers must match this grammar (its `Identifier` schema).
IDENTIFIER_RE = re.compile(r"^[a-z0-9]([_a-z0-9-]*[a-z0-9])?$")

_VERSIONED_FILE_RE = re.compile(r"^(?P<stem>.+)\.v(?P<version>\d+)\.md$")

_RUNTIME_DIR = Path(__file__).resolve().parent
_LEGAL_WORKFLOW_DIR = _RUNTIME_DIR / "legal_workflow"

# Env override for the AO-SDLC prompt dir (tests, unusual layouts).
_SDLC_DIR_ENV = "LAW_AI_SDLC_PROMPTS_DIR"


@dataclass(frozen=True)
class LocalPrompt:
    """One prompt template file, addressed the way Phoenix will see it."""

    name: str
    """Phoenix-safe identifier (matches :data:`IDENTIFIER_RE`)."""

    family: str
    """``runtime`` or ``sdlc``."""

    path: Path
    version: int | None = None
    """File-encoded version (``.v<N>.md``); ``None`` for unversioned files."""

    @property
    def tag(self) -> str | None:
        """Phoenix version tag (``v<N>``) for versioned prompts."""
        return f"v{self.version}" if self.version is not None else None

    @property
    def text(self) -> str:
        return self.path.read_text(encoding="utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def description(self) -> str:
        rel = _describe_path(self.path)
        return f"Law AI {self.family} prompt (synced from {rel})"


def _describe_path(path: Path) -> str:
    """Repo-relative-ish path for descriptions; falls back to the basename."""
    parts = path.parts
    for anchor in ("law_ai", "prompts"):
        if anchor in parts:
            return "/".join(parts[parts.index(anchor) :])
    return path.name


def _sanitize(stem: str) -> str:
    """Map an arbitrary file stem onto Phoenix's identifier grammar."""
    name = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    if not IDENTIFIER_RE.match(name):
        raise ValueError(f"cannot derive a Phoenix identifier from {stem!r}")
    return name


def _sdlc_dir() -> Path | None:
    override = os.environ.get(_SDLC_DIR_ENV)
    if override:
        p = Path(override)
        return p if p.is_dir() else None
    # In-container the repo root is mounted at /repo (docker-compose.yml);
    # on the host walk up from this file (backend/law_ai/agents_runtime/prompts).
    for candidate in (Path("/repo/prompts"), _RUNTIME_DIR.parents[3] / "prompts"):
        if candidate.is_dir():
            return candidate
    return None


def _runtime_prompts() -> list[LocalPrompt]:
    prompts: list[LocalPrompt] = []
    for path in sorted(_RUNTIME_DIR.glob("*.md")):
        match = _VERSIONED_FILE_RE.match(path.name)
        if not match:
            continue  # stray unversioned .md at the top level: not a template
        prompts.append(
            LocalPrompt(
                name=_sanitize(match.group("stem")),
                family="runtime",
                path=path,
                version=int(match.group("version")),
            )
        )
    if _LEGAL_WORKFLOW_DIR.is_dir():
        for path in sorted(_LEGAL_WORKFLOW_DIR.glob("*.md")):
            prompts.append(
                LocalPrompt(
                    name=_sanitize(f"legal_workflow_{path.stem}"),
                    family="runtime",
                    path=path,
                )
            )
    return prompts


def _sdlc_prompts() -> list[LocalPrompt]:
    sdlc_dir = _sdlc_dir()
    if sdlc_dir is None:
        return []
    return [
        LocalPrompt(
            name=_sanitize(f"sdlc_{path.stem}"),
            family="sdlc",
            path=path,
        )
        for path in sorted(sdlc_dir.glob("*.md"))
    ]


def iter_local_prompts() -> list[LocalPrompt]:
    """Every prompt template in the repo, ordered (family, name, version)."""
    prompts = _runtime_prompts() + _sdlc_prompts()
    return sorted(prompts, key=lambda p: (p.family, p.name, p.version or 0))
