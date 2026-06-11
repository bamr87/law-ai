"""Versioned prompt registry (spec 024 FR-5).

Single loader for every prompt template under
``backend/lawgraph/agents_runtime/prompts/``. Resolves a prompt id +
version to a file, strips an optional leading HTML-comment metadata
block, and returns the template text together with its content hash so
provenance events can pin exactly which prompt produced an output.

File-naming convention (matches the existing tree):

* ``<name>.v<N>.md`` — explicit version (``lsat_content_author.v2.md``)
* ``<name>.md``      — unversioned (``legal_workflow/retrieve.md``)

``load_prompt("legal_workflow/retrieve", version="1")`` prefers
``retrieve.v1.md`` and falls back to ``retrieve.md``; with no version it
picks the highest ``.vN`` available, then the unversioned file.

Placeholders use ``{{name}}`` (not ``str.format``) so JSON braces inside
prompt bodies never need escaping::

    tpl = load_prompt("legal_workflow/retrieve", version="1")
    prompt = tpl.render(question="...", jurisdiction="any")
"""

from __future__ import annotations

import functools
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["PromptTemplate", "load_prompt"]

_PROMPTS_DIR = Path(__file__).resolve().parent

_COMMENT_RE = re.compile(r"\A\s*<!--.*?-->\s*", re.DOTALL)
_VERSION_RE = re.compile(r"\.v(\d+)\.md\Z")


@dataclass(frozen=True)
class PromptTemplate:
    """A resolved prompt template plus the metadata provenance needs."""

    prompt_id: str
    version: str
    text: str
    sha256: str
    path: Path

    def render(self, **values: object) -> str:
        """Substitute ``{{key}}`` placeholders with ``values``.

        Example::

            PromptTemplate(..., text="Q: {{question}}").render(question="hi")
        """
        out = self.text
        for key, value in values.items():
            out = out.replace("{{" + key + "}}", str(value))
        return out


def _strip_metadata(raw: str) -> str:
    """Drop a single leading ``<!-- ... -->`` block (file-level metadata)."""
    return _COMMENT_RE.sub("", raw, count=1)


def _candidates(name: str, version: str | None) -> list[tuple[Path, str]]:
    base = _PROMPTS_DIR / name
    out: list[tuple[Path, str]] = []
    if version is not None:
        out.append((base.with_name(f"{base.name}.v{version}.md"), version))
        out.append((base.with_name(f"{base.name}.md"), version))
        return out
    # No version requested: highest .vN first, then the unversioned file.
    parent = base.parent
    if parent.is_dir():
        versioned: list[tuple[int, Path]] = []
        for p in parent.glob(f"{base.name}.v*.md"):
            m = _VERSION_RE.search(p.name)
            if m:
                versioned.append((int(m.group(1)), p))
        for n, p in sorted(versioned, reverse=True):
            out.append((p, str(n)))
    out.append((base.with_name(f"{base.name}.md"), "1"))
    return out


@functools.lru_cache(maxsize=64)
def load_prompt(name: str, version: str | None = None) -> PromptTemplate:
    """Load prompt ``name`` (path relative to the prompts dir, no extension).

    :raises FileNotFoundError: when no matching prompt file exists.

    Example::

        tpl = load_prompt("lsat_content_author", version="2")
        assert tpl.prompt_id == "lsat_content_author"
    """
    for path, resolved_version in _candidates(name, version):
        if path.is_file():
            raw = path.read_text(encoding="utf-8")
            text = _strip_metadata(raw).strip("\n")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            return PromptTemplate(
                prompt_id=name,
                version=resolved_version,
                text=text,
                sha256=digest,
                path=path,
            )
    raise FileNotFoundError(
        f"no prompt file for id={name!r} version={version!r} under {_PROMPTS_DIR}"
    )
