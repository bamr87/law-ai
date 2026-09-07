"""``lsat_factory`` — drive the LSAT content factory lifecycle (spec 024 FR-8).

Subcommands::

    manage.py lsat_factory plan               # ranked generation targets
    manage.py lsat_factory compile            # plan → manifest artifact
    manage.py lsat_factory run --executor …   # fulfill a manifest + ingest
    manage.py lsat_factory ingest --drafts …  # external drafts → HITL queue
    manage.py lsat_factory export-manifest    # manifest → external-farm bundle
    manage.py lsat_factory status             # census / holes / queue depth

``run --judge`` adds an adversarial review of every accepted draft, attaching
the verdict to the proposal's meta before the HITL queue (BL-20260702-02).

``plan``, ``compile``, ``ingest``, and ``status`` are offline-safe (AC-1/AC-2).
``run`` needs a live provider for the model-backed executors: ``--executor
ollama`` (product default) or ``--executor claude_code`` (dev-time only;
refuses outside the OAuth gate). ``--executor synth`` needs none — it fulfills
a job from the spec 049 synthesis engine, whose keys are proved rather than
asserted, and whose drafts still pass every intake gate into the HITL queue.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError

from law_ai.lsat import factory
from law_ai.lsat.factory.executors import ExecutorUnavailable


class Command(BaseCommand):
    help = "LSAT content factory: plan / compile / run / ingest / status."

    def add_arguments(self, parser: Any) -> None:
        sub = parser.add_subparsers(dest="subcommand", required=True)

        p_plan = sub.add_parser("plan", help="rank generation targets")
        p_plan.add_argument("--json", action="store_true", dest="as_json")

        p_compile = sub.add_parser("compile", help="plan → manifest artifact")
        p_compile.add_argument("--json", action="store_true", dest="as_json")

        p_run = sub.add_parser("run", help="fulfill a manifest and ingest")
        p_run.add_argument(
            "--executor",
            choices=("ollama", "claude_code", "xai", "drafts", "synth"),
            default="ollama",
        )
        p_run.add_argument(
            "--synth-domain",
            default=None,
            help="Restrict the synth executor to one domain pack (default: all).",
        )
        p_run.add_argument("--manifest", default=None, help="path (default: latest)")
        p_run.add_argument(
            "--drafts", default=None, help="drafts JSONL (drafts executor)"
        )
        p_run.add_argument("--jobs", default=None, help="comma-separated job ids")
        p_run.add_argument(
            "--judge",
            action="store_true",
            default=None,
            dest="judge",
            help="adversarially review each accepted draft and attach the "
            "verdict to its proposal meta (doubles model calls)",
        )
        p_run.add_argument(
            "--guides",
            action="store_true",
            default=None,
            dest="guides",
            help="draft a solve guide beside each accepted item (default on)",
        )
        p_run.add_argument(
            "--no-guides",
            action="store_false",
            dest="guides",
            help="skip guide-at-authoring for this run (budget control)",
        )
        p_run.add_argument(
            "--no-judge",
            action="store_false",
            dest="judge",
            help="skip the judge tier even when LSAT_FACTORY_JUDGE is set",
        )
        p_run.add_argument("--json", action="store_true", dest="as_json")

        p_ingest = sub.add_parser("ingest", help="external drafts → HITL queue")
        p_ingest.add_argument("--drafts", required=True, help="drafts JSONL path")
        p_ingest.add_argument("--manifest", default=None, help="path (default: latest)")
        p_ingest.add_argument("--json", action="store_true", dest="as_json")

        p_export = sub.add_parser(
            "export-manifest",
            help="manifest → self-contained prompts-only bundle for an "
            "external generation farm",
        )
        p_export.add_argument("--manifest", default=None, help="path (default: latest)")
        p_export.add_argument(
            "--out",
            default=None,
            help="destination directory (default: <factory dir>/bundles)",
        )
        p_export.add_argument(
            "--zip", action="store_true", dest="as_zip", help="also archive the bundle"
        )
        p_export.add_argument("--json", action="store_true", dest="as_json")

        p_status = sub.add_parser("status", help="census / holes / queue depth")
        p_status.add_argument("--json", action="store_true", dest="as_json")

    # -- helpers -----------------------------------------------------------

    def _emit(self, data: Any, as_json: bool) -> None:
        if as_json:
            self.stdout.write(json.dumps(data, indent=2, default=str))

    def _manifest(self, opts: dict[str, Any]) -> factory.GenerationManifest:
        raw = opts.get("manifest")
        try:
            return factory.load_manifest(Path(raw) if raw else None)
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc

    def _report_results(
        self, results: list[factory.IngestResult], as_json: bool
    ) -> None:
        if as_json:
            self._emit([r.model_dump() for r in results], True)
            return
        total_ok = sum(len(r.accepted) for r in results)
        total_rej = sum(len(r.rejected) for r in results)
        for r in results:
            line = (
                f"  {r.job_id}: +{len(r.accepted)} proposal(s), "
                f"-{len(r.rejected)} rejected [{r.model_label}]"
            )
            if r.error:
                line += "  ✗ " + r.error
            if r.balance_flag:
                line += "  ⚠ " + r.balance_flag
            if r.pending_passage_path:
                line += f"  (new passage parked: {r.pending_passage_path})"
            if r.guides:
                line += f"  +{len(r.guides)} guide draft(s)"
            if r.judge:
                counts: dict[str, int] = {}
                for word in r.judge.values():
                    counts[word] = counts.get(word, 0) + 1
                line += "  judge: " + ", ".join(
                    f"{n} {word}" for word, n in sorted(counts.items())
                )
            self.stdout.write(line)
            for warning in r.warnings:
                self.stdout.write(f"      note: {warning}")
            for rej in r.rejected:
                self.stdout.write(
                    f"      reject #{rej.draft_index} [{rej.reason}] {rej.detail}"
                )
        self.stdout.write(
            self.style.SUCCESS(
                f"\nIngest complete: {total_ok} pending proposal(s), "
                f"{total_rej} rejected. Review via the LSAT Authoring tab."
            )
        )

    # -- subcommands ---------------------------------------------------------

    def _handle_plan(self, config: factory.FactoryConfig, opts: dict[str, Any]) -> None:
        targets = factory.plan(config)
        if opts.get("as_json"):
            self._emit([t.model_dump() for t in targets], True)
            return
        self.stdout.write(
            self.style.MIGRATE_HEADING(f"{len(targets)} generation target(s)")
        )
        for t in targets:
            self.stdout.write(
                f"  [{t.tier:>8}] {t.archetype_id} x {t.difficulty} "
                f"x {t.count} ({t.mode}) — {t.rationale}"
            )

    def _handle_compile(
        self, config: factory.FactoryConfig, opts: dict[str, Any]
    ) -> None:
        manifest, path = factory.compile_plan(config)
        if opts.get("as_json"):
            self._emit(
                {
                    "manifest_id": manifest.manifest_id,
                    "path": str(path),
                    "jobs": [
                        {
                            "job_id": j.job_id,
                            "tier": j.tier,
                            "model_hint": j.model_hint,
                            "archetype_id": j.target.archetype_id,
                            "difficulty": j.target.difficulty,
                            "count": j.target.count,
                            "mode": j.target.mode,
                        }
                        for j in manifest.jobs
                    ],
                },
                True,
            )
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"manifest {manifest.manifest_id} "
                f"({len(manifest.jobs)} jobs) → {path}"
            )
        )
        for j in manifest.jobs:
            self.stdout.write(
                f"  {j.job_id} [{j.tier} → {j.model_hint}] "
                f"{j.target.archetype_id} x {j.target.difficulty} "
                f"x {j.target.count}"
            )

    def _build_executor(
        self, config: factory.FactoryConfig, opts: dict[str, Any]
    ) -> factory.Executor:
        name = opts["executor"]
        try:
            if name == "claude_code":
                return factory.ClaudeCodeExecutor(config)
            if name == "xai":
                return factory.XaiExecutor(config)
            if name == "synth":
                # No provider gate: the synthesis engine calls nothing.
                return factory.SynthExecutor(domain=opts.get("synth_domain"))
            if name == "drafts":
                drafts = opts.get("drafts")
                if not drafts:
                    raise CommandError("--drafts is required with --executor drafts")
                return factory.DraftFileExecutor(Path(drafts))
            return factory.OllamaExecutor(config)
        except ExecutorUnavailable as exc:
            raise CommandError(f"executor unavailable: {exc}") from exc

    def _handle_run(self, config: factory.FactoryConfig, opts: dict[str, Any]) -> None:
        # --judge/--no-judge override the LSAT_FACTORY_JUDGE default for this
        # run only; omitting both leaves the configured value alone.
        if opts.get("judge") is not None:
            config = config.model_copy(update={"judge_enabled": bool(opts["judge"])})
        if opts.get("guides") is not None:
            config = config.model_copy(update={"guides_enabled": bool(opts["guides"])})
        # Fail fast on the executor gate before touching manifests, so the
        # constitution §1 refusal (AC-5) is the first thing an operator sees.
        executor = self._build_executor(config, opts)
        manifest = self._manifest(opts)
        job_ids = (
            [j.strip() for j in str(opts["jobs"]).split(",") if j.strip()]
            if opts.get("jobs")
            else None
        )
        results = async_to_sync(factory.execute_manifest)(
            manifest, executor, config, job_ids=job_ids
        )
        self._report_results(results, bool(opts.get("as_json")))

    def _handle_ingest(
        self, config: factory.FactoryConfig, opts: dict[str, Any]
    ) -> None:
        manifest = self._manifest(opts)
        try:
            results = async_to_sync(factory.ingest_drafts_file)(
                manifest, Path(opts["drafts"]), config
            )
        except ExecutorUnavailable as exc:
            raise CommandError(str(exc)) from exc
        self._report_results(results, bool(opts.get("as_json")))

    def _handle_export_manifest(
        self, config: factory.FactoryConfig, opts: dict[str, Any]
    ) -> None:
        manifest = self._manifest(opts)
        raw_out = opts.get("out")
        out_dir = Path(raw_out) if raw_out else config.resolved_output_dir() / "bundles"
        path = factory.export_bundle(
            manifest, out_dir, config, archive=bool(opts.get("as_zip"))
        )
        if opts.get("as_json"):
            self._emit(
                {
                    "manifest_id": manifest.manifest_id,
                    "jobs": len(manifest.jobs),
                    "path": str(path),
                },
                True,
            )
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"bundle for {manifest.manifest_id} "
                f"({len(manifest.jobs)} job(s)) → {path}"
            )
        )
        self.stdout.write(
            "  return drafts as JSONL, then: manage.py lsat_factory ingest "
            "--drafts <file>"
        )

    def _handle_status(
        self, config: factory.FactoryConfig, opts: dict[str, Any]
    ) -> None:
        snapshot = factory.status(config)
        if opts.get("as_json"):
            self._emit(snapshot, True)
            return
        self.stdout.write(self.style.MIGRATE_HEADING("LSAT factory status"))
        self.stdout.write(
            f"  bank: {snapshot['bank_total']} items {snapshot['bank_by_section']}"
        )
        self.stdout.write(
            f"  writing library: {snapshot['writing_prompts']} prompt(s) "
            f"{snapshot['writing_by_difficulty']}"
        )
        self.stdout.write(
            f"  coverage: {snapshot['cells_with_deficit']}/"
            f"{snapshot['coverage_cells']} cells under target"
        )
        for hole in snapshot["top_deficits"]:
            self.stdout.write(
                f"    {hole['archetype_id']} x {hole['difficulty']}: "
                f"{hole['have']}/{hole['want']}"
            )
        self.stdout.write(
            f"  pending proposals: {snapshot['pending_proposals']} "
            f"({snapshot['pending_from_factory']} from factory)"
        )
        self.stdout.write(f"  latest manifest: {snapshot['latest_manifest'] or '—'}")

    # -- entry point ---------------------------------------------------------

    _HANDLERS = {
        "plan": "_handle_plan",
        "compile": "_handle_compile",
        "run": "_handle_run",
        "ingest": "_handle_ingest",
        "export-manifest": "_handle_export_manifest",
        "status": "_handle_status",
    }

    def handle(self, *args: Any, **opts: Any) -> None:
        sub = str(opts["subcommand"])
        method = self._HANDLERS.get(sub)
        if method is None:  # pragma: no cover - argparse rejects unknown subs
            raise CommandError(f"unknown subcommand {sub!r}")
        config = factory.FactoryConfig.from_settings()
        handler: Any = getattr(self, method)
        handler(config, opts)
