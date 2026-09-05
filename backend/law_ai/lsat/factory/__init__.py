"""LSAT Content Factory — scalable, HITL-gated question-bank growth (spec 024).

Public facade. Typical flows::

    from law_ai.lsat.factory import plan, compile_plan, status
    targets = plan()                       # what should we build next?
    manifest, path = compile_plan()        # freeze prompts into an artifact

    # dev-time, tiered Claude generation (gated by core.claude_code):
    from law_ai.lsat.factory import ClaudeCodeExecutor, execute_manifest
    results = await execute_manifest(manifest, ClaudeCodeExecutor(cfg))

    # or fully external generation → drafts JSONL → intake:
    from law_ai.lsat.factory import ingest_drafts_file
    results = await ingest_drafts_file(manifest, Path("drafts.jsonl"))

Everything lands as *pending proposals* in the spec-019 HITL store; nothing
this package does can write the live bank (constitution §5).
"""

from law_ai.lsat.factory.blueprints import CompiledPrompt, compile_prompt
from law_ai.lsat.factory.config import (
    DEFAULT_CLAUDE_TIER_MODELS,
    FactoryConfig,
    ModelTier,
    route_tier,
)
from law_ai.lsat.factory.coverage import (
    CoverageCell,
    GenerationTarget,
    coverage_matrix,
    plan_targets,
)
from law_ai.lsat.factory.executors import (
    ClaudeCodeExecutor,
    DraftFileExecutor,
    ExecutionError,
    Executor,
    ExecutorUnavailable,
    OllamaExecutor,
    SynthExecutor,
    RawBatch,
    XaiExecutor,
)
from law_ai.lsat.factory.intake import (
    GateRejection,
    IngestResult,
    ingest_batch,
)
from law_ai.lsat.factory.manifest import (
    GenerationJob,
    GenerationManifest,
    build_manifest,
    read_manifest,
    write_manifest,
)
from law_ai.lsat.factory.pipeline import (
    compile_plan,
    execute_manifest,
    ingest_drafts_file,
    load_manifest,
    plan,
    status,
)
from law_ai.lsat.factory.taxonomy import (
    Archetype,
    all_archetypes,
    archetypes_for,
    get_archetype,
    validate_taxonomy,
)

__all__ = [
    "DEFAULT_CLAUDE_TIER_MODELS",
    "Archetype",
    "ClaudeCodeExecutor",
    "CompiledPrompt",
    "CoverageCell",
    "DraftFileExecutor",
    "ExecutionError",
    "Executor",
    "ExecutorUnavailable",
    "FactoryConfig",
    "GateRejection",
    "GenerationJob",
    "GenerationManifest",
    "GenerationTarget",
    "IngestResult",
    "ModelTier",
    "OllamaExecutor",
    "RawBatch",
    "SynthExecutor",
    "XaiExecutor",
    "all_archetypes",
    "archetypes_for",
    "build_manifest",
    "compile_plan",
    "compile_prompt",
    "coverage_matrix",
    "execute_manifest",
    "get_archetype",
    "ingest_batch",
    "ingest_drafts_file",
    "load_manifest",
    "plan",
    "plan_targets",
    "read_manifest",
    "route_tier",
    "status",
    "validate_taxonomy",
    "write_manifest",
]
