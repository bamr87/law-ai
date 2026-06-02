# REST API Reference

The HTTP API is built with Django REST Framework. Its OpenAPI 3 schema is
**generated directly from the DRF views and serializers** by
[`drf-spectacular`](https://drf-spectacular.readthedocs.io/) — both when the
server runs and when these docs are built — so the reference here cannot drift
from the implementation (see [ADR 0004](../adr/0004-sphinx-documentation.md)).

## Live, interactive docs

When the stack is running (`make dev`), the schema and interactive explorers
are served from the backend:

| Endpoint        | What it serves                                  |
| --------------- | ----------------------------------------------- |
| `/api/schema`   | Raw OpenAPI 3 schema (YAML)                      |
| `/api/docs`     | Swagger UI (try-it-out console)                 |
| `/api/redoc`    | ReDoc (reference-style reading view)            |

Authentication uses the per-router API-key scheme defined in
{py:mod}`lawgraph.core.auth`; see [docs/security.md](../security.md).

## Generated schema

The schema below is regenerated on every docs build from the current views:

```{literalinclude} schema.yml
:language: yaml
:caption: OpenAPI 3 schema (generated — do not edit by hand)
```
