# Plan: Deliverable, Authenticated Agent Streaming + Real Ollama Readiness

- **Spec**: [spec.md](spec.md) (032-deliverable-agent-streaming)
- **Approach**: two unrelated fixes that share one theme — a surface that
*appeared* to work but structurally could not. Streaming published to a group nobody could join; the healthcheck reported ready for a server that could not serve. Both are fixed by making the contract explicit.

## Slice A — Streaming that can actually deliver (FR-1 … FR-6)

The bug is an ordering impossibility, not a timing flake:

```
before:  POST ──run both agents──► emit all events ──► response{analysis_id}
                                        ▲                      │
                                        └──── client learns id ┘   (too late)

after:   client picks stream_id ─► WS subscribe ─► ready
                                                     │
         POST{stream_id} ─► agent A done → emit ─────┤
                            agent B done → emit ─────┤
                            complete      → emit ─────┘
```

1. `stream_id` on `AnalysisRequest`, pattern-validated by Pydantic so a bad
   value is a 422 rather than a weird group name.
2. `_run_step()` wraps each agent inside the `gather`, emitting that
agent's event the moment it finishes. This is what makes the trace *incremental* rather than a batch delivered at the end.
3. Consumer: reject non-conforming ids (close 4400) and unauthenticated
sockets (close 4401) **before** `group_add`, so a rejected client never receives an event. Key accepted via query string (browsers cannot set handshake headers) or `X-API-Key`.
4. `stream_group()` lives in the consumer module and is imported by the
   producer, so the two cannot disagree about the group name.

## Slice B — Readiness that means something (FR-7, FR-8)

`ollama list` succeeds against a model-less server. New `ollama-healthcheck.sh` additionally requires the **gate model** — the first entry of `OLLAMA_BOOTSTRAP_MODELS`, the same variable the bootstrap script gates on — to appear in `ollama list`, matching the exact tag or its `:latest` form.

`OLLAMA_BOOTSTRAP_MODELS` moves into compose as the single declaration; `make local-ai-pull` now loops over the value read back *from the container*, so the list cannot drift from the bootstrap script. `make local-ai-verify` exposes the same check to operators.

`start_period` rises to 600s because the gate model is a ~4 GB cold pull — otherwise a correctly-working first boot would be marked unhealthy.

## Slice C — Frontend primitive (FR-9)

`lib/agentStream.ts`: `newStreamId()` (guaranteed to satisfy the server's id pattern, with a fallback for environments lacking `crypto.randomUUID`), `agentStreamUrl()` (http→ws, appends the key), and `openAgentStream()` which resolves on **`ready`** rather than `open` — resolving on `open` would let a caller POST before the server-side `group_add` completes, reintroducing the race the whole design removes.

## Test strategy

- Backend: 6 new consumer tests — malformed id rejection, key required /
wrong key / valid via query / valid via header / open when unset, and an **end-to-end** test that subscribes, posts through the real ASGI app, and asserts two `agent_step` events plus `complete` with a matching `analysis_id`; plus a 422 test for a bad `stream_id` at the API boundary.
- Healthcheck verified live in the running container: exit 0 with the gate
model present, exit 1 with a diagnostic when `OLLAMA_BOOTSTRAP_MODELS` points at a model that isn't pulled, and `docker inspect` reporting `healthy`.
- Frontend: 7 tests over the stream client, including that a step frame
  alone does not resolve the promise and that non-JSON frames are ignored.

## Rollback

Each slice reverts independently. Omitting `stream_id` restores exactly the old (undeliverable but harmless) event routing; reverting the healthcheck line restores the permissive check.
