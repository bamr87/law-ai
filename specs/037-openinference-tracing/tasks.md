# Tasks: OpenInference Tracing Fidelity (Phoenix)

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement in `spec.md` is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@agent:<role>`.
- `(parallel)` marks tasks with no dependency on their immediate predecessor.

> **Ordering note:** T-002 is a spike and gates everything after it. [plan.md](plan.md) §9 names it the single load-bearing assumption — that `openinference-instrumentation-langchain` recognizes our custom `ChatProviderChain` as an LLM and not merely a chain. If T-002 fails, stop and re-plan (the fallback is emitting the LLM span from `core/llm/router.py`, currently a spec §15 follow-up); do **not** build T-004…T-010 on an unverified assumption.

---

## T-001 — Add the instrumentation dependency

- **Refs**: FR-2, NFR-COMPAT-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/pyproject.toml` (edit — `local-ai` extra)
- **Steps**:
  1. Add `"openinference-instrumentation-langchain>=0.1.70",` to the `local-ai` extra, beside the other Phoenix/OTel packages (not to core `dependencies` — `core.telemetry` lazy-imports it, and FR-8 requires a build without the extra to still boot).
  2. Rebuild: `docker compose build backend`.
- **Verify**:
  - `docker compose run --rm --no-deps backend pip install --dry-run --report - "openinference-instrumentation-langchain"` resolves **only** that distribution and upgrades no `opentelemetry-*` package — the pins `>=1.34.0,<1.35.0` / `>=0.55b1,<0.56` must hold unchanged (NFR-COMPAT-1). A resolver that wants to move an OTEL pin is a blocking finding, not a pin bump.
  - `docker compose run --rm --no-deps backend python -c "from openinference.instrumentation.langchain import LangChainInstrumentor; print('ok')"`.

## T-002 — Spike: prove `ChatProviderChain` produces an OpenInference `LLM` span

- **Refs**: FR-2, AC-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/tests/core/test_openinference_langchain.py` (new)
- **Steps**:
  1. Build a local `TracerProvider` with `InMemorySpanExporter` + `SimpleSpanProcessor` (test-only; production is `BatchSpanProcessor` per NFR-PERF-1).
  2. `LangChainInstrumentor().instrument(tracer_provider=provider)`; invoke `ChatProviderChain` once with the provider chain stubbed so no real model is called.
  3. Assert an exported span has `openinference.span.kind == "LLM"` with non-empty `llm.input_messages` / `llm.output_messages` and a populated `llm.model_name`.
  4. `uninstrument()` in teardown so the instrumentor does not leak into other tests.
- **Verify**: `docker compose run --rm backend pytest tests/core/test_openinference_langchain.py -q` passes. **If it does not: stop, record the finding, and re-plan** ([plan.md](plan.md) §9).

## T-003 — Settings + env: `PHOENIX_TRACE_CONTENT`

- **Refs**: FR-7
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/settings/base.py` (edit — env entry + export beside the other `PHOENIX_*` settings)
  - `backend/law_ai/settings/dev.py` (edit — `PHOENIX_TRACE_CONTENT = True`)
  - `.env.example` (edit — ship the safe value `false` with the dev-override note)
- **Steps**:
  1. `PHOENIX_TRACE_CONTENT=(bool, False)` in the env declaration; `PHOENIX_TRACE_CONTENT: bool = env.bool("PHOENIX_TRACE_CONTENT")`.
  2. In `dev.py`, override to `True` with a comment naming OQ-2 and pointing at spec §6 — the override must be self-explaining, since it is the repo's only env-dependent security-relevant default.
- **Verify**: `docker compose run --rm backend python -c "from django.conf import settings; print(settings.PHOENIX_TRACE_CONTENT)"` prints `True` under `dev` and `False` when `DJANGO_SETTINGS_MODULE` points at `law_ai.settings.prod`.

## T-004 — Telemetry core: `register()`, project name, explicit instrumentors, FastAPI removal

