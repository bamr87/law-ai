# design-sync notes — law-ai

Repo-specific gotchas for future syncs. Read this before re-running.

## What this design system actually is

This repo ships **no component library** — no package, no `dist/`, no Storybook. The UI lives inside two Next.js apps:

- `frontend/` — the Law AI platform (Next 16, Tailwind v4, 10 exported components)
- `lsat-static/` — the static LSAT practice site (Next 16, hand-written CSS design system, 6 components)

`.design-sync/ds/` is a **synthetic package** created for the sync: `package.json` (name `law-ai-ui`), `entry.tsx` (named re-exports of both apps' default exports), a merged `tsconfig.json`, and the compiled `styles.css`. It is committed and is the converter's `--entry`. Keep `entry.tsx` and `componentSrcMap` in `config.json` in step with each other.

## Build commands

```sh
npm ci --prefix frontend && npm ci --prefix lsat-static     # both apps
mkdir -p .ds-sync && cp -r <skill>/{package-*.mjs,resync.mjs,lib,storybook} .ds-sync/
(cd .ds-sync && npm i esbuild ts-morph @types/react @tailwindcss/cli@4.2.4 playwright@1.56.0)
ln -sfn ../.ds-sync/node_modules .design-sync/node_modules   # per clone; Tailwind CLI resolves through it

# REGENERATE THE STYLESHEET whenever component classes or lsat globals.css change:
node .ds-sync/node_modules/@tailwindcss/cli/dist/index.mjs \
  -i .design-sync/ds/styles.src.css -o .design-sync/ds/styles.css

node .ds-sync/resync.mjs --config .design-sync/config.json \
  --node-modules ./frontend/node_modules --entry .design-sync/ds/entry.tsx --out ./ds-bundle
```

- `--node-modules` is **`frontend/node_modules`** — it has react/react-dom/next/cytoscape; lsat-static's deps are a subset.
- Docker is unavailable in this environment (daemon down) and the converter toolchain is host-only node anyway. This is out-of-band tooling, not one of the repo's Docker-first dev/test/lint gates — those rules are unaffected.
- Pin `@tailwindcss/cli` to the version in `frontend/package.json` (4.2.4). A newer CLI silently compiles with a different Tailwind and the utility output drifts.
- Playwright **1.56.0** is the version that pins chromium build **1194**, which is what `/opt/pw-browsers` has. The repo's own `@playwright/test` (1.59.x) pins 1217 and fails with "Executable doesn't exist".

## Fixes that are already in config — do not re-derive

- **`process is not defined`** — `frontend/lib/api.ts` reads `process.env.NEXT_PUBLIC_*` at module scope. `.design-sync/ds/process-shim.ts` installs a browser-safe `process`; it **must stay the first import in `entry.tsx`** (re-exports hoist above statements, so a bare assignment runs too late). Without it the IIFE throws on load and `window.LawAI` is never assigned — every preview goes blank.
- **`next/link` + `next/navigation`** — Next's client router reads `process.env.__NEXT_*` at module scope and needs an App Router runtime. Both are redirected to `.design-sync/ds/shims/` via `compilerOptions.paths` in `.design-sync/ds/tsconfig.json`. This also cut the bundle 1917 KB → 1558 KB. `usePathname()` reads `window.__LAWAI_PATHNAME`, which is how NavBar previews choose the active route.
- **Never put a `"//"` key in `.design-sync/ds/tsconfig.json`.** The converter's comment-stripper turns it into invalid JSON, `tsconfigPathsPlugin` silently returns `null`, and the `next/*` redirects stop working with no error. (The `@/*` aliases keep working regardless — esbuild finds each app's own tsconfig by walking up from the source file.)
- **`cfg.cssEntry` is bounded to the package dir**, unlike `tsconfig`/`docsDir`/`extraFonts` which are workspace-bounded. That is why the stylesheet lives at `.design-sync/ds/styles.css` and not in a sibling folder.
- **`cfg.provider` → `PreviewSurface`** (`.design-sync/ds/preview-surface.tsx`, re-exported from `entry.tsx`). The preview-card harness hard-codes `body{background:#fff}` in each card's own `<style>`, which beats the stylesheet. Without the wrapper, translucent surfaces and `var(--text)` text wash out on white. Preview-only — designs get the real `body` rule from `styles.css`.
- **Health fixture shape matters.** A *failed* fetch is caught and the panel hides; a *200 with the wrong shape* crashes `AgentDashboard` (`Cannot read properties of undefined (reading 'reachable')`). `LOCAL_AI_HEALTH` in `preview-mocks.ts` must keep matching `LocalAIHealth` in `frontend/lib/api.ts`.

