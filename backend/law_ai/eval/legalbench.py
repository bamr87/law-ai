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
from law_ai.eval.loaders import is_synthetic, load_task
from law_ai.eval.paths import BASELINE_PATH, CACHE_ROOT
from law_ai.eval.report import write_report
from law_ai.eval.scoring import score_response

logger = logging.getLogger("law_ai.eval.legalbench")

#: Constitution §3: a listed subset may not regress more than 1 pp.
REGRESSION_TOLERANCE_PP = 1.0


class EvalInfrastructureError(RuntimeError):
    """The eval could not run — as distinct from the model scoring badly.

    Before this existed, an unreachable Ollama produced an empty response
    per item, every item scored *incorrect*, and the run reported a
    cheerful ``accuracy=0.0`` (BL-20260810-04). That is indistinguishable
    from a catastrophic model regression, which is exactly the signal a
    regression gate must not confuse.
    """


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
            CACHE_ROOT.mkdir(parents=True, exist_ok=True)
            self.report_path = CACHE_ROOT / f"{timestamp}.json"


def _call_ollama(prompt: str, *, model: str, base_url: str, timeout: int = 120) -> str:
    """Send a generate request to the local Ollama HTTP API.

    **Deliberately not routed through the provider chain** (spec 034). The
    harness measures one named model against a fixed benchmark, so a silent
    fallback to a different provider would silently change what is being
    measured and make scores non-comparable across runs — the 1 pp regression
    policy would then be enforcing noise. Point this at a different model by
    configuration, never by letting the chain choose.

    Deliberately avoids importing ``langchain_ollama`` so the eval harness
    works even when the ``local-ai`` extras aren't installed.

    Decoding is pinned to ``temperature=0`` with a fixed seed: a 1 pp
    regression policy is not meaningful against nondeterministic sampling.
    """
    import urllib.error
    import urllib.request

    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "seed": 0},
        }
    ).encode()
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
        errored = 0
        subset_results: list[dict[str, Any]] = []
        for item in items:
            item_id = item.get("index", str(uuid.uuid4()))
            prompt = item.get("text", "")
            expected = str(item.get("answer", ""))

            t0 = time.perf_counter()
            error: str | None = None
            try:
                response = _call_ollama(
                    prompt,
                    model=config.model,
                    base_url=base_url,
                )
            except RuntimeError as exc:
                logger.warning("ollama error item=%s: %s", item_id, exc)
                response = ""
                error = str(exc)[:300]
                errored += 1

            latency_ms = (time.perf_counter() - t0) * 1000
            # An item that never reached the model is NOT a wrong answer: it
            # is excluded from the accuracy denominator below.
            is_correct = False
            norm_response = ""
            if error is None:
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
            if error is not None:
                item_result["error"] = error
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
        scored = n - errored
        if n and errored == n:
            raise EvalInfrastructureError(
                f"every item in subset {subset!r} failed to reach the model "
                f"({errored}/{n}). This is an infrastructure failure, not a "
                "score of 0.0 — check that Ollama is running and the model "
                f"{config.model!r} is pulled (make local-ai-up)."
            )
        # Denominator is items that actually ran, so partial infra failure
        # degrades coverage rather than silently deflating accuracy.
        accuracy = round(correct / scored, 4) if scored else 0.0
        results.append(
            {
                "subset": subset,
                "n": n,
                "scored": scored,
                "errored": errored,
                "correct": correct,
                "accuracy": accuracy,
                "synthetic": is_synthetic(subset),
                "items": subset_results,
            }
        )
        logger.info(
            "subset=%s accuracy=%.4f (%d/%d scored, %d errored)",
            subset,
            accuracy,
            correct,
            scored,
            errored,
        )

    report = write_report(results, config=config)
    return report


