# ADR 0004: Sphinx-generated documentation

## Status

accepted

## Context

The `docs/` tree is a set of hand-written Markdown guides (architecture,
constitution, conventions, ADRs, data model, …) with no landing page and **no
generated content**. Nothing connects the prose to the source code, so:

- API documentation has to be written and updated by hand and drifts from the
  code the moment a signature, view, or module changes.
- There is no machine-checked guarantee that documented modules still exist or
  that every public symbol is documented.
- The REST API has no published schema; `urls.py` pointed callers at the unused
  `/admin/doc/` page.

[docs/constitution.md](../constitution.md) §9 already lists documentation
obligations, and §2 requires an ADR before adopting a new top-level tool. This
ADR records the decision to add a documentation **generator**.

The codebase is unusually well-suited to Sphinx: docstrings already use reST
cross-reference roles (`:func:`, `:mod:`) — e.g. `lawgraph/core/autonomy.py` —
and [AGENTS.md](../../AGENTS.md) "Coding Standards" already mandates docstrings
on all public functions.

## Decision

Adopt **Sphinx** as the documentation generator, configured in
[docs/conf.py](../conf.py):

- **`autodoc` + `autosummary` (recursive)** generate one reference page per
  module under `backend/lawgraph/` automatically — new modules appear with no
  manual index maintenance.
- **`napoleon`** supports Google/NumPy docstrings alongside the existing reST.
- **`viewcode` + `linkcode`** add a `[source]` link from every documented
  symbol back to its exact line on GitHub.
- **`intersphinx`** links out to Python/Django docs.
- **`myst-parser`** renders the existing `docs/*.md` unchanged; **`mermaid`**
  renders the diagrams already embedded in them.
- **`drf-spectacular`** generates the OpenAPI 3 schema from the DRF views and
  serializers, served at `/api/schema`, `/api/docs`, `/api/redoc`, and embedded
  in the docs site.
- **`interrogate`** enforces a docstring-coverage floor so undocumented public
  code fails CI.

Dependencies live in a new `docs` extra in
[backend/pyproject.toml](../../backend/pyproject.toml), consistent with the
existing `dev` / `local-ai` / `nlp` extras. The build runs via `make docs`
(Docker-first) and a `docs` CI job that builds with `-W --keep-going` so any
import error or broken cross-reference blocks the PR. This is the drift gate:
the reference is regenerated from source on every run.

## Consequences

- Documentation is generated from a single source of truth (the code) and is
  verified in CI, so it cannot silently drift.
- Contributors must keep docstrings accurate and importable; a broken docstring
  reference or an undocumented public symbol fails `make docs`.
- The docs build imports the Django apps under `lawgraph.settings.test`
  (SQLite, no telemetry) with heavy native deps mocked, so it needs no real
  Postgres/Neo4j/Redis/Ollama.
- A new optional dependency set is added; the slim base install is unchanged.

## Alternatives Considered

- **MkDocs + `mkdocstrings`**: excellent Markdown-native UX, but the existing
  docstrings are already reST-flavoured and Sphinx's `autosummary --recursive`
  + `linkcode` give stronger drift guarantees and source links out of the box.
- **`pdoc`**: near-zero config, but no first-class Markdown ingestion, no
  Mermaid, weaker cross-referencing, and no way to fold in the existing guides.
- **Hand-written docs only (status quo)**: rejected — this is the source of the
  drift the task set out to eliminate.

## Supersedes / Superseded by

- Supersedes the stale `/admin/doc/` documentation pointer in
  [backend/lawgraph/urls.py](../../backend/lawgraph/urls.py).
- Not superseded.
