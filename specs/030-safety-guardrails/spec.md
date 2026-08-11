# Spec: Safety Guardrails — UPL Disclaimer, Audit Durability, LLM Throttling

- **ID**: 030-safety-guardrails
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-11
- **Roadmap Epic**: continuous-evolution hardening (2026-08-10 audit)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — §4 (audit durability), §8 (security baselines), §13 (honest presentation of authority + absence)

## 1. Problem & Motivation

Three independent safety gaps, all verified against the code:

1. **No UPL guardrail anywhere.** Grepping `frontend/app`, `frontend/components`,
   `lsat-static`, and `docs/` found no "legal advice", "disclaimer", or
   "attorney" text. The product renders confident IRAC conclusions
   ("The plaintiff is likely to succeed on a negligence claim") to lawyers,
   law students, and **prospective** law students — i.e. laypeople — with
   nothing saying it is not legal advice.
2. **The audit DB leg failed on every async path.** `_persist` called the
   Django ORM from inside the event loop, raising `SynchronousOnlyOperation`
   on every agent call, swallowed at `debug` level; the Celery fallback then
   ran inline under eager mode and failed identically. Provenance is the
   platform's constitutional differentiator, so a silently-degraded write
   path is a §4 problem.
3. **No rate limiting on LLM endpoints.** No DRF throttle existed anywhere.
   `POST /api/analysis` and the LSAT tutor each fan out to a single local
   Ollama with a 120 s timeout behind an open-by-default auth gate — one
   client or crawler could starve every other user.

A fourth, related defect surfaced while fixing (1): the Analysis Studio HITL
banner asserted "confidence … is below the 70% HITL threshold" **whatever**
triggered review, which is false whenever a degraded agent or an unresolved
citation set the flag (specs 026/029 made those the common cases).

## 2. Goals

- G1: A "not legal advice" guardrail on every page of both web surfaces, and
  next to generated analysis specifically (BL-20260810-07).
- G2: Audit events always have a durable record, and the DB leg stops doing
  guaranteed-to-fail work (BL-20260810-10).
- G3: LLM-invoking endpoints are throttled; cheap reads are not
  (BL-20260810-11).
- G4: The review banner states the *actual* reason review is required.

## 3. Non-Goals

- NG1: Per-user quotas or auth-aware throttling — the throttle is per-client
  (DRF anon/user ident); real quotas need user accounts.
- NG2: Jurisdiction-specific UPL language or counsel review of the wording;
  this is the engineering guardrail, not a legal sign-off.
- NG3: Rendering per-citation `verified` badges (BL-20260810-02 keeps that);
  this spec renders the coverage envelope only.

## 4. User Stories

- As a prospective law student, I want to be told plainly that this is not
  legal advice, so I don't act on AI output as if a lawyer wrote it.
- As an auditor, I want every agent event to land somewhere durable, so the
  provenance trail is complete.
- As an operator, I want one client unable to monopolise the local model.

## 5. Functional Requirements

- **FR-1**: `LegalDisclaimerFooter` is mounted in the frontend root layout, so
  every page carries it; `LegalDisclaimerBanner` renders in Analysis Studio
  both before a run and alongside results.
- **FR-2**: The static LSAT site carries an equivalent footer disclaimer on
  every page, with styles in `globals.css`.
- **FR-3**: `_persist` writes JSONL first (always), then chooses the DB leg by
  context: direct ORM write when sync; Celery dispatch when async; skip when
  async **and** Celery is eager (the eager task would fail identically).
- **FR-4**: A warning is logged only when an event has **no** durable record
  (JSONL failed *and* the DB leg is unavailable); routine deferral stays at
  debug so the logs remain readable.
- **FR-5**: `REST_FRAMEWORK` defines an `llm` throttle scope
  (default `20/min`, overridable via `LLM_THROTTLE_RATE`);
  `AnalysisView` and `TutorView` opt in via `ScopedRateThrottle`. No global
  default throttle is applied, so read endpoints stay unthrottled.
- **FR-6**: The test settings raise the `llm` rate so the suite's request
  volume cannot trip it; tests asserting throttling force the rate locally.
- **FR-7**: `IRACOutput` / `PrecedentList` TypeScript types carry the
  `degraded`, `requires_review`, `retrieval`, and per-source `verified`
  fields the backend has shipped since spec 026.
- **FR-8**: The HITL banner derives its message from the structured flags
  (degraded engine → degraded precedents → unverified citations → confidence
  threshold), never asserting the threshold reason unconditionally.
- **FR-9**: Analysis Studio renders the retrieval coverage envelope
  (`irac.retrieval.coverage_note` + queries searched) when present.

## 6. Non-Functional Requirements

- **NFR-SEC-1**: Throttle rate is environment-configurable and defaults to a
  real limit in production settings.
- **NFR-AUDIT-1**: No audit event is silently lost; JSONL remains the
  always-on record.
- **NFR-A11Y-1**: The disclaimer uses `role="note"` / `role="contentinfo"`
  with a labelled heading so screen readers announce it.

## 7. Data Model Impact

None.

## 8. API Surface

No new routes. `POST /api/analysis` and `POST /api/lsat/tutor` may now return
**429 Too Many Requests**.

## 9. Agent / Crew Impact

None directly; `core.provenance` (used by every agent) changes its
persistence strategy only.

## 10. Acceptance Criteria

- **AC-1**: The disclaimer is visible in Analysis Studio before any run and
  remains visible alongside rendered analysis.
- **AC-2**: With `irac.degraded`, the banner explains no engine ran and does
  **not** mention the 70% threshold.
- **AC-3**: With no structured flag set, the banner falls back to the
  confidence-threshold explanation.
- **AC-4**: The coverage envelope renders its note and the queries searched.
- **AC-5**: At a 1/min rate, a second `/api/analysis` call returns 429 while
  the first returns 200.
- **AC-6**: Read endpoints (`/api/lsat/sections`) are never throttled even at
  a 1/min `llm` rate.
- **AC-7**: `AnalysisView` and `TutorView` carry `throttle_scope == "llm"`;
  `GradeView` (deterministic) does not.
- **AC-8**: `base.REST_FRAMEWORK` ships a real `20/min` default.
- **AC-9**: The audit suite stays green with no `SynchronousOnlyOperation`
  warnings emitted from async agent paths.

## 11. LegalBench Impact

- Tasks affected: none (no reasoning or prompt change).
- Expected delta: 0 pp.

## 12. Risks & Open Questions

- **R-1**: The throttle is per-IP for anonymous clients; behind a shared
  proxy this can under-serve legitimate users. Revisit with user accounts.
- **R-2**: Under async+eager (tests/dev), `AuditEvent` rows are not written;
  JSONL is the record there. Production (non-eager) still lands rows via the
  Celery worker. Documented in the `_persist` docstring.
- **R-3**: Disclaimer wording is engineering-authored, not counsel-reviewed.

## 13. Out of Scope / Follow-ups

See `tasks.md` → `## Follow-ups Discovered` (mirrored into BACKLOG.md as
BL-20260811-05 … BL-20260811-08).
