"""``ocrmd_scan`` — OCR image or PDF files with the embedded scanner and route the pages.

The Docker-first way to use the ocrmd plug-in (spec 053) without a scanner rig or a
browser::

    make manage CMD='ocrmd_scan /repo/scans/page-15.jpg --doc prep-book'
    make manage CMD='ocrmd_scan /repo/scans/ --doc prep-book --target lsat --options {"hint":"question 15"}'
    make manage CMD='ocrmd_scan /repo/scans/ --doc notes --target matter:smith-lease --user ada'

OCR only, like every path through the embedded scanner (see
:mod:`law_ai.ingestionapp.services.ocrmd_plugin`). ``--target lsat`` sends each page
through the LSAT intake gates into the HITL queue; ``--target matter:<slug>`` files it
as a document on that matter, which needs ``--user`` because matters are per-account.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from law_ai.ingestionapp.services import ocrmd_plugin


class Command(BaseCommand):
    help = "OCR files with the embedded ocrmd scanner and route the pages (spec 053)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("paths", nargs="+", help="image/PDF files or directories")
        parser.add_argument("--doc", default="uploads", help="scanner document slug")
        parser.add_argument(
            "--target",
            default="none",
            help="none | lsat | matter:<slug> (default none)",
        )
        parser.add_argument(
            "--options", default="{}", help="JSON for the target's options"
        )
        parser.add_argument("--user", default="", help="username, for a matter target")
        parser.add_argument("--max-pages", type=int, default=None, help="per file")
        parser.add_argument("--json", action="store_true", help="print the envelopes")

    def handle(self, *args: Any, **opts: Any) -> None:
        if not ocrmd_plugin.enabled():
            raise CommandError("the ocrmd plug-in is off (ENABLE_OCRMD=false)")
        if not ocrmd_plugin.installed():
            raise CommandError("the ocrmd package is not installed (INSTALL_OCRMD=1)")
        try:
            options = json.loads(str(opts["options"] or "{}"))
        except ValueError as exc:
            raise CommandError(f"--options: {exc}") from exc
        target, matter, user = _resolve_target(str(opts["target"]), str(opts["user"]))
        files = _collect_files(opts["paths"], self.stderr.write)
        if not files:
            raise CommandError("no image or PDF files to scan")
        for f in files:
            result = ocrmd_plugin.scan_file(
                f, str(opts["doc"]), max_pages=opts["max_pages"]
            )
            self.stdout.write(f"{f.name}: {result.summary()}")
            for env in result.pages:
                env["options"] = options
                if opts["json"]:
                    self.stdout.write(json.dumps(env, ensure_ascii=False, default=str))
                for line in _route(env, target, matter, user):
                    self.stdout.write(line)


def _resolve_target(target: str, username: str) -> tuple[str, Any, Any]:
    """``(target, matter, user)`` — the matter and its owner when the target names one."""
    if target in ("none", "lsat"):
        return target, None, None
    if not target.startswith("matter:"):
        raise CommandError("--target must be none | lsat | matter:<slug>")
    if not username:
        raise CommandError("a matter target needs --user")
    user = get_user_model().objects.filter(username=username).first()
    if user is None:
        raise CommandError(f"no such user {username!r}")
    from law_ai.matters.models import Matter

    matter = Matter.objects.filter(
        owner=user, slug=target[7:], archived_at__isnull=True
    ).first()
    if matter is None:
        raise CommandError(f"no such matter {target[7:]!r} for {username}")
    return target, matter, user


def _collect_files(paths: list[str], warn: Any) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files += sorted(
                f
                for f in p.iterdir()
                if f.suffix.lower() in ocrmd_plugin.IMAGE_SUFFIXES
            )
        elif p.exists():
            files.append(p)
        else:
            warn(f"not found: {p}")
    return files


def _route(env: dict[str, Any], target: str, matter: Any, user: Any) -> list[str]:
    """Hand one envelope to the target door and describe what it did, one line each."""
    prov = env.get("provenance") or {}
    if target == "lsat":
        from law_ai.lsat.services.ocr_intake import IngestScanRequest, ingest_scan

        out = ingest_scan(IngestScanRequest.model_validate(env))
        return [f"  page {prov.get('page')}: {out.summary}"] + [
            f"    ! {w}" for w in out.warnings
        ]
    if matter is not None:
        from law_ai.matters.services import scanned

        envelope = ocrmd_plugin.Envelope.model_validate(env)
        artifact, created = scanned.file_page(matter, envelope, user)
        d = scanned.delivery(matter, artifact, created, envelope)
        return [f"  page {prov.get('page')}: {d['summary']}"]
    return []
