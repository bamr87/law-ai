# LSAT Practice — static site (`lsat-static`)

A **Next.js static export** of the LSAT exercises only, deployed to GitHub Pages. It is fully serverless: `next build` with `output: 'export'` emits a static `out/` directory with no Node server and no API. The question bank is imported at build time from [`content.json`](content.json), so the published site makes zero network calls for content.

This replaces the earlier hand-rolled vanilla site that used to live at `frontend/public/lsat-practice/`.

## What's in it

- **Overview** — the three LSAT sections (LR / RC / LG) with format, timing, and
  strategy tips.
- **Drill** — question-by-question practice per section; 35-minute section timer
with per-question pacing and elapsed readout; accessible answer-choice radiogroup (roving tabindex, arrow selection-follows-focus, Enter submits), instant key + explanation, RC/LG passage & game context.
- **Concepts** — a searchable glossary of recurring reasoning patterns.
- **Stats** — per-section accuracy from `localStorage` (device-local, private).

The LLM tutor and the authoring / HITL review surfaces of the full app are **intentionally excluded** — they require the backend API and cannot run on a static host.

## Data source (single source of truth)

`content.json` is the HITL-approved bank artifact produced by the backend exporter and refreshed with:

```bash
make lsat-export     # runs `python manage.py lsat_export` and writes lsat-static/content.json
```

`tests/test_lsat_site.py` (part of the root structural CI suite) gates this file against the source bank under `backend/law_ai/lsat/services/data/` — the site can never silently lag the approved content.

## Local development

```bash
cd lsat-static
npm install
npm run dev            # http://localhost:3000
npm run build          # static export → out/
```

The build serves under a base path for GitHub project Pages (`https://<owner>.github.io/<repo>/`). It defaults to `/law-ai`; override with `PAGES_BASE_PATH` (e.g. `PAGES_BASE_PATH="" npm run build` for a root/custom domain).

## Deployment

Pushed automatically by [`.github/workflows/deploy-lsat-pages.yml`](../.github/workflows/deploy-lsat-pages.yml) on `main` when `lsat-static/**` or the LSAT source bank changes: it runs `npm ci && npm run build` and publishes `out/` to GitHub Pages.

One-time repo setup: **Settings → Pages → Source: "GitHub Actions"**.
