# Tasks: Deliverable, Authenticated Agent Streaming + Real Ollama Readiness

Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md)

- [x] **T-001** — Client-chosen stream id (FR-1, FR-6, AC-2)
  - `AnalysisRequest.stream_id` pattern-validated (422 on malformed); producer publishes to it; `stream_group()` shared with the consumer so the group name cannot drift between the two sides.
- [x] **T-002** — Emit step events during the run (FR-2, FR-3, NFR-RESILIENCE-1, AC-1)
  - `_run_step()` awaits each agent inside the `gather` and emits that agent's event as it finishes, carrying `degraded` alongside trace/latency/confidence; `complete` stays terminal. Emission remains inside the fire-and-forget `_emit_ws_event` wrapper, so a Redis outage still cannot abort a run (spec 021 AC-2 preserved) — verified by the existing `test_agent_ws_events_resilient_to_channel_layer_failure`.
- [x] **T-003** — Authenticate + harden the consumer (FR-4, FR-5, NFR-SEC-1, AC-3, AC-4)
  - Close 4400 on a malformed id and 4401 on a missing/incorrect key, both **before** `group_add`; key read from `?api_key=` or `X-API-Key`; open when no key is configured, matching the REST posture.
- [x] **T-004** — Ollama readiness means loadable (FR-7, NFR-DX-1, AC-5)
  - `backend/scripts/ollama-healthcheck.sh` requires the gate model to be pulled, not just the server to answer; mounted into the container; `start_period` raised to 600s for a cold ~4 GB pull. Verified live: exit 0 with models present, exit 1 + diagnostic when the gate model is absent, container reports `healthy`.
- [x] **T-005** — One source of truth for the model set (FR-8)
  - `OLLAMA_BOOTSTRAP_MODELS` declared in compose; `make local-ai-pull` loops over the value read back from the container instead of restating it; new `make local-ai-verify` runs the same check.
- [x] **T-006** — Frontend stream client (FR-9, AC-6)
  - `lib/agentStream.ts` with `newStreamId()` / `agentStreamUrl()` / `openAgentStream()` (resolves on `ready`, not `open`, so a caller cannot post before the subscription is live).
- [x] **T-007** — Tests (AC-1 … AC-6)
  - 6 backend consumer tests incl. an end-to-end subscribe→post→receive run through the real ASGI app, plus a 422 boundary test; 7 frontend tests. Full backend suite green (78.58%), 32/32 frontend, tsc clean.

## Follow-ups Discovered

- Wire the live trace into Analysis Studio: call `openAgentStream` before
`runAnalysis`, render each `agent_step` as it lands, and fall back to the REST response when the socket fails. The primitive ships here; the UI does not consume it yet, so BL-20260810-06 stays partially open.
- Reconnect + event replay: a dropped socket loses the in-flight trace with
no way to catch up. Needs a short server-side ring buffer per stream id and a `?since=` cursor on connect.
- The WS API key travels in the query string and can land in proxy/access logs; fold into the per-user token work (BL-20260811-06).
- Apply the same client-chosen-stream-id pattern to the LSAT tutor and the autonomy cycle so those long-running paths can stream too.
