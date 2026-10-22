# Tasks: Safety Guardrails — UPL Disclaimer, Audit Durability, LLM Throttling

Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md)

- [x] **T-001** — UPL guardrail component + global mount (FR-1, NFR-A11Y-1, AC-1)
  - `LegalDisclaimer.tsx` exporting `LegalDisclaimerFooter` (root layout, so every page carries it) and `LegalDisclaimerBanner` (Analysis Studio, before a run and beside results). `role="note"` / `role="contentinfo"` with a labelled heading.
- [x] **T-002** — Static LSAT site disclaimer (FR-2)
  - Footer in `lsat-static/app/layout.tsx` + `.site-disclaimer` styles in that site's `globals.css` (it shares no component code with the app).
- [x] **T-003** — Context-aware audit persistence (FR-3, FR-4, NFR-AUDIT-1, AC-9)
  - `_persist` picks its DB strategy by execution context (sync → ORM, async → Celery, async+eager → skip); JSONL always written first; warning reserved for the genuine no-durable-record case. Removes the `SynchronousOnlyOperation` failure that fired on every async agent path.
- [x] **T-004** — LLM throttle scope (FR-5, FR-6, NFR-SEC-1, AC-5, AC-6, AC-7, AC-8)
  - `llm` scope in `REST_FRAMEWORK` (`20/min`, env-overridable) applied via `ScopedRateThrottle` on `AnalysisView` + `TutorView` only; test settings raise the rate; `tests/api/test_throttling.py` (6 tests) covers throttled/not-throttled, scope placement, and the production default.
- [x] **T-005** — Frontend types catch up with the backend contract (FR-7)
  - `IRACOutput` gains `degraded` / `requires_review` / `retrieval` and per-source `verified` + `resolved_case_id`; `PrecedentList` gains `degraded`; new `RetrievalStats` interface.
- [x] **T-006** — Honest review reason + coverage rendering (FR-8, FR-9, AC-2, AC-3, AC-4)
  - `reviewReason()` derives the banner message from structured flags in priority order instead of always claiming the 70% threshold; banner wording tightened to "Human review required"; coverage envelope rendered as its own labelled region. 5 new Analysis Studio tests (26 total green).

## Follow-ups Discovered

- Have counsel review the disclaimer wording and decide whether a
jurisdiction-specific or first-run acknowledgement (click-through) is warranted; the current text is engineering-authored.
- Per-user/API-key quotas instead of per-IP throttling: behind a shared
proxy the current `llm` scope under-serves legitimate users, and real quotas need the user accounts that do not exist yet.
- `AuditEvent` rows are not written under async+eager (tests/dev) — JSONL is
the record there. If dev parity matters, run the DB leg in a worker thread with `close_old_connections()` rather than skipping it.
- Surface a "local LLM offline" state in Analysis Studio distinct from the
generic degraded banner (pairs with BL-20260810-16), so users know to start Ollama rather than assuming an empty corpus.
