"""LegalBench dataset fetcher and cache builder (BL-20260811-09).

Run inside the backend container::

    python -m law_ai.eval.fetch --subset core_reasoning,precedent_retrieval

or, from the repo root, ``make legalbench-cache``.

**Why this module exists.** Until the real dataset is on disk, every eval run
falls back to :mod:`law_ai.eval.loaders`' synthetic stubs, so ``--check-regression``
has nothing meaningful to compare and ``--fail-on-synthetic`` can never pass.

Three decisions are frozen here, deliberately in code rather than in prose:

1. **Pinned revisions.** Task *data* comes from the Hugging Face dataset
   ``nguha/legalbench`` at :data:`DATA_REVISION`; the task *prompt templates*
   and the per-task licence READMEs come from the GitHub repository
   ``HazyResearch/legalbench`` at :data:`PROMPT_REVISION`. Both are commit
   SHAs, never ``main``: a benchmark that silently changes under the harness
   makes the 1 pp regression policy meaningless.
2. **Per-task licence review.** Every task's README is parsed and its licence
   checked against :data:`ALLOWED_LICENCES` *before* a single item is written.
   A task with a missing or unrecognised licence aborts the fetch — the cache
   can never contain data nobody reviewed.
3. **CI downloads, we never vendor.** ``backend/var/legalbench/*/items.jsonl``
   stays git-ignored (see ``.gitignore``); the reproducibility guarantee comes
   from the pinned revisions plus ``manifest.json``, which records the sha256
   of every source file this module downloaded. A later fetch that sees a
   different digest fails loudly instead of quietly re-benchmarking.

Only the standard library is used, so the fetcher runs in the plain backend
image without the heavy ``legalbench`` extras (``datasets``/``evaluate``).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from law_ai.eval.paths import CACHE_ROOT, subset_cache_path

logger = logging.getLogger("law_ai.eval.fetch")

#: Hugging Face dataset commit that supplies the ``test.tsv`` task splits.
DATA_REVISION = "daec8237410aa23e3faf4bc41ad8b3a7e1696826"

#: GitHub commit that supplies ``base_prompt.txt`` and the licence READMEs.
PROMPT_REVISION = "b46bf4ffae90524b2b72aaa30e7745fe9db64481"

_HF_BASE = (
    "https://huggingface.co/datasets/nguha/legalbench/resolve/" f"{DATA_REVISION}/data"
)
_GH_BASE = (
    "https://raw.githubusercontent.com/HazyResearch/legalbench/"
    f"{PROMPT_REVISION}/tasks"
)

#: Where the source-file digests are recorded. Tracked in git so a fetch on a
#: CI runner is verifiable against the fetch that produced the baseline.
MANIFEST_PATH = CACHE_ROOT / "manifest.json"

#: Per-task cap. LegalBench test splits run to hundreds of items and the gate
#: model is a local 7B on CPU; a fixed, documented cap keeps a nightly run
#: inside its budget while staying deterministic (the head of each split, in
#: file order). Changing it changes the benchmark — re-baseline afterwards.
DEFAULT_MAX_ITEMS_PER_TASK = 50

#: Licences a cached task may carry. Both are attribution licences; the
#: share-alike variant is admissible precisely because we never redistribute
#: the data (decision 3 above — CI downloads it per run). Anything else,
#: including a task whose README states no licence, is refused.
ALLOWED_LICENCES: frozenset[str] = frozenset({"cc-by-4.0", "cc-by-sa-4.0"})

#: LegalBench task -> Law AI subset mapping. Recorded here (and mirrored in
#: ``backend/var/legalbench/LICENSES.md``) so a baseline number is
#: interpretable: "core_reasoning accuracy" means *these* tasks, nothing else.
SUBSET_TASKS: dict[str, tuple[str, ...]] = {
    # Rule-application / rule-conclusion reasoning over short fact patterns.
    "core_reasoning": (
        "hearsay",
        "personal_jurisdiction",
        "ucc_v_common_law",
        "abercrombie",
    ),
    # Does a cited case support the proposition, and which case is it?
    "precedent_retrieval": (
        "citation_prediction_classification",
        "citation_prediction_open",
    ),
    # Contract NLI: does the clause entail the hypothesis?
    "contract_nli": (
        "contract_nli_explicit_identification",
        "contract_nli_confidentiality_of_agreement",
        "contract_nli_sharing_with_third-parties",
    ),
    # Definitional reasoning.
    "definitions": (
        "definition_classification",
        "definition_extraction",
    ),
    # Causal reasoning in judicial opinions.
    "causation": ("legal_reasoning_causality",),
}

_LICENCE_RE = re.compile(r"\*\*Licen[sc]e\*\*:\s*(?P<value>.+)", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"\{\{(?P<name>[a-zA-Z0-9_ -]+)\}\}")


class LegalBenchFetchError(RuntimeError):
    """A fetch could not be completed safely.

    Raised for network failures, unreviewable licences, checksum drift, and
    malformed task files. Every one of them must stop the fetch: a partial or
    unverified cache is worse than no cache, because the harness would happily
    score it and call the number a measurement.
    """


@dataclass(frozen=True)
class SourceFile:
    """One downloaded file plus the digest recorded in ``manifest.json``."""

    key: str
    url: str
    data: bytes

    @property
    def sha256(self) -> str:
        """Hex sha256 of the downloaded bytes."""
        return hashlib.sha256(self.data).hexdigest()

    @property
    def text(self) -> str:
        """UTF-8 decoding of the downloaded bytes."""
        return self.data.decode("utf-8")


@dataclass
class TaskFetch:
    """A task's licence, prompt template, rows, and source digests."""

    task: str
    licence: str
    items: list[dict[str, Any]]
    digests: dict[str, str] = field(default_factory=dict)


