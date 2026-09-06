# LSAT Practice — static site (`lsat-static`)

A **Next.js static export** of the LSAT exercises only, deployed to GitHub Pages. It is fully serverless: `next build` with `output: 'export'` emits a static `out/` directory with no Node server and no API. The question bank is imported at build time from [`content.json`](content.json), so the published site makes zero network calls for content.

This replaces the earlier hand-rolled vanilla site that used to live at `frontend/public/lsat-practice/`.

## What's in it

- **Overview** — the three LSAT sections (LR / RC / LG) with format, timing, and
  strategy tips.
- **Drill** — question-by-question practice per section; 35-minute section timer
with per-question pacing and elapsed readout; accessible answer-choice radiogroup (roving tabindex, arrow selection-follows-focus, Enter submits), instant key + explanation, RC/LG passage & game context.
- **Concepts** — a searchable glossary of recurring reasoning patterns.
- **Stats** — per-section accuracy from `localStorage` (device-local, private), plus **export / import**: a versioned JSON snapshot of attempts, library read marks and writing drafts, restorable by merge or replace, because device-local storage is lost with the device and discarded by private browsing (BL-20260702-10).

The LLM tutor and the authoring / HITL review surfaces of the full app are **intentionally excluded** — they require the backend API and cannot run on a static host. The published site says so itself, in a collapsed "What this site does not have" note under the Overview intro and again in `SolveAssist`'s no-guide empty state, so the gap is stated where a learner meets it rather than only here (BL-20260831-25).

## Where this diverges from the platform library, on purpose

The platform's concept catalog (`frontend/components/LsatLibrary.tsx`) is a rail plus a reader: one concept on screen at a time. This site renders the whole catalog as a single scrollable list of cards. That divergence is deliberate and is not a gap to be closed: three dependencies, no client router, and an offline reader who wants to skim the vocabulary end to end is better served by one scrollable page than by a second navigation surface to learn. **Capability is the contract; layout is not** (BL-20260905-04).

The one capability that did have to match is per-concept linking. Every card carries `id="catalog-<id>"` and a permalink beside its heading, and `Library.tsx` reads the URL fragment on mount and on `hashchange` — so `#catalog-<id>` opens the catalog on that concept and `#article-<id>` opens the reader on that article, the same fragments the platform's `hashTarget()` uses. If a rail-and-reader layout is ever actually wanted here, that is a new decision to make with users, not a defect to fix.

## Data source (single source of truth)

`content.json` is the HITL-approved bank artifact produced by the backend exporter and refreshed with:

```bash
make lsat-export     # runs `python manage.py lsat_export` and writes lsat-static/content.json
```

`tests/test_lsat_site.py` (part of the root structural CI suite) gates this file against the source bank under `backend/law_ai/lsat/services/data/` — the site can never silently lag the approved content.

That gate turns a forgotten export into a red build on whatever PR happens to come next, which is a poor place to discover it. So the refresh is automated too: [`.github/workflows/refresh-lsat-content.yml`](../.github/workflows/refresh-lsat-content.yml) re-runs the exporter whenever a change under `backend/law_ai/lsat/services/data/` lands on `main`, commits `content.json` if the *content* actually moved, and then dispatches the Pages build (`BL-20260702-11`).

Two details that make it safe rather than noisy. Every export stamps a fresh `generated_at`, so the workflow compares the payload with that key removed — otherwise it would commit on every run forever. And a push made with `GITHUB_TOKEN` raises no `push` event, so the Pages deploy is dispatched explicitly instead of being left to trigger itself.

Running `make lsat-export` in your own PR is still the better habit: the content diff is then reviewable alongside the change that caused it, rather than arriving as a separate bot commit on `main`.

### Bundle size, and when to shard it

The whole bank ships as one build-time import, which is what buys the site its one genuinely unusual property: **zero network calls for content**. That is worth keeping, so `content.json` is not split pre-emptively — but "we will split it if it keeps growing" is a promise nobody is holding unless something measures the growth, so the root suite does (BL-20260831-24).

`TestLibraryDrift` fails hard at a 1.5 MB budget, and at two thirds of it (1 MB) `test_the_shard_trigger_names_what_actually_grew` fails with the per-key breakdown and names the largest key. That indirection matters: the item that asked for this was filed when solve guides doubled the bundle and proposed sharding *guides*, and guides are no longer what is large. Measured on the current export (840 KB), it is `library` 43%, `questions` 28%, `guides` 10%. Splitting guides today would cost the offline-first property and recover a tenth of the file.

When the trigger does fire, the shape is already decided (spec 048 R1): have `lsat_export` emit the largest key per id under `lsat-static/public/content/<key>/<id>.json`, keep the index and metadata in `content.json`, and fetch on demand from `lib/data.ts` behind a small in-memory cache. The drift and byte-stability gates need extending to the shard directory at the same time.

## Local development

```bash
cd lsat-static
npm install
npm run dev            # http://localhost:3000
npm run build          # static export → out/
```

The build serves under a base path for GitHub project Pages (`https://<owner>.github.io/<repo>/`). It defaults to `/law-ai`; override with `PAGES_BASE_PATH` (e.g. `PAGES_BASE_PATH="" npm run build` for a root/custom domain).

## Tests

Component tests run on Vitest + React Testing Library + jsdom, the same toolchain as `frontend/`, configured in [`vitest.config.ts`](vitest.config.ts) and [`vitest.setup.ts`](vitest.setup.ts) and kept under [`__tests__/`](__tests__/). They dispatch real key events against the mounted components, so the keyboard contract is verified behaviourally rather than by the source-string assertions the root suite used to rely on.

```bash
make test-lsat-static   # from the repo root: Docker-first, node:20-alpine, node_modules on a named volume
npm test -- --run       # from lsat-static/, if you already have node_modules locally
```

CI runs the same suite (plus `tsc --noEmit`) in the `lsat-static` job of [`ci.yml`](../.github/workflows/ci.yml) whenever `lsat-static/**` changes.

## Deployment

Pushed automatically by [`.github/workflows/deploy-lsat-pages.yml`](../.github/workflows/deploy-lsat-pages.yml) on `main` when `lsat-static/**` (or the workflow itself) changes: it runs `npm ci && npm run build` and publishes `out/` to GitHub Pages. Source-bank paths under `backend/law_ai/lsat/services/data/` are deliberately **not** triggers here — a bank edit reaches the site only once `content.json` is refreshed (spec 046); listing them produced no-op deploys that looked like the site had updated when it had not. [`refresh-lsat-content.yml`](../.github/workflows/refresh-lsat-content.yml) is what watches those paths, and it dispatches this workflow after it commits. See [docs/lsat-static.md](../docs/lsat-static.md) for the full delivery channel.

One-time repo setup: **Settings → Pages → Source: "GitHub Actions"**.
