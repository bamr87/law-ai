# Plan: Safety Guardrails — UPL Disclaimer, Audit Durability, LLM Throttling

- **Spec**: [spec.md](spec.md) (030-safety-guardrails)
- **Approach**: three independent, individually-revertible slices. None
changes agent reasoning, so LegalBench is untouched and the blast radius of each is small.

## Slice A — UPL guardrail (FR-1, FR-2, NFR-A11Y-1)

One component, two presentations, mounted where the risk actually is:

- `LegalDisclaimerFooter` in the frontend **root layout** — every page, no
per-page opt-in to forget. Body becomes a flex column so the footer sits below content rather than floating mid-page.
- `LegalDisclaimerBanner` in Analysis Studio, rendered both before a run and
  next to results, because generated IRAC is where over-reliance happens.
- The static LSAT site gets an equivalent footer in its own root layout plus
`.site-disclaimer` styles, matching that site's plain-CSS conventions (it shares no component code with the main app).

Wording is deliberately specific about *why* it can be wrong: incomplete corpus, absence ≠ no such law, verify against the issuing authority.

## Slice B — Audit durability (FR-3, FR-4, NFR-AUDIT-1)

Rewrite `_persist` around an explicit context check instead of try-ORM-and-catch:

| Context | DB leg |
|---|---|
| sync (worker, command, WSGI) | direct ORM write |
| async (ASGI agent paths) | dispatch `persist_audit_event` to Celery |
| async **and** eager Celery (tests/dev) | skip — eager runs inline and fails identically |

JSONL is written first and unconditionally, so it remains the durable record in every branch. Log levels now carry information: `debug` for routine deferral, `warning` only when an event has no durable record at all. This is why the noisy `SynchronousOnlyOperation` warnings seen in test output disappear — the failing call is no longer attempted.

## Slice C — LLM throttling (FR-5, FR-6, NFR-SEC-1)

`ScopedRateThrottle` with an `llm` scope, opted into per-view rather than a global default, so cheap reads (sections, questions, grade) stay unthrottled. Rate is `env("LLM_THROTTLE_RATE", default="20/min")`.

Test settings raise the rate to `100000/min`: the API suite fires far more than 20 requests at these endpoints within a minute, and a shared throttle bucket would make ordering-dependent failures.

**Technique note (learned the hard way):** the throttle tests originally used `override_settings(REST_FRAMEWORK=…)`. DRF caches settings in `rest_framework.settings.api_settings`, and inside async tests the restore did not take effect — a 1/min override leaked into every later test in the session (14 unrelated failures). The tests now monkeypatch `ScopedRateThrottle.get_rate`, which is test-scoped and unconditionally undone, and clear the throttle cache around each test.

## Slice D — Honest review reason (FR-7, FR-8, FR-9)

Frontend types catch up with what the backend has returned since spec 026 (`degraded`, `requires_review`, `retrieval`, per-source `verified`), then `reviewReason()` picks the message from those flags in priority order (degraded engine → degraded precedents → unverified citations → threshold). Analysis Studio also renders the coverage envelope, so "we found nothing" reads as a corpus statement rather than a legal one.

## Test strategy

- Backend: `tests/api/test_throttling.py` (6 tests) covering throttled/not,
scope placement, and the production default; existing audit/provenance suites guard Slice B.
- Frontend: 5 new Analysis Studio tests — disclaimer before a run, disclaimer
alongside results, degraded reason (and *not* the threshold text), threshold fallback, coverage envelope. Assertions scope to the coverage region because the standing disclaimer shares "absence of results" wording.
- Gates: full backend suite, `npm test`, `npx tsc --noEmit`, ruff/black,
  `make lint-specs`.

## Rollback

Each slice reverts independently: remove the footer mount (A), restore the previous `_persist` (B), drop `throttle_classes` (C), revert `reviewReason` (D). No migrations, no data changes.
