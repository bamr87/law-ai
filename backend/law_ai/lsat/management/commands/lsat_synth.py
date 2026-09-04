"""``lsat_synth`` — drive the deterministic item generator.

Spec 049 FR-13/FR-16. Five verbs:

``list``      what schemas and domains exist, and which prove versus construct
``preview``   render one item with its full verification report
``verify``    prove every schema against every domain without emitting anything
``generate``  produce a batch, to a file, to the review queue, or to the bank
``sweep``     the engine's own regression test, exit non-zero on any failure

Nothing here touches the network unless ``--polish`` is passed.

    make lsat-synth-sweep
    make lsat-synth-preview ARGS='--schema lr-quantifier-most-overlap --domain field-biology'
    make lsat-synth-generate ARGS='--schema lr-necessary-assumption --count 20 --emit proposals'
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from law_ai.lsat.synth.generate import (
    SynthError,
    SynthItem,
    generate,
    generate_batch,
    sweep,
)
from law_ai.lsat.synth.lexicon import load_domains
from law_ai.lsat.synth.promote import (
    PromotionRefused,
    promote_to_bank,
    queue_for_review,
)
from law_ai.lsat.synth.schemas import all_schemas, get_schema

_ACTIONS = ("list", "preview", "verify", "generate", "sweep")


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

    def handle(self, *args: Any, **opts: Any) -> None:
        {
            "list": self._list,
            "preview": self._preview,
            "verify": self._verify,
            "generate": self._generate,
            "sweep": self._sweep,
        }[opts["action"]](opts)