def check_regression(
    report: dict[str, Any], *, tolerance_pp: float = REGRESSION_TOLERANCE_PP
) -> list[str]:
    """Return human-readable regression messages (empty when clean).

    Compares each subset against ``baseline.json`` (constitution §3: no
    listed subset may drop more than 1 pp).
    """
    problems: list[str] = []
    delta = report.get("delta") or {}
    for subset, row in delta.items():
        drop_pp = -float(row.get("delta_pp", 0.0))
        if drop_pp > tolerance_pp:
            problems.append(
                f"{subset}: {row['before']:.4f} → {row['after']:.4f} "
                f"({row['delta_pp']:+.2f} pp, tolerance {tolerance_pp} pp)"
            )
    return problems


def update_baseline(report: dict[str, Any]) -> Path:
    """Write the run's per-subset accuracies to ``baseline.json``.

    Refuses to baseline a synthetic run: a baseline derived from smoke-test
    fixtures would make every later regression check meaningless.
    """
    rows = report.get("subsets", [])
    synthetic = [r["subset"] for r in rows if r.get("synthetic")]
    if synthetic:
        raise EvalInfrastructureError(
            "refusing to write a baseline from synthetic stub data for "
            f"{synthetic}: cache real LegalBench items first "
            f"({CACHE_ROOT}/<subset>/items.jsonl)."
        )
    payload = {
        "model": report.get("model"),
        "timestamp": report.get("timestamp"),
        "run_id": report.get("run_id"),
        "accuracies": {r["subset"]: r["accuracy"] for r in rows},
    }
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("baseline updated: %s", BASELINE_PATH)
    return BASELINE_PATH


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
        help="Output JSON path (default: <backend>/var/legalbench/<UTC>.json).",
    )
    parser.add_argument(
        "--check-regression",
        action="store_true",
        help=(
            "Exit non-zero when any subset drops more than "
            f"{REGRESSION_TOLERANCE_PP} pp against baseline.json "
            "(constitution §3). Use this in CI."
        ),
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write this run's accuracies to baseline.json (rejects stub runs).",
    )
    parser.add_argument(
        "--fail-on-synthetic",
        action="store_true",
        help=(
            "Exit non-zero when any subset fell back to synthetic stubs — "
            "guards CI against 'measuring' fixtures."
        ),
    )
    return parser


def _print_summary(report: dict[str, Any], config: LegalBenchConfig) -> None:
    """Human-readable run summary, with stub/error status made obvious."""
    print(f"run_id: {report['run_id']}")
    for row in report.get("subsets", []):
        flags = []
        if row.get("synthetic"):
            flags.append("SYNTHETIC-STUBS")
        if row.get("errored"):
            flags.append(f"{row['errored']} errored")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        print(
            f"  {row['subset']}: accuracy={row['accuracy']:.4f} "
            f"({row['correct']}/{row.get('scored', row['n'])}){suffix}"
        )
    print(f"report: {config.report_path}")

    if report.get("synthetic"):
        print(
            "WARNING: at least one subset used synthetic stub fixtures. "
            "These accuracies are NOT a LegalBench measurement.",
            file=sys.stderr,
        )


def _apply_gates(report: dict[str, Any], args: argparse.Namespace) -> int:
    """Apply the opt-in CI gates; return the process exit code."""
    exit_code = 0

    if args.fail_on_synthetic and report.get("synthetic"):
        print("FAIL: run used synthetic stubs (--fail-on-synthetic)", file=sys.stderr)
        exit_code = 1

    if args.update_baseline:
        try:
            print(f"baseline: {update_baseline(report)}")
        except EvalInfrastructureError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            exit_code = 1

    if args.check_regression:
        problems = check_regression(report)
        if problems:
            for line in problems:
                print(f"REGRESSION: {line}", file=sys.stderr)
            exit_code = 1
        elif not report.get("delta"):
            print(
                "note: no baseline.json to compare against — run with "
                "--update-baseline once a real dataset is cached.",
                file=sys.stderr,
            )

    return exit_code


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
    except EvalInfrastructureError as exc:
        # Exit 2 (not 1): "the eval could not run" is a different failure
        # from "the model regressed", and CI should treat it differently.
        print(f"INFRASTRUCTURE ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    _print_summary(report, config)
    exit_code = _apply_gates(report, args)
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main(sys.argv[1:])
