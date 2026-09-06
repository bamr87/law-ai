# Plan: LSAT Static Practice Site

> **Superseded (2026-09-05, BL-20260716-11).** The buildless `frontend/public/lsat-practice/` app planned here was replaced by the Next.js static export under [`lsat-static/`](../../lsat-static/); the exporter, `make lsat-export` and the drift gate carried over unchanged. See [docs/lsat-static.md](../../docs/lsat-static.md) for the current architecture and [spec.md](spec.md) for the full supersession note. Kept as the historical record.

## Architecture

```
backend bank JSON  ──(manage.py lsat_export, Docker)──►  var/lsat_site/content.json
      │                                                         │  (make lsat-export cp)
      │  drift gate: tests/test_lsat_site.py                    ▼
      └───────────── compares ──────────────►  frontend/public/lsat-practice/data/content.json
                                                        │
                              Next dev server serves it verbatim at /lsat-practice/  (local verify)
                                                        │
                     .github/workflows/deploy-lsat-pages.yml uploads the folder as-is
                                                        ▼
                                        GitHub Pages (serverless practice app)
```

Key decisions:

1. **Commit the generated artifact, gate the drift.** CI never builds: the workflow uploads a committed folder, so Pages deploys are trivial and reviewable. The stdlib root test makes a stale `content.json` a hard CI failure — the classic generated-artifact-plus-drift-gate pattern (the repo cannot run Docker in the Pages workflow cheaply, and bank edits are infrequent).
2. **Site under `frontend/public/`.** Next serves `public/` verbatim, so the existing `make dev` / preview stack doubles as the local test bed for the static app with zero new services; the Pages artifact is the same directory, guaranteeing what you previewed is what ships.
3. **Buildless vanilla app.** One `index.html` + `styles.css` + `app.js` (ES2020, no deps). Hash routing keeps it single-file and base-path-agnostic (Pages serves under `/<repo>/`). Interaction/a11y patterns are ported from `LsatLab.tsx` (radiogroup, A–E/Enter with modifier guard, `aria-live` verdicts).
4. **Full model dumps, keys included.** The bank is public CC0 content already; client-side grading needs the key. `PublicQuestion` (the API's key-stripped view) is deliberately NOT used.
5. **Exporter validates through the loaders.** `load_bank()` etc. are the single source of truth — malformed data can't reach the artifact because the loaders raise.

## Module inventory

| File | Purpose |
|------|---------|
| `backend/law_ai/lsat/management/commands/lsat_export.py` | FR-1/FR-2 exporter |
| `backend/tests/lsat/test_export_site.py` | exporter unit tests (Docker) |
| `frontend/public/lsat-practice/index.html` | shell: header, nav tabs, view container, footer |
| `frontend/public/lsat-practice/styles.css` | dark-theme styles, focus states |
| `frontend/public/lsat-practice/app.js` | data load, hash router, views, grading, localStorage stats |
| `frontend/public/lsat-practice/.nojekyll` | disable Pages Jekyll pass |
| `frontend/public/lsat-practice/data/content.json` | committed generated artifact |
| `tests/test_lsat_site.py` | stdlib drift + structure gate (root suite) |
| `Makefile` (`lsat-export`) | Docker export + host copy |
| `.github/workflows/deploy-lsat-pages.yml` | Pages deploy |

## Testing strategy

- **Backend (Docker)**: exporter writes valid JSON; re-parses through `Question.model_validate`; deterministic ordering; counts match; `--out` honored.
- **Root suite (host stdlib)**: file structure, id/key/count parity bank↔artifact, choice-label integrity, passage linkage, relative-URL check on `index.html` (no leading-slash `src/href`).
- **Browser**: served statically, click through drill → grade → stats; keyboard path; RC/LG rendering (preview tools; AC-2/AC-3).
- **Review**: adversarial multi-agent pass over `app.js` for correctness/a11y/edge cases before ship.

## Rollout

Additive only. One-time manual step outside the repo: enable **Settings → Pages → Source: GitHub Actions** on the repository. First deploy happens on the next `main` push touching the site (or via `workflow_dispatch`).
