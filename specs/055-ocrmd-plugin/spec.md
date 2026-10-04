# Spec: ocrmd as a plug-in — scanned pages as LSAT drafts and as matter documents

- **ID**: 055-ocrmd-plugin
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-09-06
- **Roadmap Epic**: physical books into the platform — a scanner rig or an upload becomes reviewable content, with the photograph always reachable
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md). §4: the embedded scanner makes **no** model call (its provider is `None`), so `law_ai.core.llm` stays the only choke point; the LSAT door's extraction already runs through it. §5: every LSAT draft still passes the spec-024 gates into the HITL queue; a matter document is the user's own upload on the user's own matter and touches no graph node. §8: one optional dependency group, licences noted in `backend/pyproject.toml`. §1: the plug-in runs wholly locally (RapidOCR on ONNX); nothing in it needs a third party.

## 1. Problem & Motivation

[ocrmd](https://github.com/bamr87/ocrmd) reads a photographed book page twice — local OCR engines and a vision model — and reconciles the readings, marking every disagreement rather than silently choosing. Its 0.8 draft of an outbound path was a law-ai module inside the scanner (`lawai_url`, a "→ LSAT" button with section and difficulty pickers) posting to `POST /api/lsat/intake/ocr`, which shipped here in the spec-051/052 sweep without a spec, without endpoint tests, and with the request shape hard-wired to that one button.

Two things were wrong with that. On the scanner's side it made a general-purpose tool know about LSAT questions; ocrmd 0.9 replaces the module with a generic *sink contract* (descriptor on `GET`, envelope on `POST`) and expects every receiver to describe itself. On this side there was only one door: a page could become a question draft and nothing else, so a scanned lease, a treatise page or a set of notes had no way into a matter — the platform's own container for source material — and a person without a scanner rig could not OCR an upload at all.

## 2. Origin & Background

- Backlog items claimed: none — direct request ("law-ai should be able to install ocrmd as a plug-in that can use the OCR capabilities and process them further into LSAT questions, or be captured as documentation for further legal/analysis processing").
- Prior art: the scanned-page intake in `lsat/services/ocr_intake.py` and `LSATSourceExtractor` (grounding floor 0.75, `page_id` = sha256 of the processed image), the matters spine (spec 036), the quarantine model and source adapters (specs 004, 018), the `nlp` extra as the precedent for an optional-but-installable capability (BL-20260429-03).
- **Review question (constitution §13)** — *who is the stronger here, and what does this feature do for them?* The scanner's operator is the stronger party in this feature: they choose what enters and where it lands. The design gives them no standing over the record — a scanned page is labelled as a scanned source with a machine agreement figure, never as authority, and the publisher whose book was photographed gains none either. This feature does not rank, score, or summarise legal authority. It moves a page's text into the platform with its provenance attached and lets a human decide what it is. A scanned book is *secondary* material: nothing here presents a textbook's paraphrase as a holding — a matter document is labelled as a scanned source with the scanner's own agreement score, never as authority, and never enters the graph or the retrieval boost set.

## 3. Goals

- G1: Law AI is a receiver in ocrmd's sink contract, twice: an LSAT door and a matter door, each self-describing.
- G2: ocrmd installs into the backend as an optional extra and can OCR an upload inside the platform, honestly labelled as one reading.
- G3: Every path keeps the way back to the photograph (`page_id`, `document`, `page`, `bbox`) and every model call stays inside `core.llm`.
- G4: The existing intake keeps working for anything that posted to it before.

## 4. Non-Goals

- NG1: A vision path through the provider chain (the cross-check inside Law AI). Follow-up BL-20260907-21.
- NG2: A frontend for uploads or for browsing scanned pages. Follow-up BL-20260907-22.
- NG3: A graph node for scanned sources, or a `PendingReview` kind for them. A scanned book page is the user's material, not a public data source; follow-up BL-20260907-23 records the case for a `:SourceDocument` node.
- NG4: Installing ocrmd in the default image. It is pinned to a git ref and brings opencv; it is an opt-in build.
- NG5: Asynchronous scanning. The upload door is bounded (`OCRMD_MAX_PAGES`); a book goes through a scanner rig.

## 5. User Stories

- As a student with a prep book under a webcam, I want to press one button on a page and have its questions land in the review queue, with the page id attached so a reviewer can look at the photograph.
- As a lawyer scanning a lease, I want the page filed on my matter as a source document, with the scanner's provenance, and never mistaken for authority.
- As an operator without a rig, I want to upload one photographed page and have Law AI read it locally and route it, and be told plainly that it was read once, not cross-checked.
- As a contributor, I want the two doors to share one envelope model and one descriptor shape, so a third door is a page of code.

## 6. Functional Requirements

- **FR-1**: `GET /api/lsat/intake/ocr` answers with a sink descriptor: `ocrmd_sink: 1`, a name, a description, `accepts`, and typed options `hint` (string), `section` (enum LR/RC/LG), `difficulty` (enum), `max_items` (integer, default 5).
- **FR-2**: `POST /api/lsat/intake/ocr` accepts the ocrmd envelope (`ocrmd`, `kind`, `text`, `provenance`, `document`, `options`) and still accepts the legacy shape (`source_text` + top-level `hint`/`section`/`difficulty`); a section outside the multiple-choice set is a 422, not a 500.
- **FR-3**: The LSAT door's response carries `summary`, `items` (one per accepted draft: id, stem, detail, `status: pending`) and `warnings` (ungrounded and gate-rejected drafts), on top of the fields it always returned; the proposal's `meta.source` gains `tool_version`, `unresolved`, `page_url`, `document_title`.
- **FR-4**: `GET/POST /api/matters/<slug>/intake/ocrmd`, signed-in and owner-scoped like every matter route: the descriptor with `title` and `note` options, and the envelope filed as a `document` artifact (`source="ocrmd"`, `confidence` = the scanner's agreement, text/provenance/catalogue entry in `body`).
- **FR-5**: Filing the same page (and region) twice on a matter answers 200 with the artifact already made; a region with a different `bbox` is its own filing.
- **FR-6**: The matter door's answer names the scanner's caveats as `warnings`: a page with no model reading, a page the scanner marked suspect/illegible/blank, unresolved disagreements.
- **FR-7**: `backend/pyproject.toml` declares an `ocrmd` extra (ocrmd at a git ref, RapidOCR, ONNX Runtime, pymupdf); the Dockerfile installs it only when the build arg `INSTALL_OCRMD=1` is set, adding the libGL/glib packages opencv needs; `docker-compose.yml` passes the arg to `backend` and `worker`.
- **FR-8**: Settings `ENABLE_OCRMD` (default false), `OCRMD_ROOT` (default `var/ocrmd`), `OCRMD_MAX_PAGES` (default 5), declared in `settings/base.py` and documented in `.env.example`.
- **FR-9**: `GET /api/ingestion/ocrmd/status` reports enabled/installed/version/root/engines/doors; `POST /api/ingestion/ocrmd/scan` (multipart `file`, `doc`, `target` = none | lsat | matter:<slug>, `options`, `max_pages`) OCRs the upload with `ocrmd.api.Library(provider=None)` and routes each page to the named door; 503 when off or absent, 422 for a bad upload, 401/404 for a matter target without an owner.
- **FR-10**: `manage.py ocrmd_scan PATH... --doc X [--target lsat|matter:<slug> --user U] [--options JSON]` does the same from the container.
- **FR-11**: The embedded scanner never calls a model: every page it produces carries `llm_model: ""`, `status: unverified`, blank `image_url`/`page_url` and a `store_root`, and the scan response says `llm: none`.

## 7. Non-Functional Requirements

- **NFR-PERF-1**: The upload door is synchronous and bounded by `OCRMD_MAX_PAGES`; a scan writes into a temporary directory and the scanner's own store under `OCRMD_ROOT`, never into the request thread's memory beyond one file.
- **NFR-SEC-1**: No new outbound HTTP from this repo; the scanner's own store is confined to `OCRMD_ROOT`; uploads are limited to image and PDF suffixes; the document slug is validated.
- **NFR-AUDIT-1**: Every door writes a provenance event — `lsat_ocr_intake` (existing), `ocrmd_intake` with `door: matter`, `ocrmd_scan` for the embedded scanner — and the LSAT door keeps its `audit_store` record.
- **NFR-HITL-1**: `human_approval_required: true` for the LSAT door (unchanged: every draft is a pending proposal). The matter door needs no gate: it is a user's own document on their own matter, no analysis, no graph write. The embedded scanner has no output path of its own — it only feeds the two doors.
- **NFR-DOCS-1**: `docs/data-sources.md` gains a row and a section for scanned physical books (licence posture: the user's own copies, never redistributed, never in a public export); `docs/architecture.md` describes the plug-in; `CLAUDE.md` points at it.

## 8. Data Model Impact

No Neo4j change. No new Postgres table: the matter door writes `MatterArtifact` rows (`kind=document`, `source=ocrmd`), the LSAT door writes proposals as before. The scanner's own SQLite store lives under `OCRMD_ROOT` and is ocrmd's, not this schema's.

## 9. API Surface

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/lsat/intake/ocr` | — | sink descriptor |
| POST | `/api/lsat/intake/ocr` | `IngestScanRequest` (envelope or legacy) | `IngestScanResult` + `summary`/`items`/`warnings`, 202 |
| GET | `/api/matters/<slug>/intake/ocrmd` | — | sink descriptor |
| POST | `/api/matters/<slug>/intake/ocrmd` | `Envelope` | `{summary, items, warnings, artifact, created}`, 201 / 200 |
| GET | `/api/ingestion/ocrmd/status` | — | `ocrmd_plugin.status()` |
| POST | `/api/ingestion/ocrmd/scan` | multipart | `{document, engine, llm, summary, pages, routed, …}` |

## 10. Agent / Crew Impact

`LSATSourceExtractor` is invoked unchanged by the LSAT door. No new agent. The embedded scanner is a library call, not a crew, and makes no model call.

## 11. Acceptance Criteria

- **AC-1**: Given ocrmd probes the LSAT door, when it GETs, then it receives a descriptor whose `section` option lists exactly LR, RC, LG.
- **AC-2**: Given an envelope for a page with one question, when posted with `options.hint`, then the response is 202 with `summary` starting "1 question(s) queued" and the proposal's `meta.source.page_id` equals the envelope's; posted again, `accepted` is empty and `warnings` names the duplicate gate.
- **AC-3**: Given the legacy body, when posted, then 202 with a `summary`.
- **AC-4**: Given a signed-in owner, when an envelope is posted to their matter's door, then a `document` artifact with `source="ocrmd"` and the scanner's confidence exists and the matter detail lists it; posted again, 200 "already filed"; a stranger gets 404 and an anonymous caller 401.
- **AC-5**: Given an envelope with no `llm_model`, when filed on a matter, then `warnings` contains "one reading only".
- **AC-6**: Given `ENABLE_OCRMD=false`, when `/api/ingestion/ocrmd/scan` is posted, then 503 naming the flag; given the flag on and the package absent, 503 naming `INSTALL_OCRMD`.
- **AC-7**: Given the scanner stubbed, when a PNG is uploaded with `target=lsat` (resp. `matter:<slug>`), then `routed[0].door` is `lsat` (resp. `matter`) with that door's summary, and the response says `llm: none`.
- **AC-8**: `scan_file` drives the library with `llm=False`, closes it, and blanks the envelope's `image_url`/`page_url` while setting `store_root`.
- **AC-9**: `make lint`, `make typecheck` (strict-clean new modules) and `make test-backend` are green.

## 12. LegalBench Impact

- Tasks affected: none. No reasoning logic changes.
- Expected delta: 0 pp.

## 13. Risks & Open Questions

- **R-1**: A scanned page filed on a matter could be read by a later feature as authority. Mitigation: `source="ocrmd"` and `confidence` = the scanner's agreement, the artifact kind is `document`, and it never enters `MatterAuthority` or the boost set without a human recording it there.
- **R-2**: The git-pinned dependency makes the opt-in build depend on GitHub and on ocrmd's `main`. Mitigation: opt-in only, default image unchanged; BL-20260907-24 tracks pinning to a release.
- **R-3**: Copyright. A prep book photographed by its owner and OCR'd for their own review is their own use; the platform stores the text on their account, never redistributes it, and excludes it from any public export. `docs/data-sources.md` records this posture; it is not a licence row.

## 14. Out of Scope / Follow-ups

See `tasks.md` → Follow-ups Discovered.
