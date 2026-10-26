# Law AI — API Examples

Quick-reference `curl` examples for every public REST endpoint. All endpoints are prefixed with the base URL (`http://localhost:8000` for local dev). Each router gates on its own optional `<SCOPE>_API_KEY` env var, with the shared `AGENT_API_KEY` as a fallback for every scope (`backend/law_ai/core/auth.py`, spec 009): `AGENT_API_KEY` for `/api/agents`, `ANALYSIS_API_KEY` (or `AGENT_API_KEY`) for `/api/analysis`, `GRAPH_API_KEY` (or `AGENT_API_KEY`) for `/api/graph`, `LSAT_API_KEY` (or `AGENT_API_KEY`) for `/api/lsat`. With no key configured for a scope, that router stays open (local-first dev posture). `GET /health` is never gated.

---

## Health

### Top-level health check (no auth)
```bash
curl http://localhost:8000/health
```

This is the container healthcheck endpoint (`docker-compose.yml`'s `backend` service probes it directly), `AllowAny`, mounted at both `/health` and `/health/`.

**Response** (`200 OK`):
```json
{
  "status": "healthy",
  "service": "law_ai-backend",
  "version": "0.1.0",
  "last_ingest_at": "2026-08-10T09:12:00+00:00"
}
```

`last_ingest_at` is `null` when Neo4j is unreachable or has no ingested nodes yet.

---

## Agent Operations — `/api/agents`

### List registered agents
```bash
curl http://localhost:8000/api/agents | jq '.agents[].name'
```

### Recent agent runs
```bash
curl "http://localhost:8000/api/agents/runs?limit=20"
```

### Drill into a single run (all events for a trace)
```bash
curl "http://localhost:8000/api/agents/runs/<trace_id>"
```

### Per-agent performance metrics
```bash
curl "http://localhost:8000/api/agents/metrics?limit=500"
# Returns: p50/p95 latency, avg confidence, success rate, error count per agent
```

### Backlog snapshot
```bash
curl http://localhost:8000/api/agents/backlog
# Returns {counts, open, claimed, done} parsed live from BACKLOG.md
```

### Spec package status
```bash
curl http://localhost:8000/api/agents/specs
# Returns [{id, status}, ...] parsed from each specs/NNN-slug/spec.md's "## Status" line
```

### Local AI health
```bash
curl http://localhost:8000/api/agents/health/local-ai
```

**Response** (`200 OK`):
```json
{
  "ollama": {"reachable": true, "models": ["mistral:7b-instruct-q4_K_M"]},
  "checkpointer": {"kind": "postgres", "reachable": true},
  "phoenix": {"reachable": true, "ui_url": "http://localhost:6006", "enabled": true},
  "claude_code": {"reachable": true, "auth": "oauth"},
  "llm_chain": [
    {"provider": "claude_code", "position": 0, "configured": true, "reachable": true},
    {"provider": "anthropic_api", "position": 1, "configured": true, "reachable": true},
    {"provider": "ollama", "position": 2, "configured": true, "reachable": true}
  ]
}
```

`llm_chain` (spec 034/035) reports every provider in `LLM_PROVIDER_CHAIN`, in the order it is tried (`position`), answering "which provider actually serves the next request, and why" — this is the one field to check when diagnosing which tier of the Claude-first / Ollama-last chain is live. Each of the five sub-probes runs independently (`asyncio.gather`), so one dead provider never fails the whole response.

---

## LSAT Lab — `/api/lsat`

### List questions
```bash
curl "http://localhost:8000/api/lsat/questions?limit=5&section=LR&difficulty=med"
```

### Question detail
```bash
curl http://localhost:8000/api/lsat/questions/lr-001
```

### Grade an answer
```bash
curl -X POST http://localhost:8000/api/lsat/grade \
  -H 'Content-Type: application/json' \
  -d '{"question_id": "lr-001", "choice": "B"}'
```

### AI tutor explanation
```bash
curl -X POST http://localhost:8000/api/lsat/tutor \
  -H 'Content-Type: application/json' \
  -d '{"question_id": "lr-001", "user_choice": "C", "user_question": "Why is C wrong?"}'
```

### Learner stats
```bash
curl http://localhost:8000/api/lsat/stats
curl "http://localhost:8000/api/lsat/stats?section=LR"
```

### Reference data (sections, concepts, passages)
```bash
curl http://localhost:8000/api/lsat/sections               # all sections + per-section question_count
curl http://localhost:8000/api/lsat/sections/LR             # one section + sample_question_ids
curl "http://localhost:8000/api/lsat/concepts?section=LR"   # concepts, optionally filtered by section
curl http://localhost:8000/api/lsat/concepts/parallel-reasoning
curl "http://localhost:8000/api/lsat/passages?section=RC"   # reading-comprehension passages
curl "http://localhost:8000/api/lsat/passages?concept=necessary-assumption"  # only the sets carrying a concept
curl http://localhost:8000/api/lsat/passages/<passage_id>   # passage + its questions
```

---

## LSAT Content Authoring (HITL) — spec 019

### View pending proposals
```bash
curl "http://localhost:8000/api/lsat/proposals?status=pending&limit=20"
```

### Generate new draft questions (on-demand)
```bash
curl -X POST http://localhost:8000/api/lsat/proposals/generate \
  -H 'Content-Type: application/json' \
  -d '{"section": "LR", "difficulty": "med", "count": 2, "concepts": ["parallel-reasoning"]}'
# Returns proposals with status="pending". The model call goes through the
# LLM_PROVIDER_CHAIN (spec 034): Claude OAuth first, ANTHROPIC_API_KEY second,
# local Ollama last.
# degraded=true means the entire chain was exhausted; a deterministic
# placeholder draft was returned instead.
```

### Approve a proposal (promotes to live question bank)
```bash
curl -X POST "http://localhost:8000/api/lsat/proposals/<proposal_id>/approve" \
  -H 'Content-Type: application/json' \
  -d '{"reviewer": "alice", "note": "Good item, clear distractors"}'
```

### Reject a proposal
```bash
curl -X POST "http://localhost:8000/api/lsat/proposals/<proposal_id>/reject" \
  -H 'Content-Type: application/json' \
  -d '{"note": "Stem is ambiguous"}'
```

### Gap analysis — weakest measured concepts
```bash
curl "http://localhost:8000/api/lsat/gaps?limit=10"
# Returns (section, concept) pairs sorted by ascending learner accuracy.
# The nightly autonomy-lsat-content Celery beat targets the top row.
```

---

## Analysis Studio — `/api/analysis`

### Run analysis (HTTP)

```bash
curl -X POST http://localhost:8000/api/analysis \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: $ANALYSIS_API_KEY' \
  -d '{"text": "Brown v. Board of Education — equal protection claim.", "stream_id": "my-stream-1"}'
```

**Response** (`200 OK`):
```json
{
  "id": "an-a1b2c3d4e5f6",
  "timestamp": "2026-08-11T09:12:00+00:00",
  "latency_ms": 1234,
  "confidence": 0.85,
  "requires_human_review": false,
  "irac": {"issue": "...", "rule": "...", "application": "...", "conclusion": "...", "confidence": 0.9, "sources": [...], "trace_id": "...", "..."},
  "precedents": {"precedents": [...], "confidence": 0.8, "trace_id": "..."},
  "agent_trace": [
    {"agent": "LegalAnalyst", "trace_id": "...", "latency_ms": 640.1, "confidence": 0.9},
    {"agent": "PrecedentHunter", "trace_id": "...", "latency_ms": 580.4, "confidence": 0.8}
  ],
  "trace_url": null,
  "phoenix_trace_url": null,
  "langgraph_thread_id": null
}
```

`trace_url` is the span-tree deep link; `phoenix_trace_url` is a deprecated alias of it, still emitted for existing clients and always identical (BL-20260906-10). Read `trace_url`.

### Resume a thread (BL-20260810-13)

Pass a previous response's `langgraph_thread_id` back as `thread_id` to continue that thread's checkpointed state; `resumed: true` in the response says the thread already held state. A resume must ask the **same** question in the **same** jurisdiction — changing either would silently rewrite what the thread recorded, so it answers `409 Conflict` naming the field that diverged (BL-20260905-81). Omit `thread_id` to branch a new thread instead.

### Scope a round to a matter (BL-20260817-05)

```bash
curl -X POST http://localhost:8000/api/analysis \
  -H 'Content-Type: application/json' \
  -b cookies.txt -H "X-CSRFToken: $CSRF" \
  -d '{"text": "Is the lease enforceable?", "matter_id": 12}'
```

`matter_id` feeds the authorities that matter has already had *verified* into GraphRAG as a boost set, so a later round inside one matter ranks known-good citations first. The bias is always reported back in `irac.retrieval.boosted_count` and `irac.retrieval.boost_source` (`"matter:<slug>"`) — a promoted passage is never presented as the corpus's own ordering. The field is **session-only and owner-scoped**: a matter you do not own answers `404` and an anonymous caller `401`, because the boost set is another account's verified work.

### Live progress via WebSocket (spec 032)

`stream_id` is **client-chosen**, not server-generated — the response's `id` field is returned too late to subscribe to. The contract (`backend/law_ai/agentsapi/consumers.py`):

1. Client picks a `stream_id` itself (`^[A-Za-z0-9._-]{1,64}$`).
2. Client connects to `/ws/agents/<stream_id>` and waits for a `{"type": "ready"}` event.
3. Client **then** POSTs `/api/analysis` with that same `stream_id` in the request body.
4. `analysis_token` events arrive while the analyst is still writing (BL-20260905-11): `{"type": "analysis_token", "agent": "LegalAnalyst", "text": "…", "chars": 128, "model": "xai/grok-4.6"}`, where `chars` is the running total produced so far. They are progress, not the result — the deltas are a JSON payload being written, so render the count (or a spinner) rather than the fragments.
5. Two `agent_step` events arrive as each agent finishes, followed by one `complete` event, all published to the `agent-run-<stream_id>` channel-layer group.

```javascript
const streamId = crypto.randomUUID();
const ws = new WebSocket(`ws://localhost:8000/ws/agents/${streamId}?api_key=${ANALYSIS_API_KEY}`);
// Browsers cannot set headers on a WS handshake — pass the key as a query
// param (or send an X-API-Key header from a non-browser client). Omit
// entirely when no key is configured for the scope.

ws.onmessage = (e) => {
  const event = JSON.parse(e.data);
  if (event.type === "ready") {
    fetch("http://localhost:8000/api/analysis", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": ANALYSIS_API_KEY },
      body: JSON.stringify({ text: "...", stream_id: streamId }),
    });
    return;
  }
  // {"type": "analysis_token", ...} while the analyst writes, then
  // {"type": "agent_step", ...} x2, then {"type": "complete", ...}
  console.log(event);
};
```

Events are fire-and-forget — a Redis outage does not abort the HTTP response, it just means no WS events are delivered.

---

## Knowledge Graph — `/api/graph`

```bash
curl "http://localhost:8000/api/graph/stats"
curl "http://localhost:8000/api/graph/cases?limit=10"
curl "http://localhost:8000/api/graph/courts?limit=200"
curl "http://localhost:8000/api/graph/neighborhood/<case_id>?limit=50"
```

`courts` returns the distinct `Case.court` values with their case counts, most-populous first — the case picker's court filter is a free-form substring match, so its dropdown is fed from the whole corpus rather than the page it has loaded (BL-20260905-89). `limit` defaults to 200 and caps at 500.

`case_id` is a path segment, not a query parameter. `limit` (default 50, max 200) is the only query parameter `neighborhood` accepts — there is no `depth` parameter.
