# The LSAT static site (`lsat-static/`)

The LSAT module ships to learners through two surfaces. The platform Lab (`frontend/`, `/lsat`) talks to `/api/lsat/*` and carries everything that needs a backend: the tutor, authoring, the HITL proposals queue, validation. The **static site** is a serverless snapshot of the practice content — a Next.js app built with `output: 'export'` and published to GitHub Pages, with the whole question bank imported at build time so the published site makes zero network calls for content.

This document is the architecture-level description of that channel: what the app is, how content reaches it, what gates it, and which specs shaped it. The operator quickstart (local dev, npm scripts, deliberate divergences, the bundle-shard trigger) lives in [lsat-static/README.md](../lsat-static/README.md) and is not repeated here.



## Question-type playbooks (spec 053 / #126)

`content.json` schema **v4** adds a `playbooks` block:

```json
{
  "playbooks": {
    "strategies": [{ "id", "name", "sections", "summary" }],
    "traps": [{ "id", "name", "summary" }],
    "items": [{ "archetype_id", "name", "section", "family", "cues", "task", "strategies", "method", "traps", "confused_with" }]
  }
}
```

- **Source of truth:** `backend/law_ai/lsat/services/data/playbooks.json` via `public_playbook_view`.
- **Not exported:** raw `cue_patterns` (classifier-only). The static site looks up playbooks by stamped `Question.archetype`.
- **UI:** `SolveAssist` shows a playbook chip when an item guide exists; when no guide, it seeds the hint carousel from the playbook method (trap list stays spoiler-locked until graded).
- **Still lab-only:** Diagnose-first (`DiagnoseStep`) and `/lsat/playbooks` browser — those need the API exercise.

## Status: this replaced the buildless site of spec 025

[Spec 025](../specs/025-lsat-static-site/spec.md) shipped a hand-rolled, deliberately buildless app at `frontend/public/lsat-practice/` — three files (`index.html`, `styles.css`, `app.js`) deployed verbatim, with "must stay buildless" as an explicit non-goal-of-change. That directory no longer exists. It was rebuilt as the Next.js static export under `lsat-static/`, and spec 025's spec/plan/tasks are kept as the historical record of the first delivery, marked superseded, with this document as the current description (BL-20260716-11).

What carried over from 025: the delivery model (a static, serverless, HITL-approved content export on GitHub Pages), `content.json` as the single artifact, and the drift gate. What changed: the implementation is a real Next.js app with TypeScript, components and a Vitest suite, because feature parity with the Lab (solve guides, writing, the library, a section timer, full keyboard control) is not maintainable in one hand-written `app.js`.

## App layout

| Path | Contents |
|------|----------|
| `lsat-static/app/` | `layout.tsx`, `page.tsx` (the whole site is one client-side-tabbed page — there is no router), `globals.css`, and `base.css` mirrored from `frontend/ui/base.css` |
| `lsat-static/components/` | `Overview`, `Drill`, `Concepts`, `Library`, `Writing`, `Stats`, plus `QuestionCard`, `PassagePanel`, `SectionTimer`, `QuestionElapsed`, `ShortcutHelp`, `solve/` (`SolveAssist`, `ConceptRefs`, diagram renderers) and `library/BlockRenderer` |
| `lsat-static/lib/` | `data.ts` (the build-time `content.json` import + typed accessors), `types.ts`, `progress.ts` (device-local `localStorage` attempts — multiple choice only), `deviceState.ts` (every other key this site writes: library read marks, writing drafts and submissions, the header pin — found by prefix, since the writing keys are per prompt) and `backup.ts` (export/import over both), `search.ts`, `shuffle.ts`, `keyboard.ts`, and the primitives mirrored from the platform (`rovingFocus.ts`, `lsatTimer.ts`, `lsat/timerStore.ts`) |
| `lsat-static/__tests__/` | Vitest + RTL component tests, including `contracts/` shared with `frontend/` |
| `lsat-static/e2e/` | Playwright viewport/sticky measurements over the built export |
| `lsat-static/content.json` | The committed content artifact (see below) |

There is no compose service for it: nothing in the dev stack serves the static site, so both its build and its tests run in a throwaway `node:20-alpine` container.

## The delivery flow

