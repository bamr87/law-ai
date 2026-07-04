"""Factory configuration — model tiers, quality thresholds, output locations.

Spec 024 FR-2. Everything an operator may want to tune lives here as one
Pydantic model with ``LSAT_FACTORY_*`` settings overrides, so scaling knobs
(batch size, dedup threshold, tier→model routing) are configuration — not
code changes.

Constitution note (§1): the Claude tier map is a **dev-time** concern consumed
only by :class:`~lawgraph.lsat.factory.executors.ClaudeCodeExecutor`, which is
inert outside a development environment. The product runtime path maps every
tier to the local Ollama default model.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from lawgraph.core.settings_proxy import settings_proxy as settings
from lawgraph.lsat.services.bank import Difficulty

logger = logging.getLogger("lawgraph.lsat.factory.config")

# Generation cost/capability tiers. Difficulty (or an archetype hint) routes a
# job to a tier; each executor then maps the tier onto a concrete model:
#   bulk      — high-volume, low-complexity items (easy difficulty)
#   standard  — typical items (med difficulty)
#   premium   — hard items + net-new passage/game authoring
#   judge     — adversarial review / scoring of drafted items
ModelTier = Literal["bulk", "standard", "premium", "judge"]

MODEL_TIERS: tuple[ModelTier, ...] = ("bulk", "standard", "premium", "judge")

# Dev-time Claude tier defaults (spec 024 FR-2). Overridable per deployment via
# LSAT_FACTORY_CLAUDE_TIERS (JSON object tier→model-id) without a code change.
DEFAULT_CLAUDE_TIER_MODELS: dict[ModelTier, str] = {
    "bulk": "claude-haiku-4-5-20251001",
    "standard": "claude-sonnet-5",
    "premium": "claude-opus-4-8",
    "judge": "claude-fable-5",
}

# Matches the LSAT_FACTORY_DIR settings default: relative to the process cwd
# (/app inside Docker = ./backend on host), so a directly-constructed
# FactoryConfig() and FactoryConfig.from_settings() resolve identically.
_DEFAULT_OUTPUT_DIR = Path("var/lsat_factory")

_DIFFICULTY_TIER: dict[Difficulty, ModelTier] = {
    "easy": "bulk",
    "med": "standard",
    "hard": "premium",
}


def route_tier(difficulty: Difficulty, hint: ModelTier | None = None) -> ModelTier:
    """Pick the generation tier for a job: archetype hint wins, else difficulty."""
    return hint if hint is not None else _DIFFICULTY_TIER[difficulty]


class FactoryConfig(BaseModel):
    """Tunable parameters for one factory run (snapshotted into each manifest)."""

    target_per_cell: int = Field(
        default=2,
        ge=1,
        description="Desired bank items per (archetype x difficulty) cell; "
        "cells below this are generation targets.",
    )
    max_jobs: int = Field(
        default=12, ge=1, description="Cap on jobs compiled into one manifest."
    )
    drafts_per_job: int = Field(
        default=3, ge=1, le=10, description="Drafts requested per job."
    )
    exemplar_count: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Max same-archetype bank exemplars embedded per prompt.",
    )
    dedup_threshold: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        description="Token-Jaccard stem similarity at/above which a draft is "
        "rejected as a near-duplicate.",
    )
    balance_tolerance: float = Field(
        default=0.40,
        gt=0.0,
        le=1.0,
        description="Max share of one answer key within an ingested batch "
        "before the batch is flagged for key skew.",
    )
    gap_boost: float = Field(
        default=2.0,
        ge=1.0,
        description="Priority multiplier for cells whose concepts show up in "
        "learner gap analysis (weak accuracy).",
    )
    claude_tier_models: dict[ModelTier, str] = Field(
        default_factory=lambda: dict(DEFAULT_CLAUDE_TIER_MODELS),
        description="Dev-time Claude model id per tier (executor-enforced "
        "dev-only; see constitution §1).",
    )
    output_dir: Path = Field(
        default=_DEFAULT_OUTPUT_DIR,
        description="Root for manifests/ and drafts/ artifacts.",
    )

    @field_validator("claude_tier_models")
    @classmethod
    def _all_tiers_mapped(cls, v: dict[ModelTier, str]) -> dict[ModelTier, str]:
        missing = [t for t in MODEL_TIERS if t not in v]
        if missing:
            raise ValueError(f"claude_tier_models missing tiers: {missing}")
        return v

    def resolved_output_dir(self) -> Path:
        """Absolute artifacts root (mirrors the proposals-dir cwd convention)."""
        path = self.output_dir
        if not path.is_absolute():
            path = Path.cwd() / path
        return path

    @classmethod
    def from_settings(cls) -> FactoryConfig:
        """Build a config from ``LSAT_FACTORY_*`` settings with safe defaults.

        A malformed ``LSAT_FACTORY_CLAUDE_TIERS`` JSON payload logs a warning
        and falls back to the defaults rather than failing the run.
        """
        tier_models: dict[ModelTier, str] = dict(DEFAULT_CLAUDE_TIER_MODELS)
        raw_tiers = getattr(settings, "LSAT_FACTORY_CLAUDE_TIERS", "") or ""
        if raw_tiers:
            try:
                parsed = json.loads(raw_tiers)
                if not isinstance(parsed, dict):
                    raise TypeError("expected a JSON object of tier→model")
                for tier in MODEL_TIERS:
                    if tier in parsed:
                        tier_models[tier] = str(parsed[tier])
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning(
                    "ignoring malformed LSAT_FACTORY_CLAUDE_TIERS (%s); "
                    "using defaults",
                    exc,
                )

        return cls(
            target_per_cell=int(getattr(settings, "LSAT_FACTORY_TARGET_PER_CELL", 2)),
            max_jobs=int(getattr(settings, "LSAT_FACTORY_MAX_JOBS", 12)),
            drafts_per_job=int(getattr(settings, "LSAT_FACTORY_DRAFTS_PER_JOB", 3)),
            exemplar_count=int(getattr(settings, "LSAT_FACTORY_EXEMPLARS", 2)),
            dedup_threshold=float(
                getattr(settings, "LSAT_FACTORY_DEDUP_THRESHOLD", 0.60)
            ),
            balance_tolerance=float(
                getattr(settings, "LSAT_FACTORY_BALANCE_TOLERANCE", 0.40)
            ),
            gap_boost=float(getattr(settings, "LSAT_FACTORY_GAP_BOOST", 2.0)),
            claude_tier_models=tier_models,
            output_dir=Path(
                getattr(settings, "LSAT_FACTORY_DIR", "") or _DEFAULT_OUTPUT_DIR
            ),
        )
