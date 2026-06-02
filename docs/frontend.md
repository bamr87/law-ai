# Frontend reference

The Next.js frontend (`frontend/`) is documented with
[TypeDoc](https://typedoc.org/), which reads the TypeScript types and TSDoc
comments directly from the source — so this reference stays in lock-step with
the components and the API client (see
[ADR 0004](adr/0004-sphinx-documentation.md)).

Generate it locally with:

```bash
cd frontend && npm install && npm run docs   # outputs frontend/docs-api/
```

In CI the TypeDoc output is published alongside this site, under
[`frontend/`](frontend/index.html):

```{raw} html
<p><a href="frontend/index.html">Browse the frontend API reference &rarr;</a></p>
```

## What is covered

| Area               | Source                          | Notes |
| ------------------ | ------------------------------- | ----- |
| API client         | `frontend/lib/api.ts`           | Typed `apiFetch` wrapper + per-feature helpers |
| UI components      | `frontend/components/*.tsx`     | Knowledge graph, agent dashboard, analysis studio, LSAT lab, … |

All graph interactions go through the typed API routes documented in the
[REST API reference](api/index.md); the client never talks to Neo4j directly
(see [docs/architecture.md](architecture.md)).
