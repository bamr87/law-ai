# Tasks: ocrmd as a plug-in

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). CI's `spec_validator.py` enforces that every requirement is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — The shared envelope, descriptor and embedded-scanner module

- **Refs**: FR-9, FR-11, NFR-SEC-1, NFR-AUDIT-1, AC-6, AC-8
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `backend/law_ai/ingestionapp/services/ocrmd_plugin.py` (new)
- **Steps**: `Provenance`/`DocumentMeta`/`Envelope` (extra ignored, `text` non-empty), `is_envelope`, `option`/`descriptor`; `enabled`/`installed`/`version`/`root`/`status`; `library()` → `ocrmd.api.Library(root, provider=None)` or `OcrmdUnavailable`; `scan_file` → envelopes with blank image/page URLs and `store_root`, an `ocrmd_scan` provenance event.
- **Verify**: `backend/tests/ingestion/test_ocrmd_plugin.py::TestEnvelopeModel`, `::TestStatus`, `::TestScanFile`; `mypy --strict` clean.

## T-002 — The LSAT door speaks the contract

- **Refs**: FR-1, FR-2, FR-3, NFR-HITL-1, AC-1, AC-2, AC-3
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/services/ocr_intake.py`, `backend/law_ai/lsat/urls.py`
- **Steps**: `INTAKE_DESCRIPTOR`; `IngestScanRequest._accept_envelope` (before) and `_only_keyed_sections` (after); `ScanProvenance` gains `tool_version`/`unresolved`/`page_url`/`document_title`; `_summarise` fills `summary`/`items`/`warnings`; `ScanIntakeView.get`.
- **Verify**: `backend/tests/lsat/test_ocr_intake_envelope.py`; the extractor tests still pass.

## T-003 — The matter door

- **Refs**: FR-4, FR-5, FR-6, NFR-AUDIT-1, AC-4, AC-5
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `backend/law_ai/matters/services/scanned.py` (new), `backend/law_ai/matters/urls.py`
- **Steps**: `matter_descriptor`, `find_filed` (page id + bbox), `file_page` (a `document` artifact, `source="ocrmd"`, two provenance events), `delivery` (summary/items/warnings/artifact/created); `MatterOcrmdIntakeView` on `<slug>/intake/ocrmd`.
- **Verify**: `backend/tests/matters/test_ocrmd_intake.py`; `test_matters_api.py` unchanged and green.

## T-004 — The upload door and the management command

- **Refs**: FR-9, FR-10, FR-11, NFR-PERF-1, NFR-SEC-1, AC-6, AC-7
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `backend/law_ai/ingestionapp/urls.py`, `backend/law_ai/ingestionapp/management/commands/ocrmd_scan.py` (new)
- **Steps**: `OcrmdStatusView`, `OcrmdScanView` (multipart; `_plugin_gate`, `_parse_scan_request`, `_owned_matter`, `_route_page`, `_page_row`); the command with `--target`/`--user`/`--options`/`--json`.
- **Verify**: `backend/tests/ingestion/test_ocrmd_plugin.py::TestScanRoute`, `::TestCommand`.

## T-005 — Settings, packaging, the opt-in build

- **Refs**: FR-7, FR-8, NFR-SEC-1
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `backend/law_ai/settings/base.py`, `.env.example`, `backend/pyproject.toml`, `backend/Dockerfile`, `docker-compose.yml`
- **Steps**: three settings declared and bound; the `ocrmd` extra with licences noted; `ARG INSTALL_OCRMD=0` and a conditional layer adding libGL/glib and the extra; compose passes the arg to `backend` and `worker`; `ocrmd.*` in the mypy ignore list.
- **Verify**: `docker compose config --quiet`; the default build is unchanged; `INSTALL_OCRMD=1 docker compose build backend` installs the extra (follow-up BL-20260907-25 exercises it with a real engine).

## T-006 — Docs, gates, backlog

- **Refs**: NFR-DOCS-1, AC-9
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `docs/data-sources.md`, `docs/architecture.md`, `CLAUDE.md`, `BACKLOG.md`
- **Steps**: the scanned-books row and section; the plug-in in the component table and its own subsection; the CLAUDE.md paragraph; follow-ups mirrored.
- **Verify**: `make lint-specs`; `make lint`, `make typecheck`, `make test-backend` green.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `make lint && make test` green.
- LegalBench delta recorded in PR description (n/a — no reasoning change).
- Provenance logging verified manually for new agent paths (no new agent; three event types added).
- **`## Follow-ups Discovered` section below populated**.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- BL-20260907-21 — feature, med — An image path through `law_ai.core.llm` (`LLMRequest.images` across the four transports), so ocrmd's vision cross-check can run inside Law AI through the §4 choke point instead of OCR-only.
- BL-20260907-22 — feature, med — A frontend for the plug-in: an upload panel (`POST /api/ingestion/ocrmd/scan`) on the LSAT Lab authoring tab and on a matter's documents, and a "scanned page" view that shows the scanner's provenance and caveats.
- BL-20260907-23 — feature, low — A `:SourceDocument` node (or `PendingReview` kind `scanned_page`) so a scanned source can be cited from an analysis with graph-level provenance; needs its own spec, a licence posture per source, and HITL.
- BL-20260907-24 — infra, low — Pin the `ocrmd` extra to a release tag once ocrmd publishes one (or to PyPI), and consider installing it in the default image if the opencv system libraries are acceptable there.
- BL-20260907-25 — test-gap, med — An `integration`-marked test that runs `scan_file` against a real RapidOCR engine in an `INSTALL_OCRMD=1` image, nightly, so the embedded path is exercised end to end.
- BL-20260907-26 — doc-gap, low — Regenerate `frontend/__tests__/fixtures/api-schema.json` with `IngestScanRequest`/`IngestScanResult` and the ocrmd `Envelope` once the frontend consumes them (`make manage CMD=export_api_schema`).
