# Documentation runbook

> How the LawGraph AI docs are generated, built, and kept from drifting.
> Recorded by [ADR 0004](adr/0004-sphinx-documentation.md).

## What is generated vs. hand-written

| Part                         | Source of truth                              | How |
| ---------------------------- | -------------------------------------------- | --- |
| Python API reference         | docstrings in `backend/lawgraph/`            | Sphinx `autodoc` + `autosummary` (recursive) |
| REST API reference           | the DRF views/serializers                    | `drf-spectacular` → OpenAPI 3 schema |
| Guides / ADRs                | the Markdown under `docs/`                   | `myst-parser` renders them as-is |
| Diagrams                     | Mermaid fences inside the Markdown           | `sphinxcontrib-mermaid` |
| Source links                 | the code itself                              | `linkcode` → GitHub `[source]` links |

Because the reference pages are regenerated from the code on every build, they
**cannot silently drift**. CI builds with `-W --keep-going`, so a broken
docstring reference, a renamed module, or an unimportable app fails the build.

## Build the docs

Docker-first (matches the rest of the repo):

```bash
make docs            # build HTML into docs/_build/html
make docs-serve      # build, then serve at http://localhost:8001
make docs-linkcheck  # verify internal + external links
```

Locally without Docker:

```bash
pip install -e "backend[docs]"
sphinx-build -b html docs docs/_build/html -W --keep-going
```

The build imports the Django apps under `lawgraph.settings.test` (SQLite, no
telemetry) with heavy native deps mocked, so no Postgres/Neo4j/Redis/Ollama is
required.

## Docstring-coverage gate

[`interrogate`](https://interrogate.readthedocs.io/) enforces the
[AGENTS.md](../AGENTS.md) "all public functions must have docstrings" rule
quantitatively:

```bash
cd backend && interrogate lawgraph -c pyproject.toml
```

The `fail-under` threshold in `backend/pyproject.toml` is a **ratchet**: raise
it as coverage improves, never lower it.

## Adding documentation

- **New Python module/app** — nothing to do; `autosummary --recursive` picks it
  up automatically. Just write good docstrings (reST or Google/NumPy style).
- **New API endpoint** — document the view/serializer; the OpenAPI schema and
  `/api/docs` update automatically. Add response/request annotations with
  `drf-spectacular`'s `@extend_schema` where the inference needs help.
- **New guide** — add the Markdown file under `docs/` and list it in the
  relevant `toctree` in [docs/index.md](index.md).
- **New ADR** — add it under `docs/adr/` and to the ADR `toctree`.

## CI

The `docs` workflow (`.github/workflows/docs.yml`) builds the site and runs the
docstring-coverage gate on every PR that touches `backend/`, `frontend/`, or
`docs/`. On merge to `main` it publishes the HTML to GitHub Pages.
