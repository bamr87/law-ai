# Plan: Static LSAT solving-aid parity

- **Spec**: [spec.md](spec.md)
- **Status**: shipped
- **Approach**: move the data first, port the renderers second, then gate the drift so this is the last time it happens quietly.

## 1. Architecture

### The data was always portable

Solve guides are hand-authored JSON validated by Pydantic at load. Nothing about them needs a server — they were simply absent from `build_content()`. Adding them is four lines, and it is the whole reason the port is feasible:

```
guides.json (40, source of truth)
   └─ lsat_export.build_content()   ← spec 046 adds this hop
        └─ lsat-static/content.json  (bundled at build time)
             └─ guideFor(questionId) (synchronous, no fetch)
```

Only guides whose question shipped are emitted, sorted by id, so re-exports stay byte-identical apart from `generated_at` — the property `tests/test_lsat_site.py` gates on.

### Spoilers without a server

The platform strips spoiler steps in `public_guide_view` before they reach the browser. Offline there is nowhere to strip them, so the static build ships the whole guide and the **client** locks spoiler steps until `graded`.

That is not a weakening: `content.json` already contains every answer key, because the site cannot grade offline otherwise. The guide adds no secret the bundle did not hold. What matters is that the *experience* matches — a locked step shows its title and position so the learner knows how many remain, and unlocks in place on grading.

### Renderers, ported not shared

The six diagram/carousel components are re-implemented against semantic CSS rather than imported, because the static export is Tailwind-free and the platform's copies are utility-class-based. The markup, ARIA, and behaviour are carried across intact; only the class names change.

This is real duplication, and R13 is the answer to it: the file must exist on both sides or the divergence must be stated. What R13 deliberately does *not* do is assert the two behave identically — that would need a shared test harness the static site does not have (BL-20260831-18).

### Why the drift was invisible

Two independent failures, both fixed:

- The Pages deploy listed `backend/law_ai/lsat/services/data/**` in its path filter, so the spec 045 merge triggered a deploy that rebuilt the site **without changing it**. A green deploy that changes nothing is worse than no deploy.
- `ux_audit.py` gained both surfaces in spec 044 but only checks structure. R13 adds the feature-level question: does this component exist on the other side, and if not, why.

## 2. Files

```
backend/law_ai/lsat/management/commands/lsat_export.py   EDIT emit guides + counts
lsat-static/content.json                                 REGEN 40 guides (339 KB)
lsat-static/lib/types.ts                                 EDIT guide schema types
lsat-static/lib/data.ts                                  EDIT guideFor(), conceptById()
lsat-static/components/solve/SolveAssist.tsx             NEW  carousel, client-side locking
lsat-static/components/solve/ConceptRefs.tsx             NEW  bundle lookup, no fetch
lsat-static/components/solve/diagrams/*.tsx              NEW  5 renderers + dispatcher
lsat-static/components/QuestionCard.tsx                  EDIT mount both
lsat-static/app/globals.css                              EDIT semantic CSS for all of it
lsat-static/app/page.tsx                                 EDIT nav labels match the platform
frontend/components/lsat/{CrossCheckPanel,ValidationReport,SectionTimerWidget}.tsx
                                                         EDIT static-parity: none — <reason>
scripts/ux_audit.py                                      EDIT R13
.github/workflows/deploy-lsat-pages.yml                  EDIT honest path filter
```

## 3. Test strategy

`lsat-static` still has no test runner (BL-20260831-18), so verification is the audit, the backend suites, and a real build driven in a browser:

| Layer | Covers |
|-------|--------|
| `pytest tests/lsat`, `tests/test_lsat_site.py` | The exporter change and the content drift gate |
| `scripts/ux_audit.py` R13 | Every platform LSAT component is ported or declared |
| Static export build | Compiles; TypeScript clean; Tailwind-free (14 KB CSS, zero `--tw-`) |
| Headless Chromium on the artifact | Hint reveals step 1 with method + count; the 6-step LG guide walks Orient→Answer; sequence/notation/grid/argument-map/passage-map all render; the answer step is locked pre-grade with no reveal control, and unlocks in place after |
| `make test-frontend` | The platform's 157 tests still pass |

The grid is the interesting case: it sits on a **spoiler** step in `lg-001`, so it correctly refuses to render until the question is graded. Verifying it took grading first — which is itself the evidence that the client-side lock works.

## 4. Rollout

One commit. `make lsat-export` must be run whenever the source bank or guides change; the corrected path filter means the deploy now fires on exactly that artifact landing.

## 5. Risks

Carried from [spec.md](spec.md) §13. The one to keep in view: two implementations of one carousel, gated for existence but not for behaviour.
