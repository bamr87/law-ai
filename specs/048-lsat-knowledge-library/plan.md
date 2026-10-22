# Plan: LSAT Knowledge Library

> Implementation plan for [spec.md](spec.md). Slices ship in order; one slice = one PR.

## 1. Architecture Overview

The library is a fifth content type in the LSAT module, sitting beside questions, passages, guides and writing prompts. It follows the module's established shape exactly — file-backed content, Pydantic models, lazy `lru_cache` loaders that fail loudly on cross-reference drift, a public view helper, an exporter into `content.json`, and an HITL-gated agent that can only ever propose.

```
data/library/*.md ──► library.py ──┬──► /api/lsat/library/*        ──► frontend/  (reader route)
    (30+ articles)   (parse+validate)│
data/library_tracks.json ───────────┴──► lsat_export ──► content.json ──► lsat-static/ (offline reader)
                                     │
                                     └──► library_audit()  ──► lsat_library audit  ──► health report
                                                              lsat_library review ──► LSATLibrarian
                                                                                        │ (HITL)
                                                                                        ▼
                                                                                    proposals.jsonl
```

The one genuinely new piece of machinery is the **parser**. An article is authored as Markdown because that is what a human reviews and an agent patches surgically, but neither client ever sees Markdown: `library.py` compiles the body into a typed block list at load time, and both products render *blocks*. That single decision buys three things — no Markdown dependency in either frontend, no `dangerouslySetInnerHTML` anywhere (NFR-SAFETY-1), and one shared rendering contract that a new block type must satisfy on both products before it can ship (FR-11).

Cross-references are typed inline spans rather than text conventions, so `[[concept:negation-test]]` is resolved and validated at load, not hopefully-matched at render.

## 2. Component Changes

| Component | Change |
| --------- | ------ |
| `backend/law_ai/lsat/services/library.py` | **New.** Models, frontmatter + Markdown parsers, loaders, search, audit, public view. |
| `backend/law_ai/lsat/services/data/library/*.md` | **New.** The corpus. |
| `backend/law_ai/lsat/services/data/library_tracks.json` | **New.** Curated reading paths. |
| `backend/law_ai/lsat/urls.py` | Five new read-only views under `/api/lsat/library`; `ConceptDetailView` gains `taught_in`. |
| `backend/law_ai/lsat/management/commands/lsat_export.py` | Ships `library` + `library_tracks`; `SCHEMA_VERSION` 2 → 3. |
| `backend/law_ai/lsat/management/commands/lsat_library.py` | **New.** `audit` / `review` / `promote`. |
| `backend/law_ai/agents_runtime/crews/lsat_librarian.py` | **New.** `LSATLibrarian.run()`. |
| `backend/law_ai/agents_runtime/prompts/lsat_librarian.v1.md` | **New.** Versioned prompt. |
| `frontend/lib/api.ts` | Typed client for the five endpoints. |
| `frontend/components/lsat/library/*` | **New.** Reader, contents rail, outline, search, block renderer. |
| `frontend/app/(app)/lsat/library/page.tsx` | **New.** Route. |
| `frontend/lib/modules/catalog.ts` | LSAT module sidebar gains the Library link. |
| `lsat-static/lib/types.ts`, `lib/data.ts`, `lib/search.ts` | Library types, accessors, offline index. |
| `lsat-static/components/Library.tsx` + `components/library/*` | **New.** Offline reader at parity. |
| `lsat-static/app/page.tsx`, `app/globals.css` | Library destination + reading-layout styles. |
| `Makefile` | `lsat-library-audit`, `lsat-library-review`. |
| `tests/test_lsat_site.py` | Library drift + no-raw-HTML + renderer-parity gates. |

## 3. Data & Schema Migrations

None in any database. `content.json` `schema_version` goes 2 → 3; both consumers already treat missing keys as "older artifact", so the bump is additive and a stale bundle degrades to no-library rather than breaking.

## 4. Tech Choices & Alternatives

