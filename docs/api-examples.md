# LawGraph AI — API Examples

Quick-reference `curl` examples for every public REST endpoint. All endpoints are prefixed with the base URL (`http://localhost:8000` for local dev). The optional `X-API-Key` header is required when `LSAT_API_KEY` / `AGENT_API_KEY` is set in your environment (spec 009).

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

### Local AI health
```bash
curl http://localhost:8000/api/agents/health/local-ai
```

---

## LSAT Lab — `/api/lsat`

### List questions
```bash
curl "http://localhost:8000/api/lsat/questions?limit=5&section=LR&difficulty=med"
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
# Returns proposals with status="pending"; model runs Ollama locally.
# degraded=true means Ollama was unreachable; fallback placeholder draft returned.
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

```bash
curl -X POST http://localhost:8000/api/analysis/run \
  -H 'Content-Type: application/json' \
  -d '{"case_text": "Brown v. Board of Education ...", "jurisdiction": "US"}'
```

---

## Knowledge Graph — `/api/graph`

```bash
curl "http://localhost:8000/api/graph/stats"
curl "http://localhost:8000/api/graph/cases?limit=10"
curl "http://localhost:8000/api/graph/neighborhood?case_id=<id>&depth=2"
```