1. **Source of truth** — JSON under `backend/law_ai/lsat/services/data/`: `lr_bank.json`, `rc_bank.json`, `lg_bank.json`, concepts, passages, solve guides, writing prompts and rubrics, and the knowledge library. Everything is read through the Pydantic loaders in `backend/law_ai/lsat/services/`, so only loader-valid content can ship.
2. **Export** — [`manage.py lsat_export`](../backend/law_ai/lsat/management/commands/lsat_export.py) writes one `content.json` carrying the complete HITL-approved module — including answer keys, explanations, spoiler guide steps and model writing responses, because the site grades and self-scores offline; the *client* keeps spoilers locked until the learner submits, mirroring `public_guide_view` / `public_prompt_view` on the API side. The payload is stamped with `schema_version` (currently `3`) and ordered deterministically, so re-exporting an unchanged bank is byte-identical apart from `generated_at`.
3. **Refresh the committed artifact** — `make lsat-export` runs the command in the backend container and copies `backend/var/lsat_site/content.json` over `lsat-static/content.json`. The artifact is committed deliberately: the Pages build has no database, no backend and no secrets. Running the target in the PR that changes the bank stays the better habit — the content diff is then reviewable next to its cause — but [refresh-lsat-content.yml](../.github/workflows/refresh-lsat-content.yml) is the backstop: on any push to `main` touching `backend/law_ai/lsat/services/data/**` it re-exports, commits only when the payload changed (it compares with `generated_at` removed, or it would commit forever), and explicitly dispatches the Pages deploy, since a `GITHUB_TOKEN` push raises no `push` event (BL-20260702-11).
4. **Gates** — [tests/test_lsat_site.py](../tests/test_lsat_site.py) in the root structural suite (`smoke` marker, CI job "Run root structural suite") fails when a source bank file changes without a matching export, when the bundle exceeds its size budget, and when the site's structure drifts. `make test-lsat-static` runs the site's own Vitest suite; the `lsat-static` job in [ci.yml](../.github/workflows/ci.yml) runs it plus `tsc --noEmit` whenever `lsat-static/**` changes.
5. **Deploy** — [deploy-lsat-pages.yml](../.github/workflows/deploy-lsat-pages.yml) fires on pushes to `main` touching `lsat-static/**` or the workflow itself, runs `npm ci && npm run build` with `PAGES_BASE_PATH=/<repo>`, sanity-checks and browser-measures `out/`, and uploads it to Pages. Source-bank paths are intentionally not triggers: a bank edit reaches the site only through step 3, and listing them produced no-op deploys that looked like content updates (spec 046).

**One-time repo setup**: Settings → Pages → Source: **GitHub Actions**. There is nothing else to provision.

## Keeping the two UIs in step

`make ui-sync` copies the shared primitives one way — platform → static — so the export cannot fork them: `frontend/ui/base.css`, `frontend/lib/shell/rovingFocus.ts`, `frontend/lib/lsatTimer.ts`, `frontend/lib/lsat/timerStore.ts`, and the `solveAssist` contract test. `make lsat-static-build` builds the export locally exactly as Pages does.

Parity is a **capability** contract, not a layout contract: the static site may render a surface differently (the library is one scrollable catalog here, a rail-and-reader in the Lab) as long as the learner can do the same things and the shared fragments (`#catalog-<id>`, `#article-<id>`) still resolve. The tutor and every authoring/HITL surface are excluded on purpose — they require the API — and the site says so where a learner meets the gap.

## Spec history

| Spec | What it did to this channel |
|------|-----------------------------|
| [025](../specs/025-lsat-static-site/spec.md) (superseded) | Established the serverless GitHub Pages channel, `content.json`, `make lsat-export` and the drift gate — as a buildless vanilla app under `frontend/public/lsat-practice/` |
| [044](../specs/044-static-site-ux-parity/spec.md) | UI/UX parity pass on the Next.js rebuild: shared tokens, layout and accessibility behaviour |
| [046](../specs/046-static-lsat-feature-parity/spec.md) | Solving-aid parity — solve guides and diagrams in the export (`guides` added to the payload), and the deploy-trigger fix |
| [047](../specs/047-lsat-continuous-curriculum/spec.md) | Argumentative Writing: `writing_prompts` + `writing_rubrics` in the payload, offline self-scoring against the rubric |
| [048](../specs/048-lsat-knowledge-library/spec.md) | Knowledge library shipped whole as compiled typed blocks (`library`, `library_tracks`), plus the bundle-size budget and the sharding plan |

See [docs/architecture.md](architecture.md#lsat-static-delivery-channel) for how this channel sits in the wider system, and [docs/ui-ux.md](ui-ux.md) for the surface inventory.
