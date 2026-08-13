# Spec: OpenInference Tracing Fidelity (Phoenix)

- **ID**: 037-openinference-tracing
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-11
- **Roadmap Epic**: observability — make the Arize Phoenix surface shipped in spec 010 actually carry LLM content and trace structure
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — no new vendor (§1: Phoenix is already self-hosted, no LLM provider added or changed), no new top-level framework (§2: OpenTelemetry/OpenInference are the existing observability layer), provenance strengthened not bypassed (§4: OTEL spans are added *alongside* the JSONL/Postgres audit trail, never in place of it), one new direct dependency with a license note in §14 (§8). Constitution §10 is touched: the "Langfuse (or equivalent) traces wired up" Level-3 prerequisite is currently marked **Met** on the strength of a surface that this spec shows is not carrying data — see §12 R-4.

## 1. Problem & Motivation

Spec 010 put a self-hosted Arize Phoenix container in the stack and spec 036 observed that "only the *tracing* half is wired." This spec establishes that the tracing half is wired only in the sense that bytes arrive: **the traces carry no LLM content and no trace structure.**

Measured against the running dev stack on 2026-08-11 (`GET /v1/projects/UHJvamVjdDox/spans?limit=500`):

| Measurement | Value | Meaning |
|---|---|---|
| Total spans sampled | 500 | — |
| `span_kind` values | `UNKNOWN` × 500 | No span is recognized as an LLM/chain/retriever span |
| Distinct trace IDs | **499** | 498 traces hold exactly one span; nothing nests |
| Span names | `POST` × 260, `GET` × 185, `legal_workflow.invoke` × 55 | — |
| Distinct attribute keys, all 500 spans | `http.url`, `http.method`, `http.status_code`, `legal_workflow.thread_id`, `legal_workflow.model` | No prompt, completion, model, token, or cost data exists anywhere |
| Phoenix projects | `default` only | `PHOENIX_PROJECT_NAME=law_ai` never took effect |

A representative span — the one an operator opened when reporting this — is a bare httpx client span:

```json
{"name":"POST","span_kind":"UNKNOWN","parent_id":null,
 "attributes":{"http.url":"https://api.anthropic.com/v1/messages",
               "http.method":"POST","http.status_code":200}}
```

That is the entire record of a Claude call. Phoenix renders it faithfully; there is nothing else to render.

