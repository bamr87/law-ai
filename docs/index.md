# LawGraph AI Documentation

> Open-source agent-orchestrated legal intelligence platform.

This site is **generated**. The Python API reference is built from the source
docstrings under `backend/lawgraph/`, the REST API reference is generated from
the Django REST Framework views, and the guides below are the hand-written
Markdown under `docs/` rendered as-is. Because every reference page is
regenerated from the code on each build, the documentation **cannot silently
drift** from the source — and CI fails the build if it does (see
[ADR 0004](adr/0004-sphinx-documentation.md) and
[the documentation runbook](documentation.md)).

## Guides

```{toctree}
:maxdepth: 1
:caption: Guides

architecture
constitution
django-conventions
data-model
data-sources
agent-roles
security
api-examples
legalbench
local-ai
ao-sdlc
ao-sdlc-guide
related-github-repos
documentation
```

## Architecture Decision Records

```{toctree}
:maxdepth: 1
:caption: ADRs

adr/README
adr/0001-adopt-django-backend
adr/0003-autonomy-orchestrator
adr/0004-sphinx-documentation
```

## Reference (generated)

```{toctree}
:maxdepth: 2
:caption: Reference

reference/index
api/index
frontend
```

## Indices

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`