- **Refs**: FR-1, FR-2, FR-3, FR-8, NFR-SEC-1, AC-3, AC-5, AC-10
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/core/telemetry.py` (rewrite `init_tracing`)
  - `backend/law_ai/core/apps.py` (edit — `init_tracing(None)` → `init_tracing()` at [line 38](../../backend/law_ai/core/apps.py#L38))
- **Steps**:
  1. `init_tracing()` takes no arguments; register via `phoenix.otel.register(endpoint=…, project_name=settings.PHOENIX_PROJECT_NAME, batch=True, set_global_tracer_provider=True)` — `batch=True` is NFR-PERF-1, non-negotiable. Preserve `deployment.environment` and `service.version` as resource attributes.
  2. Install exactly three instrumentors, explicitly and by name (never `auto_instrument=True`, per OQ-3): `DjangoInstrumentor`, `LangChainInstrumentor`, `HTTPXClientInstrumentor`. Instrument httpx with **no** request/response hooks so no header is ever captured (NFR-SEC-1).
  3. Delete the `FastAPI` `TYPE_CHECKING` import and the unreachable `FastAPIInstrumentor` branch; rewrite the module docstring, which still claims FastAPI auto-instrumentation and references `app.core.*` paths that have not existed since spec 011.
  4. Keep the `_INITIALIZED` idempotence guard and the lazy guarded imports: a missing optional package logs a warning and returns `False` (FR-8).
- **Verify**:
  - `docker compose run --rm backend pytest tests/core/test_telemetry.py -q` passes.
  - `grep -rE "FastAPIInstrumentor|from fastapi" backend/law_ai/core/` returns nothing (AC-10), and no FastAPI/uvicorn reference survives in `core/` docstrings.
  - New test `test_init_tracing_sets_no_provider_when_disabled` asserts that with the endpoint unset, `init_tracing()` is `False` and the global provider is still the default no-op (AC-5).

## T-005 — Root server span for every request (parallel with T-006)

- **Refs**: FR-3, AC-2
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/tests/core/test_telemetry.py` (edit — add the root-span test)
- **Steps**:
  1. Drive a real request through the Django test client with an in-memory exporter attached and assert exactly one exported span has `parent_id is None`, and that it is the Django server span.
  2. If `DjangoInstrumentor` yields no server span under daphne/ASGI, fall back to `opentelemetry-instrumentation-asgi` on the Channels application — and record the dependency-table change in spec §14 rather than slipping it in ([plan.md](plan.md) §9).
- **Verify**: `docker compose run --rm backend pytest tests/core/test_telemetry.py -k root_span -q` passes.

## T-006 — `logged_node` emits a `CHAIN` span without touching the audit write