The operator-visible consequences: an engineer debugging a bad answer cannot see the prompt or the completion; nobody can attribute latency or token spend to a node; `legal_workflow.invoke` does not parent the LLM calls it causes, so there is no run to inspect; and the `phoenix_trace_url` deep-link the API hands to Analysis Studio ([`analysis/urls.py:254`](../../backend/law_ai/analysis/urls.py#L254), rendered at [`AnalysisStudio.tsx:295`](../../frontend/components/AnalysisStudio.tsx#L295)) points at a project that does not exist.

Four independent root causes, each verified in source:

- **RC-1 — No OpenInference instrumentation.** Phoenix's LLM UI is driven entirely by OpenInference semantic conventions (`openinference.span.kind`, `llm.input_messages`, `llm.output_messages`, `llm.token_count.*`, `input.value` / `output.value`). [`core/telemetry.py`](../../backend/law_ai/core/telemetry.py) instruments only FastAPI and httpx, so it emits *transport* spans and never sets any of them. No `openinference-instrumentation-*` package is a declared dependency.
- **RC-2 — No root span.** [`telemetry.py:76-81`](../../backend/law_ai/core/telemetry.py#L76-L81) calls `FastAPIInstrumentor` — but this backend has been Django/daphne since spec 011, and the only caller passes `app=None` ([`core/apps.py:38`](../../backend/law_ai/core/apps.py#L38)), so that branch is unreachable dead code. `opentelemetry-instrumentation-django` is a declared dependency ([`pyproject.toml:91`](../../backend/pyproject.toml#L91)) that is never imported. With no request-level span, every downstream client call becomes its own orphan root — the 499-traces-for-500-spans result above.
- **RC-3 — Wrong project.** [`telemetry.py:63-69`](../../backend/law_ai/core/telemetry.py#L63-L69) sets the resource attribute `service.name`. Phoenix keys projects off `openinference.project.name` (confirmed: `openinference.semconv.resource.ResourceAttributes.PROJECT_NAME == "openinference.project.name"`). `PHOENIX_PROJECT_NAME` is therefore silently ignored and all traces land in `default`.
- **RC-4 — Broken deep-link.** [`phoenix_trace_url`](../../backend/law_ai/core/telemetry.py#L99-L108) builds `{PHOENIX_UI_URL}/projects/{PHOENIX_PROJECT_NAME}/traces/{trace_id}`. Phoenix's own UI addresses projects by base64 GraphQL ID (`/projects/UHJvamVjdDox/spans/<trace_id>`), and — independently of the ID-vs-name question — a project named `law_ai` does not exist at all (RC-3), so the link cannot resolve. Because Phoenix is a single-page app that returns HTTP 200 for any path, this failure is invisible to a status-code check and shows only as an empty state in the browser.

The leverage is high and the change is small because of how spec 035 built the stack: [`ChatProviderChain`](../../backend/law_ai/core/llm/langchain.py#L55) is a genuine `BaseChatModel`, so LangChain's callback machinery — which `openinference-instrumentation-langchain` hooks — already sees every prompt, completion, and provider metadata blob flowing through the constitution-§1 chain. Capturing it requires no change to the provider code and no second audit path.

**§13 review question — who is the stronger here, and what does this feature do for them?** This feature ranks and summarizes nothing about legal authority; it is developer-facing observability. The stronger party is the operator of this system relative to its users, and better tracing does shift power toward the operator: it makes user prompts and model completions durably legible in a UI. That is a privacy cost, not a neutral good, and §14 constrains it — trace content is retained only in the self-hosted Phoenix inside the compose network, the default-off posture is preserved, and `LLM_PROVIDER_CHAIN=ollama` deployments handling privileged data get an explicit off-switch documented alongside the pin. The offsetting benefit runs to users: an unauditable answer path is precisely what §13 forbids, and today nobody — operator or user — can see what the model was actually asked.

## 2. Origin & Background

**Backlog items claimed:**

- **BL-20260503-23** — *refactor, low* — "Strip the dead-code FastAPI path from `law_ai/core/telemetry.py` (TYPE_CHECKING import + `FastAPIInstrumentor.instrument_app` branch) and replace with `DjangoInstrumentor` so OTEL spans cover the new ASGI app. Sweep remaining historical FastAPI/uvicorn references in core docstrings." _Surfaced in:_ specs/011-django-backend implementation. This is exactly RC-2, filed in 2026-05 as a low-severity tidy-up; the span census above shows its real cost, and this spec absorbs it whole.

**Related but explicitly not claimed:**

- **BL-20260502-07** (Langfuse fallback behind `settings.OBSERVABILITY_BACKEND`) — this spec leans *further* into Phoenix-specific tooling and makes that abstraction harder, not easier. Recorded as risk R-3 rather than silently invalidated.
- **BL-20260503-06** (surface `phoenix_trace_url` on tutor responses) — depends on this spec producing a link that resolves, but adding the field to the tutor payload is separate work.
- **BL-20260811-30/31/32** (spec 036 prompt-registry follow-ups) — the prompt half of the Phoenix surface; independent of trace fidelity.

## 3. Goals

- G1: Every LLM call made through the constitution-§1 provider chain appears in Phoenix as an OpenInference `LLM` span carrying its prompt, completion, model, and provider.
- G2: One user-facing request produces **one** trace with a real parent/child tree — request → workflow → node → LLM call — instead of N orphan single-span traces.
- G3: Traces land in the configured `PHOENIX_PROJECT_NAME` project, and `phoenix_trace_url` returns a link that opens that trace in the Phoenix UI.
- G4: Tracing stays strictly optional and default-off: with `PHOENIX_COLLECTOR_ENDPOINT` unset the backend behaves exactly as it does today, and no Phoenix dependency is required to boot.

## 4. Non-Goals

- NG1: Instrumenting the raw-httpx Claude transport at the SDK level. [`claude_code.py`](../../backend/law_ai/core/claude_code.py) deliberately speaks raw `httpx` to `/v1/messages` rather than using the `anthropic` SDK, so `openinference-instrumentation-anthropic` would capture nothing; adding the SDK purely for tracing is out of scope. Coverage for non-LangChain callers comes from G1's chokepoint plus explicit spans, not from vendor SDK adoption.
- NG2: Replacing or reducing the `core.provenance` JSONL + Postgres audit trail. OTEL spans are a debugging surface; the audit trail remains the constitution-§4 record of truth, and nothing in this spec may make an audit event conditional on tracing being enabled.
- NG3: Phoenix-side evaluations, datasets, experiments, or annotation queues.
- NG4: An `OBSERVABILITY_BACKEND` vendor abstraction (BL-20260502-07).
- NG5: Frontend changes. `AnalysisStudio.tsx` already renders `phoenix_trace_url` verbatim; fixing the URL server-side is sufficient.
- NG6: Tracing the Celery worker and Channels consumers. Worth doing, recorded as a follow-up in §13.

## 5. User Stories

- As a developer debugging a wrong answer, I want to open the trace and read the exact system prompt, user prompt, and completion for each model call, so that I can tell a retrieval failure from a prompting failure without re-running with print statements.
- As an operator, I want one request to be one trace with nested spans, so that I can see which node consumed the latency instead of scrolling 500 unrelated single-span traces.
- As a reviewer, I want the `phoenix_trace_url` on an analysis response to open that run in Phoenix, so that the deep-link Analysis Studio already renders is worth clicking.
- As a privacy-conscious operator running `LLM_PROVIDER_CHAIN=ollama` for privileged matters, I want a documented switch that keeps prompt and completion text out of the trace store, so that observability does not create a second copy of client data.

## 6. Functional Requirements

- **FR-1**: `core.telemetry.init_tracing` registers its tracer provider through `phoenix.otel.register(endpoint=…, project_name=…, batch=True, set_global_tracer_provider=True)` (`arize-phoenix-otel` 0.17.1, already installed) instead of hand-building `TracerProvider` + `OTLPSpanExporter`. This sets the `openinference.project.name` resource attribute, resolving RC-3. `deployment.environment` and `service.version` are preserved as resource attributes.
- **FR-2**: `openinference-instrumentation-langchain` is added as a direct backend dependency and instrumented **explicitly** — `LangChainInstrumentor().instrument(tracer_provider=…)`, never `phoenix.otel.register(auto_instrument=True)` — so every call through `ChatProviderChain` and every LangGraph node emits OpenInference spans with `openinference.span.kind`, `llm.input_messages`, `llm.output_messages`, and `llm.model_name` populated. Resolves RC-1. The instrumented set is exactly what `telemetry.py` names; adding one is a reviewable diff (OQ-3).
- **FR-3**: `DjangoInstrumentor` replaces the unreachable `FastAPIInstrumentor` branch, giving every HTTP request a root server span that downstream client and LLM spans nest under. The `FastAPI` `TYPE_CHECKING` import and the `app` parameter are removed; `init_tracing()` takes no arguments and [`core/apps.py`](../../backend/law_ai/core/apps.py#L38) is updated accordingly. Resolves RC-2 and closes BL-20260503-23.
- **FR-4**: `logged_node` ([`core/provenance.py:313`](../../backend/law_ai/core/provenance.py#L313)) opens a real OTEL span around the wrapped node, named for the node, carrying `openinference.span.kind=CHAIN` plus the existing `model` / `prompt_id` / `prompt_version` metadata, and recording exceptions on the span. The span is opened **unconditionally** — no `telemetry.is_enabled()` branch — because with tracing off the global provider is still the default `NoOpTracerProvider` and `start_as_current_span` is a free no-op; this is the idiomatic OTEL pattern and keeps one code path under test (OQ-4). `_current_trace_id()` already reads the ambient span this way ([`provenance.py:265`](../../backend/law_ai/core/provenance.py#L265)), so the OTEL API is on the default path today and FR-8's promise is about *registering* a provider, not about never calling `get_tracer`. The JSONL + Postgres audit write is unchanged and unconditional (NG2), and `_current_trace_id()` continues to read the ambient trace so the audit event and the span share an ID.
- **FR-5**: `legal_workflow.invoke`'s manual span ([`legal_workflow.py:448`](../../backend/law_ai/agents_runtime/graphs/legal_workflow.py#L448)) is kept but corrected: `legal_workflow.model` currently hard-codes `settings.OLLAMA_DEFAULT_MODEL`, which has been wrong since spec 034 made Claude the default runtime — it must report the provider and model that actually served the call, matching the `llm_call` provenance event.
- **FR-6**: `phoenix_trace_url` returns a URL that resolves in the Phoenix UI, addressing the project by the identifier Phoenix's own routes use rather than by `PHOENIX_PROJECT_NAME`. Project-ID resolution is **lazy** — one `GET /v1/projects` on first use, cached on the module for the process lifetime, `None` until it succeeds (OQ-1). Eager resolution in `init_tracing` is rejected: it would make boot depend on Phoenix being reachable, which contradicts G4/FR-8. Deriving the ID locally as `base64("Project:<pk>")` is also rejected: it is an undocumented internal encoding, and we do not know the `pk` without asking anyway. The lookup must never block or fail a request — it carries an explicit short timeout (≤ 2 s connect+read), and a failure is negative-cached for a cooldown so a down Phoenix cannot put that timeout on every subsequent response; any resolution error logs at debug and returns `None`, exactly as the disabled path does today. Resolves RC-4.
- **FR-7**: Trace-content capture is controllable without disabling tracing. A boolean setting `PHOENIX_TRACE_CONTENT` suppresses prompt and completion text — via OpenInference's standard `TraceConfig` (`OPENINFERENCE_HIDE_INPUTS` / `OPENINFERENCE_HIDE_OUTPUTS`), not a hand-rolled scrubber — while preserving span structure, model names, latency, and token counts, so a privileged-matter deployment can keep the trace tree and drop the content. **Default: off in `settings/base.py`, on in `settings/dev.py`** (OQ-2). Rationale: the constitution-§4 audit trail already made this call in the other direction — `log_agent_call` stores `input_hash` plus a 500-char `output_summary` and comments that it does so "without leaking full prompts" ([`provenance.py:190-201`](../../backend/law_ai/core/provenance.py#L190-L201)) — so a capture-on default would make the debugging surface a *more* permissive store of client data than the audit record of truth. Off-in-base keeps any non-development deployment opt-in; on-in-dev means `make dev` still delivers the primary user story out of the box. `.env.example` ships the safe value with the switch documented next to the `LLM_PROVIDER_CHAIN=ollama` pin, in both `.env.example` and [docs/local-ai.md](../../docs/local-ai.md).
- **FR-8**: With `PHOENIX_COLLECTOR_ENDPOINT` unset, `init_tracing()` remains a no-op returning `False`, no instrumentor is installed, no global tracer provider is touched, and `phoenix_trace_url` returns `None` — preserving today's default-off behavior (G4). A missing optional package logs a warning and returns `False` rather than raising.

### Clarifications (resolved 2026-08-12, `/clarify`)

All four open questions are closed; the resolutions are folded into the FR text above and restated here with their reasoning so `/plan` does not relitigate them.

- **OQ-1 → FR-6: lazy, cached, bounded.** Resolve the Phoenix project ID on first use, cache on the module for the process lifetime, negative-cache failures for a cooldown, ≤ 2 s timeout, `None` until it succeeds. Eager-at-boot is rejected because FR-8/G4 promise the backend boots and serves identically with Phoenix absent, and eager resolution would make boot reach for it. Local `base64("Project:<pk>")` derivation is rejected as an undocumented internal encoding that still needs the `pk` from somewhere. NFR-PERF-1's < 25 ms budget is measured on the steady-state cached path; the one-time lookup is bounded by its own timeout and is not on the budget.
- **OQ-2 → FR-7: off in `base.py`, on in `dev.py`** (decided by @bamr87). The audit layer already declined to persist full prompts ([`provenance.py:190-201`](../../backend/law_ai/core/provenance.py#L190-L201)); a capture-on default would make Phoenix a more permissive store of client prompts than the constitution-§4 record of truth, which is backwards. Off-in-base keeps every non-development deployment explicitly opt-in and satisfies R-5 and the §13 analysis in §1; on-in-dev keeps `make dev` useful, so the feature is not inert for the developer it is built for. Mechanism is OpenInference `TraceConfig`, never a bespoke scrubber. This is the one deviation from the repo's usual "same safe value in code and in `.env.example`" convention (`AUTONOMY_ENABLED`), and it is deliberate: the risk being managed is *retention of client data in a deployed environment*, which the dev stack does not have.
- **OQ-3 → FR-2: explicit instrumentation.** `LangChainInstrumentor().instrument(tracer_provider=…)`. `auto_instrument=True` discovers instrumentors through entry points, so a future transitive dependency could silently begin emitting spans — including from a package nobody reviewed against NFR-SEC-1. The instrumented set stays a reviewable list in `telemetry.py`.
- **OQ-4 → FR-4: unconditional span, no `is_enabled()` branch.** With tracing off the global provider is the default `NoOpTracerProvider` and the span is free. `_current_trace_id()` already calls `trace.get_current_span()` on the default path ([`provenance.py:265`](../../backend/law_ai/core/provenance.py#L265)), so this adds no new exposure to the OTEL API; FR-8's guarantee is that no provider is *registered*, which AC-5 asserts directly. One code path also means AC-9's "audit written identically when disabled" is testing the code that actually runs in production.

## 7. Non-Functional Requirements

- **NFR-PERF-1**: Span export stays off the request path — `BatchSpanProcessor` only, never `SimpleSpanProcessor`. Added p95 latency on `/api/analysis` from tracing must be < 25 ms measured on the steady-state path (FR-6's project ID already resolved), and an unreachable or slow Phoenix must never fail, block, or delay a request. FR-6's one-time project lookup is the single permitted synchronous call to Phoenix; it is bounded by its own ≤ 2 s timeout, happens at most once per cooldown window, and its failure path returns `None` rather than propagating.
- **NFR-SEC-1**: No credential, API key, or `Authorization` header value may appear in any span attribute. The Claude OAuth token and `ANTHROPIC_API_KEY` are handled in [`claude_code.py:295`](../../backend/law_ai/core/claude_code.py#L295) (`_build_headers`); httpx instrumentation must not be configured to capture request headers.
- **NFR-AUDIT-1**: The `core.provenance` JSONL + Postgres trail is written unconditionally and identically whether tracing is on or off. Constitution §4 compliance may not become contingent on Phoenix (NG2).
- **NFR-PRIVACY-1**: With FR-7's content capture disabled, no prompt or completion text appears in any exported span — verified by a test asserting on the exported span attributes, not by inspection.
- **NFR-COMPAT-1**: `opentelemetry-*` packages stay within the existing pinned ranges (`opentelemetry-{api,sdk}>=1.34.0,<1.35.0`, instrumentation `>=0.55b1,<0.56`). If `openinference-instrumentation-langchain` cannot satisfy those pins, that is a blocking finding for `/plan`, not a silent pin bump.
- **NFR-HITL-1**: `human_approval_required: false` — this is developer-facing observability. It adds no data source (§5 ingestion gate), no schema migration, and no new agent output path; the analysis and ingestion HITL gates are untouched.

## 8. Data Model Impact

None. No Neo4j nodes or edges, no Postgres tables, no vector collections are added or changed. Trace data lives in the Phoenix container's own volume (`phoenix:/data`, [`docker-compose.yml:239`](../../docker-compose.yml#L239)), which is outside the application's data model and is not an audit surface (NG2).

## 9. API Surface

No routes are added, removed, or re-shaped. One response *field value* changes semantics:

- `phoenix_trace_url` (`AnalysisResponse`, [`analysis/urls.py:70`](../../backend/law_ai/analysis/urls.py#L70); `IRACOutput`, [`crews/legal_analyst.py:72`](../../backend/law_ai/agents_runtime/crews/legal_analyst.py#L72); `LegalWorkflowOutput`, [`graphs/legal_workflow.py:80`](../../backend/law_ai/agents_runtime/graphs/legal_workflow.py#L80)) — type (`str | None`) and nullability are unchanged; the string now points at a URL that resolves. Frontend needs no change (NG5).

## 10. Agent / Crew Impact

No agent is added, removed, or given a new tool, and no agent's `run(input: dict) -> dict` contract changes. `LegalWorkflow` and `LegalAnalyst` gain observability only. [docs/agent-roles.md](../../docs/agent-roles.md) needs no update; [docs/local-ai.md](../../docs/local-ai.md) §Observability and [docs/architecture.md](../../docs/architecture.md) do (§9 of the constitution).

## 11. Acceptance Criteria

- **AC-1**: Given `PHOENIX_COLLECTOR_ENDPOINT` is set and an analysis request is made, when the resulting trace is fetched from Phoenix, then at least one span has `span_kind == "LLM"` and non-empty `llm.input_messages` and `llm.output_messages` attributes. (FR-1, FR-2 — directly falsifies the "500 × UNKNOWN, no content" census.) Content-bearing attributes require FR-7's `PHOENIX_TRACE_CONTENT` to be on; the dev stack has it on by default, so this is checked as-is against `make dev` and no test may satisfy it by flipping the setting in a way production would not.
- **AC-2**: Given the same request, when its spans are fetched, then they share a single `trace_id`, exactly one span has `parent_id == null`, and the LLM span is a descendant of a `legal_workflow` span. (FR-3, FR-4 — falsifies "499 traces / 500 spans".)
- **AC-3**: Given `PHOENIX_PROJECT_NAME=law_ai`, when `GET /v1/projects` is queried after a traced request, then a project named `law_ai` exists and holds the new spans. (FR-1/RC-3.)
- **AC-4**: Given a completed analysis, when the `phoenix_trace_url` from the response is opened, then the Phoenix UI displays that trace's span tree. (FR-6.) Because Phoenix is an SPA that returns 200 for unknown paths, the automated form of this check asserts the URL's project segment against the ID returned by `GET /v1/projects` — an HTTP status assertion is explicitly insufficient and must not be used.
- **AC-5**: Given `PHOENIX_COLLECTOR_ENDPOINT` is unset, when the backend boots and serves an analysis request, then `init_tracing()` returns `False`, no global tracer provider is set, `phoenix_trace_url` returns `None`, and the response is byte-identical to the pre-change response. (FR-8, G4.)
- **AC-6**: Given `PHOENIX_TRACE_CONTENT` is off — which is the `settings/base.py` default, so this is the *unconfigured* production posture, not a special case — when a traced request completes, then no exported span attribute contains the prompt or completion text, while `span_kind`, `llm.model_name`, and the parent/child structure remain intact. Asserted on the exported spans via an in-memory span exporter, not by inspection. (FR-7, NFR-PRIVACY-1.)
- **AC-7**: Given tracing is enabled and Phoenix is unreachable (container stopped), when an analysis request is made, then the request succeeds within its normal latency envelope and the failure appears only as a log line. (NFR-PERF-1.)
- **AC-8**: Given any traced request, when every exported span attribute is scanned, then no value contains the configured `ANTHROPIC_API_KEY` or OAuth token. (NFR-SEC-1.)
- **AC-9**: Given a `logged_node`-decorated node runs with tracing disabled, when the audit log is read, then the `langgraph_node` JSONL event and its `AuditEvent` row are written exactly as before this change. (NFR-AUDIT-1, NG2.)
- **AC-10**: `grep -r "FastAPIInstrumentor\|from fastapi" backend/law_ai/core/` returns nothing, and the historical FastAPI/uvicorn references in `core/` docstrings are gone. (FR-3, closing BL-20260503-23.)

## 12. Risks & Open Questions

- **R-1** — *Test churn:* [`backend/tests/core/test_telemetry.py:34`](../../backend/tests/core/test_telemetry.py#L34) asserts the exact broken URL (`http://localhost:6006/projects/law_ai/traces/abc123`). That assertion encodes RC-4 as expected behavior and must be rewritten, not deleted — the replacement must assert the new contract, so the suite keeps a regression guard on FR-6 rather than losing coverage (§11 "tests stay aligned").
- **R-2** — *Dependency resolution:* `openinference-instrumentation-langchain` must coexist with the `<1.35.0` OTEL pin and LangChain 1.x. Mitigation: NFR-COMPAT-1 makes an incompatibility a blocking `/plan` finding. Note that `arize-phoenix-otel` 0.17.1 already ships `openinference-instrumentation` 0.1.57 and `openinference-semantic-conventions` 0.1.32 transitively, so the version family is already resolved in the image — this is one new *direct* dependency, not a new tree.
- **R-3** — *Deepens Phoenix coupling:* `phoenix.otel.register()` and OpenInference conventions make BL-20260502-07's `OBSERVABILITY_BACKEND` abstraction harder. Accepted deliberately: OpenInference is Apache-2.0 and vendor-neutral at the *convention* layer (Langfuse and others ingest it), so the coupling is to a shared semantic standard plus one thin registration call, not to Phoenix internals. The registration call is the only piece a future backend swap would need to replace.
- **R-4** — *Constitution §10 is currently inaccurate:* §10 lists "Langfuse (or equivalent) traces wired up" as **Met**, citing `core/telemetry.py`. The census in §1 shows that surface carries no LLM content and no trace structure, so the prerequisite is met in name only. This spec does not amend the constitution (that requires an ADR and human review, per §10 and the closing clause) and does not promote the repo to Level 3 — but it should make the claim true, and the discrepancy is recorded here so a future ADR is not written against a false premise.
- **R-5** — *Observability as a second copy of client data:* enabling content capture writes user prompts and model completions into Phoenix's volume. **Mitigated** by FR-7's resolved default (off in `settings/base.py`, on only in `settings/dev.py`), so no deployed environment retains prompt text unless an operator turns `PHOENIX_TRACE_CONTENT` on and inherits the choice knowingly; §1's §13 review question records why this matters. Residual risk: the dev stack *does* retain content in the `phoenix:/data` volume, which is correct for debugging but means a developer must not point a `make dev` stack at privileged client matters — documented alongside the `LLM_PROVIDER_CHAIN=ollama` pin in [docs/local-ai.md](../../docs/local-ai.md) per FR-7.

Open questions OQ-1 … OQ-4 are **resolved** — see §6 "Clarifications (resolved 2026-08-12, `/clarify`)". No `[CONSTITUTION CONFLICT]` was surfaced: §4 is strengthened not bypassed (NG2/NFR-AUDIT-1), §1 adds no vendor, §5 adds no gate to remove, and OQ-2 settled on the more conservative retention posture of the two.

## 13. LegalBench Impact

- Tasks affected: **none.** No reasoning logic, prompt, retrieval path, or decoding parameter changes; this spec adds observation only.
- Expected delta: 0 pp. The harness stays pinned to Ollama for comparability (constitution §1, §6), and no `legalbench` marker is added to any test in this cycle.
- The `reasoning-change` label (§3) does **not** apply, so a LegalBench run is not gated on this PR. If `/plan` finds that instrumenting `ChatProviderChain` alters request construction in any way, that changes this assessment and requires a run.

## 14. Dependency, License & Security Note (constitution §8)

| Package | Status | License | Note |
|---|---|---|---|
| `openinference-instrumentation-langchain` | **new direct dependency** (0.1.70) | Apache-2.0 | Instruments via LangChain's public callback-manager API; no provider transport, credential path, or request construction is touched. Resolves standalone: `pip install --dry-run` adds this distribution and upgrades nothing, so the OTEL pins hold (NFR-COMPAT-1). |
| `opentelemetry-instrumentation-asgi` | **new direct dependency** (0.55b1) | Apache-2.0 | Added during implementation, not planned at spec time. `DjangoInstrumentor` installs its middleware but emits **no server span under daphne/ASGI** — verified live: the first traced `/api/analysis` request was rooted at `legal_workflow.invoke`, and every other request stayed a single-span orphan, so FR-3 was unmet. This is the fallback [plan.md](plan.md) §9 pre-authorized for exactly that outcome; `law_ai/asgi.py` wraps the outermost ASGI callable in `OpenTelemetryMiddleware`. **Pin note:** unpinned it resolves to 0.65b0 and drags `opentelemetry-api`/`-semantic-conventions` past the `<1.35.0`/`<0.56` pins — a NFR-COMPAT-1 violation — so it is pinned to the sibling family `>=0.55b1,<0.56`, which resolves with nothing else moving. |
| `arize-phoenix-otel` (0.17.1) | already declared ([`pyproject.toml:87`](../../backend/pyproject.toml#L87)), currently **unused** | Apache-2.0 | This spec finally uses it. Distinct from the `arize-phoenix` server package, which is Elastic License 2.0 and is consumed only as a container image, not linked into our code. |
| `opentelemetry-instrumentation-django` | already declared ([`pyproject.toml:91`](../../backend/pyproject.toml#L91)), currently **unused** | Apache-2.0 | This spec finally uses it. |
| `openinference-instrumentation`, `openinference-semantic-conventions` | already present transitively (0.1.57 / 0.1.32) | Apache-2.0 | Pulled in by `arize-phoenix-otel`; verified installed in the current backend image. |

Security posture: all traffic is backend → `phoenix:6006` inside the compose network; no new external egress and no new inbound surface. NFR-SEC-1 forbids credential capture; NFR-PRIVACY-1 plus FR-7 bound what request content is retained. The Elastic-License-2.0 note for the Phoenix *server* in [docs/local-ai.md](../../docs/local-ai.md) is unchanged by this spec — self-hosting and internal use remain permitted.

## 15. Out of Scope / Follow-ups

Candidate follow-ups for `tasks.md` §Follow-ups Discovered and [BACKLOG.md](../../BACKLOG.md) (constitution §11):

- Trace the Celery worker and Channels consumers (NG6) — ingestion and WS streaming are wholly invisible today, and context does not propagate across the Celery boundary without explicit instrumentation.
- Emit explicit OpenInference `LLM` spans from `law_ai.core.llm.router` so non-LangChain callers (LSAT tutor, `test_synthesizer`, `topic_frontier`) get content spans too — LangChain instrumentation only covers `ChatProviderChain` consumers (see NG1).
- Give `GraphRAGRetriever` an OpenInference `RETRIEVER` span (`retrieval.documents`), so retrieval quality is inspectable next to the LLM span that consumed it.
- Record token counts and cost on LLM spans once the provider chain surfaces usage metadata, enabling Phoenix's cost view.
- Surface `phoenix_trace_url` on LSAT tutor responses — unblocks the existing BL-20260503-06.
- Write the ADR that constitution §10 R-4 is waiting on, or amend §10's "Met" wording to match what is actually wired.
- Re-evaluate BL-20260502-07 (`OBSERVABILITY_BACKEND` abstraction) in light of R-3, now that the coupling surface is one `register()` call.
