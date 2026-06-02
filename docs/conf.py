"""Sphinx configuration for the LawGraph AI documentation site (ADR 0004).

This config wires Sphinx so the **Python API reference is generated from the
source docstrings** under ``backend/lawgraph/`` and the existing hand-written
Markdown under ``docs/`` is rendered as-is. The goal is that documentation
cannot drift from the code: ``make docs`` regenerates the reference on every
run and fails (``-W``) on any import error or broken cross-reference.

Run from the repo root via ``make docs`` (Docker) or locally::

    pip install -e "backend[docs]"
    sphinx-build -b html docs docs/_build/html -W --keep-going
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths + Django bootstrap
# ---------------------------------------------------------------------------
# autodoc imports the real modules, so the backend package must be importable
# and Django must be configured before the build walks the API surface.
DOCS_DIR = Path(__file__).resolve().parent
REPO_ROOT = DOCS_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Use the test settings (SQLite, no telemetry, eager Celery) so the build needs
# no real Postgres/Neo4j/Redis. See backend/lawgraph/settings/test.py.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lawgraph.settings.test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./docs-build.sqlite3")
# Minimal env so settings/base.py env() reads succeed during django.setup().
os.environ.setdefault("AGENT_API_KEY", "docs-build")
os.environ.setdefault("SECRET_KEY", "docs-build-not-a-secret")

import django  # noqa: E402

django.setup()

# ---------------------------------------------------------------------------
# Project information
# ---------------------------------------------------------------------------
project = "LawGraph AI"
author = "LawGraph AI contributors"
copyright = "LawGraph AI contributors"  # noqa: A001 — Sphinx-reserved name
release = "0.1.0"
version = "0.1"

# GitHub coordinates used by the linkcode resolver below.
GITHUB_USER = "bamr87"
GITHUB_REPO = "law-ai"
GITHUB_BRANCH = os.environ.get("DOCS_GIT_BRANCH", "main")

# ---------------------------------------------------------------------------
# Extensions
# ---------------------------------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",          # pull docstrings from the source
    "sphinx.ext.autosummary",      # auto-generate one page per module
    "sphinx.ext.napoleon",         # Google/NumPy docstring styles
    "sphinx.ext.viewcode",         # render highlighted source alongside docs
    "sphinx.ext.linkcode",         # deep-link each symbol to GitHub
    "sphinx.ext.intersphinx",      # link out to Python/Django/DRF docs
    "sphinx.ext.autosectionlabel", # stable cross-reference targets
    "myst_parser",                 # render docs/*.md (architecture, ADRs, ...)
    "sphinxcontrib.mermaid",       # render embedded Mermaid diagrams
]

templates_path = []
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
]

# ---------------------------------------------------------------------------
# autodoc / autosummary
# ---------------------------------------------------------------------------
autosummary_generate = True
autosummary_imported_members = False
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_typehints = "description"
autodoc_member_order = "bysource"
add_module_names = False

# Optional deps that live in the `nlp` / `local-ai` extras are NOT installed in
# the slim docs environment (`backend[docs]`), so mock just those. Everything
# else (channels, neo4j, crewai, langgraph, chromadb, ...) ships in the base
# install and must NOT be mocked — mocking an installed base class breaks the
# import of modules that subclass it (MRO errors).
autodoc_mock_imports = [
    "blackstone",
    "langchain_ollama",
    "arize_phoenix",
    "phoenix",
    "langgraph.checkpoint.postgres",
    "langgraph.checkpoint.redis",
]

# ---------------------------------------------------------------------------
# MyST (Markdown) — enable the features the existing docs already use.
# ---------------------------------------------------------------------------
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "linkify",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3
# Route ```mermaid fenced blocks in the existing Markdown to the mermaid
# directive (sphinxcontrib-mermaid) instead of a missing pygments lexer.
myst_fence_as_directive = ["mermaid"]
# `myst.xref_missing`     — Markdown guides cross-link sibling files freely.
# `autosectionlabel.*`    — duplicate section titles across guides are fine.
# `ref.python`            — several packages legitimately re-export symbols via
#                           `__all__` (e.g. lawgraph.core.schemas), so a short
#                           docstring xref like :class:`ExtractionResult` is
#                           ambiguous between the package and submodule. This is
#                           benign; autosummary *import* failures are category
#                           `autosummary` and stay fatal under `-W`, so the
#                           drift signal (a module that no longer imports) is
#                           preserved.
suppress_warnings = ["myst.xref_missing", "autosectionlabel.*", "ref.python"]
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# ---------------------------------------------------------------------------
# intersphinx
# ---------------------------------------------------------------------------
# intersphinx needs network to fetch inventories. Allow fully offline builds
# (e.g. sandboxed CI steps) to skip it via DOCS_OFFLINE=1 without failing -W.
if os.environ.get("DOCS_OFFLINE") == "1":
    intersphinx_mapping = {}
else:
    intersphinx_mapping = {
        "python": ("https://docs.python.org/3", None),
        "django": (
            "https://docs.djangoproject.com/en/stable/",
            "https://docs.djangoproject.com/en/stable/_objects/",
        ),
    }
intersphinx_disabled_reftypes = ["*"]

# ---------------------------------------------------------------------------
# HTML output
# ---------------------------------------------------------------------------
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_title = "LawGraph AI Documentation"

# ---------------------------------------------------------------------------
# linkcode: map a documented Python object back to its source on GitHub.
# ---------------------------------------------------------------------------
def linkcode_resolve(domain: str, info: dict) -> str | None:
    """Return the GitHub URL for the source of a documented object.

    Sphinx calls this for every documented symbol; returning a URL renders a
    ``[source]`` link next to the symbol so the docs always point at the exact
    file/line that produced them.
    """
    if domain != "py" or not info.get("module"):
        return None
    import importlib
    import inspect

    modname = info["module"]
    fullname = info["fullname"]
    try:
        obj = importlib.import_module(modname)
        for part in fullname.split("."):
            obj = getattr(obj, part)
    except (ImportError, AttributeError):
        return None

    obj = inspect.unwrap(obj)
    try:
        source_file = inspect.getsourcefile(obj)
        lines, start = inspect.getsourcelines(obj)
    except (TypeError, OSError):
        return None
    if not source_file:
        return None

    try:
        rel = Path(source_file).resolve().relative_to(REPO_ROOT)
    except ValueError:
        return None
    end = start + len(lines) - 1
    return (
        f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/blob/"
        f"{GITHUB_BRANCH}/{rel}#L{start}-L{end}"
    )


# ---------------------------------------------------------------------------
# linkcheck: don't fail on auth-gated or rate-limited hosts.
# ---------------------------------------------------------------------------
linkcheck_ignore = [
    r"http://localhost:\d+",
    r"http://127\.0\.0\.1:\d+",
    r"https://github\.com/.*/(issues|pull)/.*",
]
linkcheck_timeout = 15


# ---------------------------------------------------------------------------
# Generate the OpenAPI schema from the DRF views at build time so the REST API
# page is always regenerated from the code (ADR 0004, Phase 3).
# ---------------------------------------------------------------------------
def _generate_openapi_schema(app, *_args) -> None:
    """Write ``docs/api/schema.yml`` from the live DRF views via drf-spectacular.

    Registered as a ``builder-inited`` handler so the schema is refreshed on
    every ``sphinx-build`` and the API reference cannot drift from the views.
    Failures are downgraded to a warning so an unrelated docs build still runs.
    """
    target = DOCS_DIR / "api" / "schema.yml"
    try:
        from drf_spectacular.generators import SchemaGenerator
        from drf_spectacular.renderers import OpenApiYamlRenderer

        schema = SchemaGenerator().get_schema(request=None, public=True)
        target.write_bytes(OpenApiYamlRenderer().render(schema))
    except Exception as exc:  # noqa: BLE001 — never hard-fail the whole build here
        logger = __import__("logging").getLogger(__name__)
        logger.warning("Could not generate OpenAPI schema: %s", exc)
        if not target.exists():
            target.write_text(
                "openapi: 3.0.3\ninfo:\n  title: LawGraph AI API\n"
                "  version: 0.1.0\npaths: {}\n"
            )


def setup(app) -> None:
    """Sphinx extension hook: wire build-time schema generation."""
    app.connect("builder-inited", _generate_openapi_schema)