- **Refs**: FR-4, NFR-AUDIT-1, AC-9
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/core/provenance.py` (edit — both the async and sync `logged_node` wrappers)
  - `backend/tests/core/test_provenance_spans.py` (new)
- **Steps**:
  1. Wrap each wrapper body in `tracer.start_as_current_span(f"node.{name}")`, setting `openinference.span.kind=CHAIN` plus the existing `model` / `prompt_id` / `prompt_version` metadata. Unconditional — no `telemetry.is_enabled()` branch (OQ-4).
  2. On exception: `record_exception` + `set_status(ERROR)`, then re-raise. Existing behavior (no audit event on raise) must be preserved exactly.
  3. `_record_node_event` stays inside the span and stays unconditional — it may not become contingent on tracing (NG2).
- **Verify**: `docker compose run --rm backend pytest tests/core/test_provenance_spans.py tests/core/test_provenance.py -q` passes, including a test that the `langgraph_node` audit payload (minus `trace_id`) is byte-identical tracing-on vs tracing-off (AC-9, NFR-AUDIT-1).

## T-007 — `legal_workflow.model` reports the model that actually served the call

- **Refs**: FR-5
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/agents_runtime/graphs/legal_workflow.py` (edit — [line 452](../../backend/law_ai/agents_runtime/graphs/legal_workflow.py#L452))
- **Steps**:
  1. Remove the hard-coded `settings.OLLAMA_DEFAULT_MODEL`, which has been wrong since spec 034 made Claude the default tier.
  2. Stamp the attribute after `ainvoke` returns, from the `model_label` the chain recorded in `response_metadata` ([`langchain.py:124`](../../backend/law_ai/core/llm/langchain.py#L124)), carried out through workflow state. Fallback if state plumbing grows: set it in the node that owns the model call ([plan.md](plan.md) §2).
  3. Add `openinference.span.kind=CHAIN` to the span.
- **Verify**: `docker compose run --rm backend pytest tests/agents/test_legal_workflow.py -q` passes, with a test asserting the attribute matches the label on the corresponding `llm_call` provenance event — not a hard-coded string.

## T-008 — `phoenix_trace_url`: lazy, cached, bounded project-ID resolution

- **Refs**: FR-6, NFR-PERF-1, AC-4, AC-7
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/core/telemetry.py` (edit — `_resolve_project_id` + rewrite `phoenix_trace_url`)
  - `backend/tests/core/test_telemetry.py` (edit — **rewrite** the URL assertion, do not delete it: R-1)
- **Steps**:
  1. `_resolve_project_id()` — reuse spec 036's `phoenix_base_url()` ([`prompts/phoenix.py:63`](../../backend/law_ai/agents_runtime/prompts/phoenix.py#L63)) rather than re-deriving the REST base; `GET {base}/v1/projects` with an explicit `httpx.Timeout(2.0)`; scan `data[]` for `name == PHOENIX_PROJECT_NAME`; cache the `id` for the process lifetime.
  2. On any failure (timeout, connect error, non-200, name absent): log at `debug`, stamp a monotonic cooldown, return `None`. Calls inside the cooldown return `None` without touching the network — this is what keeps a down Phoenix off the request path (AC-7, NFR-PERF-1).
  3. `phoenix_trace_url` returns `{PHOENIX_UI_URL}/projects/{id}/spans/{trace_id}`, or `None` when the ID is unresolved. It must never raise.
  4. Rewrite `test_phoenix_trace_url_enabled_builds_link` — its current assertion encodes RC-4 as correct behavior; the replacement asserts the new contract so coverage is preserved, not lost.
- **Verify**: `docker compose run --rm backend pytest tests/core/test_telemetry.py -q` passes, covering: cached (two calls ⇒ one respx request), failure ⇒ `None` + no raise + no second request inside cooldown, and project-absent ⇒ `None`.

## T-009 — Content suppression via `TraceConfig`

- **Refs**: FR-7, NFR-PRIVACY-1, AC-6
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/core/telemetry.py` (edit — build `TraceConfig` from `settings.PHOENIX_TRACE_CONTENT`, pass to each instrumentor)
  - `backend/tests/core/test_telemetry.py` (edit)
- **Steps**:
  1. `PHOENIX_TRACE_CONTENT=False` ⇒ `TraceConfig(hide_inputs=True, hide_outputs=True)`; `True` ⇒ defaults. OpenInference's own mechanism only — a bespoke attribute scrubber is out of bounds (spec §6).
  2. Test the **unconfigured** posture (`base.py` default, off) so a regression in the default fails a test rather than relying on code review.
- **Verify**: `docker compose run --rm backend pytest tests/core/test_telemetry.py -k trace_content -q` passes, asserting over **exported span attributes** from an in-memory exporter (NFR-PRIVACY-1 forbids satisfying this by inspection) that no prompt or completion text appears while `openinference.span.kind`, `llm.model_name`, and the parent/child structure survive.

## T-010 — No credential may reach a span (parallel with T-009)

- **Refs**: NFR-SEC-1, AC-8
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/tests/core/test_telemetry.py` (edit)
- **Steps**:
  1. With a sentinel `ANTHROPIC_API_KEY` / OAuth token in settings, run a traced request and scan every attribute value of every exported span for the sentinel.
  2. Confirm `HTTPXClientInstrumentor` is instrumented without request/response hooks — hooks are the only way headers would land in a span.
- **Verify**: `docker compose run --rm backend pytest tests/core/test_telemetry.py -k credential -q` passes.

## T-011 — Docs: the retention switch, next to the local-only pin

- **Refs**: FR-7, NFR-HITL-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `docs/local-ai.md` (edit — `PHOENIX_TRACE_CONTENT` row in the env table, beside `LLM_PROVIDER_CHAIN=ollama`)
  - `docs/architecture.md` (edit — tracing-path row, matching the spec 036/038 rows already there)
- **Steps**:
  1. Document the default (off in `base.py`, on in `dev.py`), what it hides, and — explicitly — that a `make dev` stack **does** retain prompt text in the `phoenix:/data` volume, so it must not be pointed at privileged client matters (spec §12 R-5 residual risk).
  2. State the HITL posture in the PR body: `human_approval_required: false` (NFR-HITL-1) — no ingestion source, no migration, no new agent output path, no gate added or removed.
- **Verify**: `make lint-specs` green; `docs/local-ai.md` names `PHOENIX_TRACE_CONTENT` in the env table.

## T-012 — Live verification against the running stack

- **Refs**: AC-1, AC-2, AC-3, AC-4
- **Owner**: @bamr87
- **Status**: `[x]`
- **Steps**:
  1. `make dev`, then issue one `/api/analysis` request.
  2. **AC-3**: `GET localhost:6006/v1/projects` lists a project named `law_ai` (it does not today — the live baseline is `default` + `playground`), and it holds the new spans.
  3. **AC-2**: fetch that project's spans — one `trace_id`, exactly one span with `parent_id == null`, LLM span a descendant of a `legal_workflow` span.
  4. **AC-1**: at least one span has `span_kind == "LLM"` with non-empty `llm.input_messages` / `llm.output_messages` (dev has content capture on, so this needs no extra configuration).
  5. **AC-4**: open the response's `phoenix_trace_url` in a browser and confirm the span tree renders. Also confirm the route segment (`/spans/` vs `/traces/`) against the real UI. An HTTP status assertion is explicitly insufficient — Phoenix returns 200 for unknown paths.
- **Verify**: transcript (project list, span census, screenshot or description of the rendered tree) recorded in the PR description.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` covered: AC-5…AC-10 by tests, AC-1…AC-4 by tests plus the T-012 live transcript.
- `make lint && make typecheck && make test` green; `make lint-specs` green.
- No LegalBench delta (spec §13: none — instrumentation only, request construction untouched; confirmed in [plan.md](plan.md) §7). Harness stays Ollama-pinned.
- `core.provenance` JSONL + `AuditEvent` writes verified unchanged with tracing both on and off (NFR-AUDIT-1).
- Spec status bumped `clarified` → `shipped`.
- **`## Follow-ups Discovered` section below populated** and mirrored into [BACKLOG.md](../../BACKLOG.md).

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI ([scripts/spec_validator.py](../../scripts/spec_validator.py)) checks this section exists; ([scripts/backlog_lint.py](../../scripts/backlog_lint.py)) checks the BACKLOG mirror.

- BL-20260812-01 — feature, med — emit OpenInference `LLM` spans from `law_ai.core.llm.router` so non-LangChain callers (LSAT tutor, `test_synthesizer`, `topic_frontier`) get content spans; `LangChainInstrumentor` only covers `ChatProviderChain` consumers (spec §15, NG1).
- BL-20260812-02 — feature, med — trace the Celery worker and Channels consumers; ingestion and WS streaming are wholly invisible and OTEL context does not cross the Celery boundary without explicit instrumentation (spec NG6).
- BL-20260812-03 — test-gap, med — measure NFR-PERF-1 rather than argue it: [plan.md](plan.md) §7 discharges the < 25 ms p95 budget by construction (`batch=True`, bounded/cached project lookup) and explicitly does **not** claim it as benchmarked.
- BL-20260812-04 — tech-debt, low — `WorkflowCitation.source` still uses the literal `"ollama-hallucination-check"` for citations the cite-checker could not resolve. Same class of stale-provider label FR-5 fixed on the span, but it is an API-visible enum value, so renaming it (e.g. `cite-check-unresolved`) needs a frontend sweep.
- BL-20260812-05 — feature, low — give `GraphRAGRetriever` an OpenInference `RETRIEVER` span with `retrieval.documents`, so retrieval quality is inspectable next to the LLM span that consumed it (spec §15).
- BL-20260812-06 — infra, low — record token counts and cost on LLM spans once the provider chain surfaces usage metadata, enabling Phoenix's cost view (spec §15).
- BL-20260812-07 — tech-debt, low — write the ADR constitution §10 R-4 is waiting on (or amend §10's "Langfuse (or equivalent) traces wired up — **Met**" wording), now that this spec makes the claim true; and re-evaluate BL-20260502-07's `OBSERVABILITY_BACKEND` abstraction given R-3 reduced the coupling surface to one `register()` call.