## The Tailwind safelist — the important one

`frontend/` styles entirely with utility classes, so the shipped stylesheet is a **pre-compiled** Tailwind build. Tailwind only emits what it finds in the scanned sources, which means **a design agent composing new layouts gets unstyled output for any utility the apps don't already use**.

`.design-sync/ds/styles.src.css` therefore carries an `@source inline(...)` safelist covering the six ramps the DS uses (`slate blue emerald amber red indigo`) plus common spacing/layout/typography utilities. Stylesheet is ~893 KB as a result (from ~91 KB). Colours outside those six ramps still will not resolve — `conventions.md` tells the agent to stay inside them. If the product adopts a new colour family, add it to the safelist **and** to `conventions.md`.

`@source "../previews"` is also listed so preview-authored classes compile; without it `LegalDisclaimerBanner`'s `max-w-xs` cell rendered identically to the default.

## Previews

All 16 are authored in `.design-sync/previews/` and graded `good` (27 cells). Points worth keeping:

- **Data-driven screens are mocked**, not left in their error states. `.design-sync/ds/preview-mocks.ts` installs a path-matching `fetch` (longest prefix first) with Law AI fixtures. Call `installApiMock(ALL_ROUTES)` at module scope.
- **`AnalysisStudio.IracResult`** drives the component the way a user would — fills the textarea through the native value setter (React swallows a plain `.value` assignment), then clicks *Run analysis*. It scopes its queries to a `ref`, because every cell of a card renders into the same page and a bare `document.querySelector` would drive the sibling cell's form.
- **`Stats`** seeds `localStorage['lsat-practice.attempts.v1']` with **fixed** timestamps — using `Date.now()` would make captures non-deterministic.
- **`PassagePanel`** imports real passages from `../../lsat-static/lib/data` instead of copying them, so it can't drift from `content.json`.
- **Graph previews need ≥5–6 nodes.** Cytoscape's `cose` layout fits-to-viewport, so a 2–3 node graph zooms in far enough to blow the labels out of scale.

## Known render warns

None. The final validate run reports `16/16 previews render cleanly` with no warn lines. **Any warn on a future run is new** — investigate it rather than assuming it was always there.

## Re-sync risks — what can silently go stale

1. **The compiled stylesheet is generated but committed.** It does *not* regenerate as part of `resync.mjs`. If someone adds new utility classes to `frontend/` or edits `lsat-static/app/globals.css`, previews and designs keep using the stale CSS until the Tailwind command above is re-run. Run it first, every time.
2. **`entry.tsx` / `componentSrcMap` are hand-maintained.** A component added to either app will not appear in the DS until both are updated. Neither the converter nor validate will flag the omission.
3. **API fixtures are copies of response shapes.** `preview-mocks.ts` duplicates types from `frontend/lib/api.ts`. A backend shape change won't fail the build — it will crash or hollow a preview at capture time. `dtsPropsFor` in `config.json` is hand-written for the same reason: there is no shipped `.d.ts` tree to extract from, so **prop contracts drift silently** if a component's props change. Re-check `dtsPropsFor` against the sources on any sync that follows component edits.
4. **Only partially verified**: interaction-only states (hover, focus rings, the answered/explanation state of `QuestionCard`, the LsatLab tabs beyond Overview) are not covered — they can't be reached in a static card. `AnalysisStudio.IracResult` is the one exception and it is timing-based (60 ms), so it could in principle flake.
5. **Toolchain assumptions**: node 22, Tailwind CLI 4.2.4, playwright 1.56.0 + the preinstalled chromium 1194 at `/opt/pw-browsers`. All three are version-coupled to things outside this repo.
6. **Not uploaded.** This run produced a verified bundle but never reached a Claude Design project — `DesignSync` could not authorize in this environment, so there is **no `projectId` in `config.json` and no remote `_ds_sync.json` anchor**. The next sync that can authorize will therefore treat everything as new and re-verify all 16 components. That is the documented safe state, not a bug.
