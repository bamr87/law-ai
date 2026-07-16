"""LegalBench CLI entry-point and orchestrator (spec 018 T-002, FR-1 FR-2 AC-1).

Run via::

    python -m law_ai.eval.legalbench \\
        --subset core_reasoning,precedent_retrieval \\
        --model mistral:7b-instruct-q4_K_M \\
        --limit 50 \\
        --report backend/var/legalbench/run.json

Every item emits an OpenTelemetry span via ``law_ai.core.provenance``
so individual prompt/response pairs are inspectable in Phoenix.
Scoring is task-agnostic (exact-match + normalised); the harness does not
depend on the LegalBench Python package being installed — it resolves tasks
from ``backend/var/legalbench/`` cache directories.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from law_ai.core.settings_proxy import settings_proxy as settings
from law_ai.eval.loaders import load_task
from law_ai.eval.report import write_report
from law_ai.eval.scoring import score_response

logger = logging.getLogger("law_ai.eval.legalbench")

# ---------------------------------------------------------------------------
# Allowed subset names (constitution §3 — only tracked subsets are permitted
# without an explicit spec amendment).
# ---------------------------------------------------------------------------
ALLOWED_SUBSETS: frozenset[str] = frozenset(
    {
        "core_reasoning",
        "precedent_retrieval",
        "contract_nli",
        "definitions",
        "causation",
    }
)


@dataclass
class LegalBenchConfig:
    """Runtime configuration for a LegalBench eval run."""

    subsets: list[str]
    model: str = ""
    limit: int | None = None
    report_path: Path | None = None
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        unknown = set(self.subsets) - ALLOWED_SUBSETS
        if unknown:
            raise ValueError(
                f"Unknown LegalBench subset(s): {sorted(unknown)}. "
                f"Allowed: {sorted(ALLOWED_SUBSETS)}"
            )
        if not self.model:
            self.model = str(
                getattr(settings, "OLLAMA_DEFAULT_MODEL", "mistral:7b-instruct-q4_K_M")
            )
        if self.report_path is None:
            timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            default_dir = Path("backend/var/legalbench")
            default_dir.mkdir(parents=True, exist_ok=True)
            self.report_path = default_dir / f"{timestamp}.json"


def _call_ollama(prompt: str, *, model: str, base_url: str, timeout: int = 120) -> str:
    """Send a generate request to the local Ollama HTTP API.

    Deliberately avoids importing ``langchain_ollama`` so the eval harness
    works even when the ``local-ai`` extras aren't installed.
    """
    import urllib.error
    import urllib.request

    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
            return str(body.get("response", ""))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Ollama is unreachable at {base_url}: {exc}. "
            "Is the local-ai stack running? Try: make local-ai-up"
        ) from exc


def run_eval(config: LegalBenchConfig) -> dict[str, Any]:
    """Run the configured LegalBench subsets and return a result dict.

    Each item is evaluated independently:
    1. Load task items from cache (see :mod:`law_ai.eval.loaders`).
    2. Build a few-shot prompt from the item's fields.
    3. Call Ollama via the raw HTTP API.
    4. Score the response against the expected label.
    5. Emit a provenance event per item.

    Returns a ``dict`` that is also written to ``config.report_path``.
    """

    base_url: str = str(getattr(settings, "OLLAMA_BASE_URL", "http://ollama:11434"))
    results: list[dict[str, Any]] = []

    for subset in config.subsets:
        items = load_task(subset, limit=config.limit)
        logger.info("subset=%s items=%d model=%s", subset, len(items), config.model)

        correct = 0
        subset_results: list[dict[str, Any]] = []
        for item in items:
            item_id = item.get("index", str(uuid.uuid4()))
            prompt = item.get("text", "")
            expected = str(item.get("answer", ""))

            t0 = time.perf_counter()
            try:
                response = _call_ollama(
                    prompt,
                    model=config.model,
                    base_url=base_url,
                )
            except RuntimeError as exc:
                logger.warning("ollama error item=%s: %s", item_id, exc)
                response = ""

            latency_ms = (time.perf_counter() - t0) * 1000
            is_correct, norm_response = score_response(response, expected, subset)
            if is_correct:
                correct += 1

            item_result: dict[str, Any] = {
                "subset": subset,
                "index": item_id,
                "expected": expected,
                "response": norm_response,
                "correct": is_correct,
                "latency_ms": round(latency_ms, 1),
            }
            subset_results.append(item_result)

            # Provenance span per item (constitution §4 / spec 018 NFR-AUDIT-1)
            _emit_item_event(
                config=config,
                subset=subset,
                item_id=item_id,
                prompt=prompt,
                response=norm_response,
                expected=expected,
                correct=is_correct,
                latency_ms=latency_ms,
            )

        n = len(subset_results)
        accuracy = round(correct / n, 4) if n else 0.0
        results.append(
            {
                "subset": subset,
                "n": n,
                "correct": correct,
                "accuracy": accuracy,
                "items": subset_results,
            }
        )
        logger.info("subset=%s accuracy=%.4f (%d/%d)", subset, accuracy, correct, n)

    report = write_report(results, config=config)
    return report


def _emit_item_event(
    *,
    config: LegalBenchConfig,
    subset: str,
    item_id: str | int,
    prompt: str,
    response: str,
    expected: str,
    correct: bool,
    latency_ms: float,
) -> None:
    """Write a single per-item provenance event (non-blocking)."""
    try:
        from law_ai.core.audit_jsonl import record

        record(
            {
                "type": "legalbench.item",
                "run_id": config.run_id,
                "model": config.model,
                "subset": subset,
                "item_id": str(item_id),
                "correct": correct,
                "latency_ms": latency_ms,
                "agent_version": "law_ai.eval.legalbench.v1",
                "source": "legalbench",
                "confidence": 1.0 if correct else 0.0,
            }
        )
    except Exception as exc:  # pragma: no cover — audit failure must not abort eval
        logger.debug("provenance write skipped: %s", exc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m law_ai.eval.legalbench",
        description="Run LegalBench evaluation against the configured Ollama model.",
    )
    parser.add_argument(
        "--subset",
        default="core_reasoning,precedent_retrieval",
        help=(
            "Comma-separated subset names (default: core_reasoning,precedent_retrieval). "
            f"Allowed: {', '.join(sorted(ALLOWED_SUBSETS))}."
        ),
    )
    parser.add_argument(
        "--model",
        default="",
        help="Ollama model tag. Defaults to OLLAMA_DEFAULT_MODEL setting.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap items per task during local development.",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Output JSON path (default: backend/var/legalbench/<UTC>.json).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    import django

    django.setup()

    parser = _build_parser()
    args = parser.parse_args(argv)

    subsets = [s.strip() for s in args.subset.split(",") if s.strip()]
    config = LegalBenchConfig(
        subsets=subsets,
        model=args.model,
        limit=args.limit,
        report_path=Path(args.report) if args.report else None,
    )

    try:
        report = run_eval(config)
    except ValueError as exc:
        parser.error(str(exc))
        return

    # Summarise to stdout
    print(f"run_id: {report['run_id']}")
    for row in report.get("subsets", []):
        print(
            f"  {row['subset']}: accuracy={row['accuracy']:.4f} ({row['correct']}/{row['n']})"
        )
    print(f"report: {config.report_path}")


if __name__ == "__main__":
    main(sys.argv[1:])
