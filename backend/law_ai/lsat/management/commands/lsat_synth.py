"""``lsat_synth`` — drive the deterministic item generator.

Spec 049 FR-13/FR-16. Six verbs:

``list``          what schemas and domains exist, and which prove versus construct
``preview``       render one item with its full verification report
``verify``        prove every schema against every domain without emitting anything
``generate``      produce a batch, to a file, to the review queue, or to the bank
``sweep``         the engine's own regression test, exit non-zero on any failure
``polish-yield``  measure the polish prompt: proposed vs accepted, by reject reason

Nothing here touches the network unless ``--polish`` is passed, or the
``polish-yield`` verb is run — that verb *is* a live measurement of the prompt
(BL-20260903-17) and calls the provider chain by design.

    make lsat-synth-sweep
    make lsat-synth-preview ARGS='--schema lr-quantifier-most-overlap --domain field-biology'
    make lsat-synth-generate ARGS='--schema lr-necessary-assumption --count 20 --emit proposals'
    make lsat-synth-polish-yield ARGS='--rounds 2 --count 6'
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.core.management.base import BaseCommand, CommandError

from law_ai.lsat.synth.generate import (
    SynthError,
    SynthItem,
    generate,
    generate_batch,
    sweep,
)
from law_ai.lsat.synth.lexicon import DomainPack, Property, get_domain, load_domains
from law_ai.lsat.synth.promote import (
    PromotionRefused,
    promote_to_bank,
    queue_for_review,
)
from law_ai.lsat.synth.schemas import all_schemas, get_schema

if TYPE_CHECKING:  # pragma: no cover - typing only
    from law_ai.lsat.synth.polish import PolishYield

_ACTIONS = ("list", "preview", "verify", "generate", "sweep", "polish-yield")

#: Where ``polish-yield`` writes its report, relative to the process cwd
#: (``/app`` in Docker = ``./backend`` on the host), like ``--emit jsonl``.
_YIELD_REPORT = "var/lsat_synth/polish_yield.json"


class Command(BaseCommand):
    help = "Generate LSAT items from proved formal skeletons (spec 049)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("action", choices=_ACTIONS)
        parser.add_argument("--schema", help="Schema id. Default: all.")
        parser.add_argument("--domain", help="Domain pack id. Default: all.")
        parser.add_argument("--seed", type=int, default=0)
        parser.add_argument("--count", type=int, default=5)
        parser.add_argument(
            "--seeds", type=int, default=5, help="Seeds per pair in a sweep."
        )
        parser.add_argument(
            "--emit",
            choices=("stdout", "jsonl", "proposals", "bank"),
            default="stdout",
            help="Where generated items go. 'bank' needs LSAT_SYNTH_AUTOPROMOTE "
            "and --promote, and refuses structural-proof items.",
        )
        parser.add_argument("--out", help="Output path for --emit jsonl.")
        parser.add_argument(
            "--promote",
            action="store_true",
            help="Required alongside --emit bank. The setting alone is not consent.",
        )
        parser.add_argument("--reviewer", default="synth")
        parser.add_argument(
            "--polish",
            action="store_true",
            help="Opt in to the one model call: vocabulary proposals only, "
            "re-rendered through the unchanged template and re-verified.",
        )
        parser.add_argument(
            "--rounds",
            type=int,
            default=1,
            help="polish-yield: proposal rounds per domain. Default 1.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="polish-yield: exit non-zero when the measured yield falls "
            "below the floor.",
        )

    # -- list ---------------------------------------------------------------

    def _list(self, opts: dict[str, Any]) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("\nSchemas"))
        for schema in all_schemas():
            m = schema.meta
            marker = "proved " if m.proof_kind == "logical" else "built  "
            self.stdout.write(
                f"  {marker} {m.id:38s} {m.section}  {m.difficulty:6s} "
                f"{m.capability:8s} {m.summary}"
            )
        self.stdout.write(self.style.MIGRATE_HEADING("\nDomains"))
        for domain in load_domains().values():
            caps = ", ".join(
                c
                for c in ("prop", "region", "order", "assign", "causal", "ratio")
                if domain.supports(c)
            )
            self.stdout.write(
                f"  {domain.id:22s} {domain.tone:12s} "
                f"{len(domain.properties)} properties · supports: {caps}"
            )
        self.stdout.write("")

    # -- preview ------------------------------------------------------------

    def _render(self, item: SynthItem) -> None:
        q = item.question
        self.stdout.write(
            self.style.MIGRATE_HEADING(f"\n{q.id}  [{q.section}/{q.difficulty}]")
        )
        self.stdout.write(q.stem)
        for choice in q.choices:
            mark = "*" if choice.label == q.correct else " "
            self.stdout.write(f"  {mark}({choice.label}) {choice.text}")
        self.stdout.write(f"\n  key: {q.correct}")
        self.stdout.write(f"  {item.report.summary()}")
        for check in item.report.checks:
            state = "ok  " if check.passed else "FAIL"
            self.stdout.write(f"    [{state}] {check.name} {check.detail}".rstrip())
        self.stdout.write(
            "  choices: "
            + ", ".join(f"{c.label}={c.status}" for c in item.report.choices)
        )
        self.stdout.write(
            f"  provenance: {item.provenance.schema_id} / "
            f"{item.provenance.domain_id} / seed {item.provenance.seed}"
        )

    def _preview(self, opts: dict[str, Any]) -> None:
        if not opts["schema"] or not opts["domain"]:
            raise CommandError("preview needs --schema and --domain")
        item = generate(opts["schema"], opts["domain"], seed=opts["seed"])
        if opts["polish"]:
            item = self._polish(item)
        self._render(item)
        self.stdout.write(self.style.MIGRATE_HEADING("\n  solve guide"))
        for i, step in enumerate(item.guide.steps, start=1):
            lock = " (spoiler)" if step.spoiler else ""
            self.stdout.write(f"    {i}. [{step.kind}]{lock} {step.title}")

    # -- verify -------------------------------------------------------------

    def _verify(self, opts: dict[str, Any]) -> None:
        schemas = (
            [get_schema(opts["schema"])] if opts["schema"] else list(all_schemas())
        )
        domains = load_domains()
        failures = 0
        for schema in schemas:
            usable = [d for d in domains.values() if d.supports(schema.meta.capability)]
            if not usable:
                self.stdout.write(
                    self.style.WARNING(
                        f"  {schema.meta.id}: no domain supplies "
                        f"{schema.meta.capability!r} content"
                    )
                )
                continue
            for domain in usable:
                try:
                    item = generate(schema.meta.id, domain.id, seed=opts["seed"])
                except (SynthError, Exception) as exc:
                    failures += 1
                    self.stdout.write(
                        self.style.ERROR(f"  {schema.meta.id} / {domain.id}: {exc}")
                    )
                    continue
                self.stdout.write(
                    f"  {schema.meta.id:38s} {domain.id:22s} {item.report.summary()}"
                )
        if failures:
            raise CommandError(f"{failures} schema/domain pair(s) failed to verify")

    # -- generate -----------------------------------------------------------

    def _polish(self, item: SynthItem) -> SynthItem:
        from law_ai.lsat.synth.polish import polish_item

        return polish_item(item)

    def _generate(self, opts: dict[str, Any]) -> None:
        if not opts["schema"]:
            raise CommandError("generate needs --schema")
        domains = (
            [opts["domain"]]
            if opts["domain"]
            else [
                d.id
                for d in load_domains().values()
                if d.supports(get_schema(opts["schema"]).meta.capability)
            ]
        )
        items: list[SynthItem] = []
        per_domain = max(1, opts["count"] // max(1, len(domains)))
        for domain_id in domains:
            items.extend(
                generate_batch(
                    opts["schema"], domain_id, count=per_domain, start_seed=opts["seed"]
                )
            )
        if opts["polish"]:
            items = [self._polish(i) for i in items]

        emit = opts["emit"]
        if emit == "stdout":
            for item in items:
                self._render(item)
        elif emit == "jsonl":
            out = Path(opts["out"] or "var/lsat_synth/items.jsonl")
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", encoding="utf-8") as fh:
                for item in items:
                    fh.write(
                        json.dumps(
                            {
                                "question": item.question.model_dump(mode="json"),
                                "guide": item.guide.model_dump(
                                    mode="json", by_alias=True
                                ),
                                "verification": item.report.model_dump(mode="json"),
                                "provenance": item.provenance.model_dump(mode="json"),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            self.stdout.write(self.style.SUCCESS(f"wrote {len(items)} items → {out}"))
        elif emit == "proposals":
            ids = [queue_for_review(item) for item in items]
            self.stdout.write(
                self.style.SUCCESS(
                    f"queued {len(ids)} draft(s) for review — nothing serves to "
                    "learners until a reviewer approves them"
                )
            )
        else:
            if not opts["promote"]:
                raise CommandError(
                    "--emit bank requires --promote as well: the setting alone is "
                    "not consent to skip review"
                )
            written = 0
            for item in items:
                try:
                    promote_to_bank(item, reviewer=opts["reviewer"])
                    written += 1
                except PromotionRefused as exc:
                    self.stdout.write(self.style.WARNING(f"  refused: {exc}"))
            self.stdout.write(
                self.style.SUCCESS(
                    f"wrote {written} of {len(items)} item(s) to the bank"
                )
            )

    # -- sweep --------------------------------------------------------------

    def _sweep(self, opts: dict[str, Any]) -> None:
        result = sweep(seeds=opts["seeds"])
        self.stdout.write(
            f"{result.generated} item(s) across {result.combinations} "
            f"schema/domain pair(s)"
        )
        for failure in result.failures:
            self.stdout.write(
                self.style.ERROR(
                    f"  {failure.schema_id} / {failure.domain_id} "
                    f"seed {failure.seed}: {failure.error}"
                )
            )
        if not result.ok:
            raise CommandError(f"{len(result.failures)} generation(s) failed")
        self.stdout.write(self.style.SUCCESS("every generated item verified"))

    # -- polish-yield -------------------------------------------------------

    def _rounds_for(
        self, domain: DomainPack, *, rounds: int, count: int
    ) -> tuple[list[PolishYield], list[Property]]:
        """Run the proposal prompt N times against one domain.

        Returns the per-round yields and every property that survived the lint,
        so the caller can check that the accepted vocabulary still renders a
        verifiable item.
        """
        from asgiref.sync import async_to_sync

        from law_ai.lsat.synth.polish import propose_with_yield

        measured: list[PolishYield] = []
        accepted: list[Property] = []
        for _ in range(rounds):
            properties, result = async_to_sync(propose_with_yield)(domain, count=count)
            measured.append(result)
            accepted.extend(properties)
        return measured, accepted

    def _reverifies(
        self, domain: DomainPack, properties: list[Property]
    ) -> bool | None:
        """Does the accepted vocabulary still render a verified item?

        None when there is nothing to try — no accepted properties, or no
        schema whose capability this domain supplies.
        """
        if not properties:
            return None
        extended = domain.model_copy(
            update={"properties": [*properties, *domain.properties]}
        )
        for schema in all_schemas():
            if not domain.supports(schema.meta.capability):
                continue
            try:
                item = generate(
                    schema.meta.id, domain.id, seed=0, domain_override=extended
                )
            except Exception:
                return False
            return bool(item.report.ok)
        return None

    def _yield_report(self, opts: dict[str, Any]) -> dict[str, Any]:
        """Measure the polish prompt across the requested domains."""
        from law_ai.lsat.synth import ENGINE_VERSION
        from law_ai.lsat.synth.polish import POLISH_YIELD_FLOOR, PolishYield

        domains = (
            [get_domain(opts["domain"])]
            if opts["domain"]
            else list(load_domains().values())
        )
        rounds = max(1, int(opts["rounds"]))
        count = max(1, int(opts["count"]))
        overall = PolishYield()
        by_provider: dict[str, PolishYield] = {}
        by_domain: list[dict[str, Any]] = []
        errors: dict[str, int] = {}
        for domain in domains:
            measured, accepted = self._rounds_for(domain, rounds=rounds, count=count)
            per_domain = PolishYield()
            for result in measured:
                overall.merge(result)
                per_domain.merge(result)
                if result.error:
                    errors[result.error] = errors.get(result.error, 0) + 1
                    continue
                tier = result.model_label or result.provider or "unknown"
                by_provider.setdefault(tier, PolishYield()).merge(result)
            by_domain.append(
                {
                    "domain_id": domain.id,
                    "rounds": rounds,
                    **self._yield_dump(per_domain),
                    "accepted_reverifies": self._reverifies(domain, accepted),
                }
            )
        return {
            "engine_version": ENGINE_VERSION,
            "floor": POLISH_YIELD_FLOOR,
            "rounds_per_domain": rounds,
            "proposals_per_round": count,
            "errors": errors,
            "overall": self._yield_dump(overall),
            "by_provider": {
                tier: self._yield_dump(agg) for tier, agg in sorted(by_provider.items())
            },
            "by_domain": by_domain,
        }

    @staticmethod
    def _yield_dump(measured: PolishYield) -> dict[str, Any]:
        return {
            "proposed": measured.proposed,
            "accepted": measured.accepted,
            "rate": round(measured.rate, 4),
            "rejected": dict(sorted(measured.rejected.items())),
        }

    def _polish_yield(self, opts: dict[str, Any]) -> None:
        from law_ai.lsat.synth.polish import POLISH_YIELD_FLOOR, REJECT_REASONS

        report = self._yield_report(opts)
        self.stdout.write(self.style.MIGRATE_HEADING("\nPolish yield"))
        self.stdout.write(
            f"  {'domain':24s} {'proposed':>8s} {'accepted':>8s} {'rate':>7s}  rejects"
        )
        for row in report["by_domain"]:
            rejects = ", ".join(
                f"{reason}={row['rejected'][reason]}"
                for reason in REJECT_REASONS
                if row["rejected"].get(reason)
            )
            self.stdout.write(
                f"  {row['domain_id']:24s} {row['proposed']:8d} "
                f"{row['accepted']:8d} {row['rate']:7.2f}  {rejects}"
            )
        for tier, agg in report["by_provider"].items():
            self.stdout.write(
                f"  tier {tier}: {agg['accepted']}/{agg['proposed']} "
                f"({agg['rate']:.2f})"
            )
        if report["errors"]:
            detail = ", ".join(f"{k}={v}" for k, v in sorted(report["errors"].items()))
            self.stdout.write(
                self.style.WARNING(f"  rounds that never linted: {detail}")
            )

        out = Path(opts["out"] or _YIELD_REPORT)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        overall = report["overall"]
        self.stdout.write(
            f"\n  overall {overall['accepted']}/{overall['proposed']} "
            f"= {overall['rate']:.2f} (floor {POLISH_YIELD_FLOOR:.2f}) → {out}"
        )
        if not overall["proposed"]:
            message = "no proposal round reached the lint — no provider answered"
            if opts["strict"]:
                raise CommandError(message)
            self.stdout.write(self.style.WARNING(f"  {message}"))
            return
        if overall["rate"] < POLISH_YIELD_FLOOR:
            message = (
                f"polish yield {overall['rate']:.2f} is below the "
                f"{POLISH_YIELD_FLOOR:.2f} floor — the prompt needs re-authoring"
            )
            if opts["strict"]:
                raise CommandError(message)
            self.stdout.write(self.style.WARNING(f"  {message}"))
        else:
            self.stdout.write(self.style.SUCCESS("  yield is at or above the floor"))

    def handle(self, *args: Any, **opts: Any) -> None:
        {
            "list": self._list,
            "preview": self._preview,
            "verify": self._verify,
            "generate": self._generate,
            "sweep": self._sweep,
            "polish-yield": self._polish_yield,
        }[opts["action"]](opts)
