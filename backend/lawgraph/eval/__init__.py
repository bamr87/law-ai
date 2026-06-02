"""LawGraph LegalBench evaluation harness (spec 018 T-002/T-003).

Provides the eval package public API:

    from lawgraph.eval import run_eval, LegalBenchConfig
    from lawgraph.eval import CoverageRecord, load_coverage_report, overall_coverage

CLI equivalent (via ``python -m lawgraph.eval.legalbench``):

    python -m lawgraph.eval.legalbench \\
        --subset core_reasoning,precedent_retrieval \\
        --limit 20 \\
        --report backend/var/legalbench/report.json
"""

from __future__ import annotations

from .coverage_audit import CoverageRecord, load_coverage_report, overall_coverage
from .legalbench import LegalBenchConfig, run_eval

__all__ = [
    "CoverageRecord",
    "LegalBenchConfig",
    "load_coverage_report",
    "overall_coverage",
    "run_eval",
]
