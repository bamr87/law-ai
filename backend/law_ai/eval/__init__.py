"""Law AI LegalBench evaluation harness (spec 018 T-002).

Provides the eval package public API:

    from law_ai.eval import run_eval, LegalBenchConfig

CLI equivalent (via ``python -m law_ai.eval.legalbench``):

    python -m law_ai.eval.legalbench \\
        --subset core_reasoning,precedent_retrieval \\
        --limit 20 \\
        --report backend/var/legalbench/report.json
"""

from __future__ import annotations

from .legalbench import LegalBenchConfig, run_eval

__all__ = [
    "LegalBenchConfig",
    "run_eval",
]