Downloader = Callable[[str], bytes]


def _http_get(url: str, *, timeout: int = 60) -> bytes:
    """Fetch ``url`` and return its bytes, or raise :class:`LegalBenchFetchError`."""
    request = urllib.request.Request(url, headers={"User-Agent": "law-ai-eval"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload: bytes = response.read()
            return payload
    except (urllib.error.URLError, TimeoutError) as exc:
        raise LegalBenchFetchError(
            f"could not download {url}: {exc}. The fetcher needs outbound "
            "network access (dev container or CI runner)."
        ) from exc


def parse_licence(readme: str) -> str | None:
    """Return the normalised licence id declared in a LegalBench task README.

    LegalBench task READMEs carry a ``**License**:`` line, usually as a
    markdown link with inconsistent casing (``CC By 4.0``, ``CC BY-SA 4.0``).

    Examples:
        >>> parse_licence("**License**: [CC By 4.0](https://example.test)")
        'cc-by-4.0'
        >>> parse_licence("no licence here") is None
        True
    """
    match = _LICENCE_RE.search(readme)
    if not match:
        return None
    raw = match.group("value").strip()
    # Strip a markdown link wrapper: "[CC BY 4.0](url)" -> "CC BY 4.0".
    link = re.match(r"\[(?P<label>[^\]]+)\]", raw)
    if link:
        raw = link.group("label")
    slug = re.sub(r"[^a-z0-9.]+", "-", raw.strip().lower()).strip("-")
    return slug or None


def parse_tsv(text: str) -> list[dict[str, str]]:
    """Parse a LegalBench TSV into a list of row dicts.

    Examples:
        >>> parse_tsv("index\\tanswer\\ttext\\n0\\tYes\\thi\\n")
        [{'index': '0', 'answer': 'Yes', 'text': 'hi'}]
    """
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    rows: list[dict[str, str]] = []
    for raw in reader:
        row = {k: (v or "") for k, v in raw.items() if k is not None}
        if any(value.strip() for value in row.values()):
            rows.append(row)
    return rows


def render_prompt(template: str, row: dict[str, str]) -> str:
    """Substitute a row's columns into a LegalBench ``base_prompt.txt``.

    The templates end with the task instruction plus ``{{column}}``
    placeholders for each TSV column they consume (``{{text}}``,
    ``{{citation}}``, ``{{circuit}}``, …).

    Examples:
        >>> render_prompt("Q: {{text}}\\nA:", {"text": "why?"})
        'Q: why?\\nA:'

    Raises:
        LegalBenchFetchError: If the template references a missing column —
            a silently unresolved placeholder would be sent to the model
            verbatim and score as a wrong answer.
    """
    missing: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        name = match.group("name")
        if name not in row:
            missing.append(name)
            return match.group(0)
        return row[name]

    rendered = _PLACEHOLDER_RE.sub(_replace, template)
    if missing:
        raise LegalBenchFetchError(
            f"prompt template references unknown column(s) {sorted(set(missing))}; "
            f"available columns: {sorted(row)}"
        )
    return rendered


def _task_urls(task: str) -> dict[str, str]:
    """Source URLs for ``task``, keyed by manifest key suffix."""
    return {
        "test.tsv": f"{_HF_BASE}/{task}/test.tsv",
        "base_prompt.txt": f"{_GH_BASE}/{task}/base_prompt.txt",
    }


def _fetch_readme(task: str, download: Downloader) -> SourceFile:
    """Fetch a task README, tolerating the repo's ``README.MD`` spelling."""
    last: LegalBenchFetchError | None = None
    for name in ("README.md", "README.MD"):
        url = f"{_GH_BASE}/{task}/{name}"
        try:
            return SourceFile(key=f"{task}/README.md", url=url, data=download(url))
        except LegalBenchFetchError as exc:
            last = exc
    assert last is not None
    raise last


def fetch_task(
    task: str,
    *,
    max_items: int = DEFAULT_MAX_ITEMS_PER_TASK,
    download: Downloader | None = None,
) -> TaskFetch:
    """Download one LegalBench task, licence-check it, and build its items.

    Args:
        task: LegalBench task directory name (e.g. ``"hearsay"``).
        max_items: Cap on items taken from the head of the test split.
        download: Byte fetcher, injected by tests. Defaults to plain HTTP.

    Returns:
        A :class:`TaskFetch` with the reviewed licence, the converted items,
        and the sha256 of every downloaded source file.

    Raises:
        LegalBenchFetchError: On a network failure, an unreviewable licence,
            or a task file the converter cannot read.
    """
    fetch = download or _http_get
    readme = _fetch_readme(task, fetch)
    licence = parse_licence(readme.text)
    if licence is None:
        raise LegalBenchFetchError(
            f"task {task!r} declares no licence in its README — refusing to "
            "cache data that has not been licence-reviewed."
        )
    if licence not in ALLOWED_LICENCES:
        raise LegalBenchFetchError(
            f"task {task!r} is licensed {licence!r}, which is not in "
            f"{sorted(ALLOWED_LICENCES)}. Add an entry to LICENSES.md and "
            "widen ALLOWED_LICENCES only after a licence review."
        )

    sources = [readme]
    urls = _task_urls(task)
    for suffix, url in urls.items():
        sources.append(SourceFile(key=f"{task}/{suffix}", url=url, data=fetch(url)))
    by_key = {source.key: source for source in sources}

    template = by_key[f"{task}/base_prompt.txt"].text
    rows = parse_tsv(by_key[f"{task}/test.tsv"].text)
    if not rows:
        raise LegalBenchFetchError(f"task {task!r} test split is empty")

    items: list[dict[str, Any]] = []
    for row in rows[:max_items]:
        answer = row.get("answer", "").strip()
        if not answer:
            continue
        items.append(
            {
                "index": f"{task}-{row.get('index', len(items))}",
                "text": render_prompt(template, row),
                "answer": answer,
                "metadata": {
                    "task": task,
                    "licence": licence,
                    "data_revision": DATA_REVISION,
                    "prompt_revision": PROMPT_REVISION,
                },
            }
        )
    if not items:
        raise LegalBenchFetchError(f"task {task!r} produced no answerable items")

    return TaskFetch(
        task=task,
        licence=licence,
        items=items,
        digests={source.key: source.sha256 for source in sources},
    )


def interleave(groups: Sequence[Sequence[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Round-robin the per-task item lists into one subset ordering.

    A subset is several tasks concatenated, and the eval CLI's ``--limit``
    takes the head of the list. Concatenation would make ``--limit 20`` mean
    "the first task only"; interleaving makes it a spread across tasks.

    Examples:
        >>> interleave([[{"index": "a"}], [{"index": "b"}, {"index": "c"}]])
        [{'index': 'a'}, {'index': 'b'}, {'index': 'c'}]
    """
    merged: list[dict[str, Any]] = []
    for column in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if column < len(group):
                merged.append(group[column])
    return merged


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    """Read ``manifest.json``, or return an empty manifest when absent."""
    if not path.exists():
        return {
            "data_revision": DATA_REVISION,
            "prompt_revision": PROMPT_REVISION,
            "files": {},
        }
    parsed: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    parsed.setdefault("files", {})
    return parsed


def verify_digests(
    manifest: dict[str, Any], digests: dict[str, str], *, update: bool
) -> None:
    """Compare fresh digests against the manifest, recording new ones.

    Args:
        manifest: Manifest dict from :func:`load_manifest` (mutated in place).
        digests: ``{manifest key: sha256}`` for the files just downloaded.
        update: When true, a differing digest overwrites the manifest entry
            instead of raising (``--update-manifest``).

    Raises:
        LegalBenchFetchError: When a recorded digest changed and ``update``
            is false — the pinned revision would not have changed, so this
            means the source moved and scores are no longer comparable.
    """
    known: dict[str, str] = manifest["files"]
    for key, digest in sorted(digests.items()):
        recorded = known.get(key)
        if recorded is None or update:
            known[key] = digest
            continue
        if recorded != digest:
            raise LegalBenchFetchError(
                f"checksum mismatch for {key}: manifest has {recorded}, "
                f"download has {digest}. Re-run with --update-manifest only "
                "after confirming the source change is intended (it resets "
                "benchmark comparability)."
            )


def write_subset(subset: str, items: Iterable[dict[str, Any]]) -> Path:
    """Write ``items`` as JSONL to the subset's cache path and return it."""
    path = subset_cache_path(subset)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return path


def fetch_subsets(
    subsets: Sequence[str],
    *,
    max_items: int = DEFAULT_MAX_ITEMS_PER_TASK,
    update_manifest: bool = False,
    download: Downloader | None = None,
    manifest_path: Path = MANIFEST_PATH,
) -> dict[str, Path]:
    """Fetch every task of each subset and write the JSONL caches.

    Args:
        subsets: Subset names; each must appear in :data:`SUBSET_TASKS`.
        max_items: Per-task cap on items taken from the test split.
        update_manifest: Accept and record changed source digests.
        download: Byte fetcher, injected by tests.
        manifest_path: Manifest location (overridden in tests).

    Returns:
        ``{subset: written path}``.

    Raises:
        LegalBenchFetchError: On an unmapped subset, or any per-task failure.
    """
    unknown = [subset for subset in subsets if subset not in SUBSET_TASKS]
    if unknown:
        raise LegalBenchFetchError(
            f"no LegalBench task mapping for {unknown}; "
            f"known subsets: {sorted(SUBSET_TASKS)}"
        )

    manifest = load_manifest(manifest_path)
    manifest["data_revision"] = DATA_REVISION
    manifest["prompt_revision"] = PROMPT_REVISION
    written: dict[str, Path] = {}

    for subset in subsets:
        groups: list[list[dict[str, Any]]] = []
        for task in SUBSET_TASKS[subset]:
            result = fetch_task(task, max_items=max_items, download=download)
            verify_digests(manifest, result.digests, update=update_manifest)
            logger.info(
                "fetched task=%s licence=%s items=%d",
                result.task,
                result.licence,
                len(result.items),
            )
            groups.append(result.items)
        items = interleave(groups)
        written[subset] = write_subset(subset, items)
        logger.info(
            "cached subset=%s items=%d -> %s", subset, len(items), written[subset]
        )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return written


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m law_ai.eval.fetch",
        description=(
            "Download the real LegalBench task data at a pinned revision and "
            "cache it as backend/var/legalbench/<subset>/items.jsonl."
        ),
    )
    parser.add_argument(
        "--subset",
        default="core_reasoning,precedent_retrieval",
        help=(
            "Comma-separated subsets to cache (default: "
            "core_reasoning,precedent_retrieval). "
            f"Known: {', '.join(sorted(SUBSET_TASKS))}."
        ),
    )
    parser.add_argument(
        "--max-items-per-task",
        type=int,
        default=DEFAULT_MAX_ITEMS_PER_TASK,
        help=(
            "Cap items taken from each task's test split "
            f"(default: {DEFAULT_MAX_ITEMS_PER_TASK}). Changing this changes "
            "the benchmark — re-record the baseline afterwards."
        ),
    )
    parser.add_argument(
        "--update-manifest",
        action="store_true",
        help="Record changed source checksums instead of failing on drift.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for ``python -m law_ai.eval.fetch``."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)
    subsets = [s.strip() for s in args.subset.split(",") if s.strip()]

    try:
        written = fetch_subsets(
            subsets,
            max_items=args.max_items_per_task,
            update_manifest=args.update_manifest,
        )
    except LegalBenchFetchError as exc:
        print(f"FETCH FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    for subset, path in written.items():
        count = sum(1 for _ in path.open(encoding="utf-8"))
        print(f"{subset}: {count} items -> {path}")
    print(f"manifest: {MANIFEST_PATH}")
    print(f"revisions: data={DATA_REVISION[:12]} prompts={PROMPT_REVISION[:12]}")


if __name__ == "__main__":
    main(sys.argv[1:])