- **Markdown source, typed-block runtime.** Alternative: store articles as JSON like every other
content file. Rejected — long prose in JSON strings is unreviewable in a diff and impossible for an agent to patch surgically, which is the whole point of the maintenance loop.
- **Hand-rolled restricted parser over a Markdown library.** Alternative: add `markdown-it-py` on
the backend or `react-markdown` on both clients. Rejected — a general parser's output is HTML, which forces raw-HTML rendering on two clients and a sanitiser on each; and `lsat-static` is deliberately a three-dependency project. The dialect we need is small and closed.
- **Server-side parse, client-side render.** The parse happens once at load/export; clients receive blocks. Keeps both frontends free of parsing logic and guarantees they agree.
- **Reuse `proposals.py` rather than a new store.** The HITL review path, audit trail and promotion semantics already exist and are tested; the library adds proposal *kinds*, not a parallel system.
- **Computed `reading_minutes`.** A declared value drifts the moment an agent expands a section.

## 5. Provenance & Audit Hook-up

- `LSATLibrarian.run()` writes exactly one `provenance.log_agent_call` per run (agent name, action, target article, model, latency, confidence, degraded flag) — including on the degraded path.
- The model call itself is logged as `llm_call` by `law_ai.core.llm`; the agent never touches a provider transport.
- Proposal creation, status transitions and promotion are recorded by `proposals.py` in its append-only JSONL, as they are for questions and guides.
- Library reads are content reads, not model calls, and are not separately audited — consistent with `/api/lsat/concepts`.

## 6. HITL Gates

- `LSATLibrarian.human_approval_required = True`.
- Every librarian output persists as a `pending` proposal (`library_finding` / `library_article`).
- `lsat_library review` never writes to `data/library/`. `lsat_library promote` is the only path
that does, it takes an explicit proposal id, and it re-runs the full loader validation before writing so a promoted draft cannot break the load.
- The scheduled cycle runs `review` only. A human decides everything else.

## 7. Test Strategy

| Layer | Coverage |
| ----- | -------- |
| Parser unit tests | Every block type, every inline span, and one failing case per rule in FR-2/FR-3/FR-4. |
| Loader tests | Cross-reference integrity, prerequisite cycle detection, computed reading time, duplicate ids. |
| Corpus tests | Article count floor, per-kind and per-section coverage, every concept-teaching claim resolves. |
| API tests | Index filters, detail resolution, 404, search ranking + 422, health shape. |
| Export tests | Library present, ordering stable, byte-identical re-export. |
| Agent tests | Each action's output shape; degraded fallback with no provider; provenance event written; nothing written to `data/library/`. |
| Frontend tests | Block renderer per block type, outline generation, search behaviour, no `dangerouslySetInnerHTML`. |
| Root suite | Drift gate, renderer parity, static-site structure. |

## 8. Rollout

Five slices, in order:

1. **Content model + parser** — `library.py`, tests, three seed articles proving the dialect.
2. **Corpus** — the remaining articles and the tracks file.
3. **API + export** — endpoints, exporter, drift gate.
4. **Reading surfaces** — platform reader, then static reader at parity.
5. **Maintenance loop** — audit, agent, command, schedule.

Slice 3 deliberately precedes slice 4 so both clients build against a frozen wire shape, and slice 5 comes last so the agent operates on a corpus that already has a working reader to review it in.

## 9. Risks & Mitigations

| Risk | Mitigation |
| ---- | ---------- |
| Parser complexity creeps toward a real Markdown implementation | The dialect is documented and closed; anything unrecognised is an error, so scope creep shows up as a failing load rather than as silent partial support. |
| Bundle growth (spec R1) | Export profile support from spec 047 FR-15; library shards out if the full profile exceeds budget. |
| Agent prose drifting from exam fact (spec R3) | HITL promotion, staleness in the audit, references required on structural claims. |
| Two renderers diverging (spec R4) | Shared block-type contract plus a root-suite parity test. |
| Article ↔ concept drift as the concept catalog changes | Load-time resolution: a renamed concept id breaks the load and CI, not the page. |

## 10. Estimated Effort

| Slice | Scope | Estimate |
| ----- | ----- | -------- |
| 1 | Model + parser + loader + tests | ~1.5 days |
| 2 | 30+ articles + tracks | ~3 days |
| 3 | API + export + drift gate | ~0.5 day |
| 4 | Two reading surfaces at parity | ~2 days |
| 5 | Audit + agent + command + schedule | ~1.5 days |
