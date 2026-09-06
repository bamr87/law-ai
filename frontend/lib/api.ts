/**
 * Same-origin proxy route that attaches the API key server-side
 * (`app/api/backend/[...path]/route.ts`, BL-20260430-07).
 */
export const PROXY_BASE = '/api/backend'

export const API_BASE = resolveApiBase()

/**
 * Where API calls go.
 *
 * `NEXT_PUBLIC_API_BASE_URL` decides, and every shipped configuration
 * (`.env.example`, `docker-compose.yml`) sets it to `PROXY_BASE`, so the
 * browser talks to this app's own server and the key is attached there. An
 * absolute URL is still valid — that is how a gate-less deployment, a
 * server-side caller, and the test suite (whose network is mocked at the
 * backend's own origin) address the API — and it is safe now precisely
 * because `apiFetch` carries no credential either way.
 *
 * The bare fallback stays the local backend rather than the proxy: with
 * nothing configured there is no key to protect, and pointing a bare `npm
 * run dev` at a proxy route it may not be serving would fail confusingly.
 */
function resolveApiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL
  if (configured) return configured.replace(/\/$/, '')
  return 'http://localhost:8000'
}

/**
 * Centralised fetch wrapper (specs 008 + 009; BL-20260430-07).
 *
 * - Always prepends `API_BASE` to the path.
 * - Sets **no** credentials of its own. The shared key that gates
 *   `/api/agents/*`, `/api/analysis`, `/api/graph/*` and `/api/lsat/*` is
 *   attached by the proxy route from a server-only `AGENT_API_KEY`, so it is
 *   never in the page. `NEXT_PUBLIC_AGENT_API_KEY` is gone: a
 *   `NEXT_PUBLIC_*` secret is not a secret.
 * - With no key configured on the server (local dev), nothing is added at all
 *   — the local-first posture from constitution §1 is unchanged.
 */
export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers)
  return fetch(`${API_BASE}${path}`, { ...init, headers })
}

// Spec 008 alias kept for source-compat with earlier call sites.
export const agentFetch = apiFetch

// --- Analysis Studio (spec 007) ---

/** Retrieval coverage envelope (constitution §13 "absence is reported"). */
export interface RetrievalStats {
  queries: string[]
  result_count: number
  lexical_count?: number
  expanded_count?: number
  jurisdiction_requested?: string | null
  jurisdictions_present?: string[]
  jurisdiction_absent?: boolean
  /** Earliest decision date among retrieved passages, ISO (BL-20260803-02). */
  date_earliest?: string | null
  /** Latest decision date among retrieved passages, ISO (BL-20260803-02). */
  date_latest?: string | null
  coverage_note?: string
}

export interface IRACOutput {
  issue: string
  rule: string
  application: string
  conclusion: string
  sources: {
    title?: string
    url?: string
    /** False when the citation could not be resolved against the graph. */
    verified?: boolean
    /**
     * Constitution §13 issuing authority for this source — court,
     * jurisdiction, decision date, binding/persuasive — read off the graph
     * node, never from model prose (BL-20260803-04).
     */
    attribution?: Attribution
    resolved_case_id?: string | null
    [k: string]: unknown
  }[]
  confidence: number
  /** True when no real analysis ran (unimplemented/offline/engine down). */
  degraded?: boolean
  /**
   * Which degraded path produced this row (BL-20260810-16).
   * `engine_unavailable` is fixed by starting a local engine;
   * `offline_fallback` means every tier of the chain failed. Absent on
   * payloads written before the field existed — fall back to the
   * `[ENGINE UNAVAILABLE]` / `[OFFLINE FALLBACK]` prefix in `rule`.
   */
  degraded_reason?: 'engine_unavailable' | 'offline_fallback' | null
  /** Structured HITL flag — not inferred from prose. */
  requires_review?: boolean
  retrieval?: RetrievalStats | null
  reasoning_trace: string[]
  trace_id?: string | null
  /** Phoenix span for this run, when telemetry is configured. */
  phoenix_trace_url?: string | null
  /** LangGraph checkpoint thread, when the LangGraph engine produced it. */
  langgraph_thread_id?: string | null
  /** True when this run continued an existing thread (BL-20260810-13). */
  resumed?: boolean
}

/**
 * Constitution §13 issuing authority for one cited proposition
 * (BL-20260803-04). Read off the `:Case` node, never restated by the model;
 * `authority` is `unknown` rather than guessed when either the court or the
 * requested jurisdiction is missing.
 */
export interface Attribution {
  court?: string | null
  jurisdiction?: string | null
  decided_at?: string | null
  authority?: 'binding' | 'persuasive' | 'unknown'
  opinion_part?: 'majority' | 'dissent' | 'concurrence' | 'unknown'
}

export interface Precedent {
  case_id: string
  title: string
  court: string
  year: number
  relevance_score: number
  distinguishing_factors: string[]
  url: string
  /** `lexical` (fulltext hit) or `citation_expansion` (CITES hop). */
  retrieval_mode?: string
  /** Ingestion source recorded on the graph node. */
  source?: string
  /** `confidence` stored on the :Case node, when the graph records one. */
  graph_confidence?: number | null
  attribution?: Attribution
}

export interface PrecedentList {
  precedents: Precedent[]
  summary: string
  confidence: number
  /** True when no real retrieval ran — never present as search results. */
  degraded?: boolean
  /**
   * Verbatim coverage envelope from the retriever: what the corpus could and
   * could not answer (constitution §13). Empty when the backend had none.
   */
  coverage_note?: string
  /**
   * True when at least one retrieved precedent ships without a complete
   * issuing authority, so the set needs a human before it is relied on
   * (constitution §13, BL-20260803-04).
   */
  requires_review?: boolean
  trace_id?: string | null
}

export interface AnalysisAgentTrace {
  agent: string
  trace_id: string | null
  latency_ms: number
  confidence: number
}

export interface AnalysisResponse {
  id: string
  timestamp: string
  latency_ms: number
  confidence: number
  requires_human_review: boolean
  irac: IRACOutput
  precedents: PrecedentList
  agent_trace: AnalysisAgentTrace[]
  phoenix_trace_url?: string | null
  langgraph_thread_id?: string | null
  /** True when `thread_id` already had checkpointed state (BL-20260810-13). */
  resumed?: boolean
}

export interface AnalysisRequest {
  text: string
  jurisdiction?: string
  case_id?: string
  use_langgraph?: boolean
  /**
   * Durable LangGraph thread to resume (BL-20260810-13). Pass a previous
   * response's `langgraph_thread_id` to continue that thread's checkpointed
   * state; omit to start a fresh one.
   */
  thread_id?: string
  /**
   * Client-chosen correlation id (spec 032). Subscribe to
   * `/ws/agents/<stream_id>` and wait for `ready` BEFORE posting, or the step
   * events fire before anyone is listening. See lib/agentStream.ts.
   */
  stream_id?: string
  /**
   * Matter this research round belongs to (BL-20260817-05). The server
   * promotes the authorities that matter has already had *verified*, so a
   * later round ranks known-good citations first, and reports the bias back
   * in `irac.retrieval.boosted_count` / `boost_source`. Requires a signed-in
   * caller who owns the matter — anything else is a 404.
   */
  matter_id?: number | null
}

export async function runAnalysis(
  input: AnalysisRequest,
): Promise<AnalysisResponse> {
  const res = await apiFetch(`/api/analysis`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`Analysis failed (${res.status}): ${detail.slice(0, 200)}`)
  }
  return (await res.json()) as AnalysisResponse
}

/**
 * A persisted analysis, as returned by `GET /api/analysis/<id>`
 * (BL-20260429-25). Same shape as the original response plus the provenance
 * needed to revisit it — the trace ids the `/agents/runs` drill-down joins on.
 */
export interface PersistedAnalysis extends AnalysisResponse {
  persisted: true
  created_at: string | null
  trace_id: string | null
  child_trace_ids: string[]
  request: AnalysisRequest
}

/**
 * Reload a previous run by its `analysis_id`. Returns `null` for a run that
 * was never persisted or has been archived, so a stale permalink degrades to
 * an empty studio rather than an error screen.
 */
export async function fetchAnalysis(
  analysisId: string,
): Promise<PersistedAnalysis | null> {
  const res = await apiFetch(`/api/analysis/${encodeURIComponent(analysisId)}`)
  if (res.status === 404) return null
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(
      `Analysis lookup failed (${res.status}): ${detail.slice(0, 200)}`,
    )
  }
  return (await res.json()) as PersistedAnalysis
}

/** A "save & share" bookmark on an analysis (BL-20260429-26). */
export interface ShareLink {
  slug: string
  /** Frontend path the slug resolves at, e.g. `/shared/<slug>`. */
  url: string
  analysis_id: string
  label: string
  created_at: string | null
  revoked: boolean
}

/** A shared analysis as an unauthenticated reader sees it. */
export interface SharedAnalysis extends PersistedAnalysis {
  shared: true
  slug: string
  label: string
  /** Always present: a reader arriving from a link has none of the context. */
  disclaimer: string
}

/**
 * Mint a share link for a run. Signed-in callers only — the backend answers
 * 403 otherwise, and the thrown message is the backend's own wording so the
 * UI never has to guess why.
 *
 * `credentials: 'include'` because the credential here is the session cookie,
 * not the server-side API key `apiFetch` deliberately never carries.
 */
export async function createShareLink(
  analysisId: string,
  options: { slug?: string; label?: string } = {},
): Promise<ShareLink> {
  const res = await apiFetch(
    `/api/analysis/${encodeURIComponent(analysisId)}/share`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(options),
    },
  )
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: '' }))
    throw new Error(detail?.detail || `Share failed (${res.status})`)
  }
  return (await res.json()) as ShareLink
}

/** Revoke a share link. A revoked slug 404s and can never be re-minted. */
export async function revokeShareLink(
  analysisId: string,
  slug: string,
): Promise<ShareLink> {
  const res = await apiFetch(
    `/api/analysis/${encodeURIComponent(analysisId)}/share/${encodeURIComponent(slug)}`,
    { method: 'DELETE', credentials: 'include' },
  )
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: '' }))
    throw new Error(detail?.detail || `Revoke failed (${res.status})`)
  }
  return (await res.json()) as ShareLink
}

/**
 * Resolve a share slug. Returns `null` for a slug that never existed, was
 * revoked, or points at an archived/unshareable run — the backend makes those
 * indistinguishable on purpose, so probing learns nothing.
 */
export async function fetchSharedAnalysis(
  slug: string,
): Promise<SharedAnalysis | null> {
  const res = await apiFetch(`/api/shared/${encodeURIComponent(slug)}`)
  if (res.status === 404) return null
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(
      `Shared lookup failed (${res.status}): ${detail.slice(0, 200)}`,
    )
  }
  return (await res.json()) as SharedAnalysis
}

// --- Matters (spec 036 / BL-2026081x) ---

/**
 * A matter is user-owned data, so every call here sends the session cookie
 * (`credentials: 'include'`) and none of them carry the server-side API key:
 * a matter must never be reachable with a shared scope key.
 *
 * The list shape is identity only — `{id, slug, name, …}` — and the **id
 * always comes from the server**. A slug in a URL is a hint the server
 * re-resolves against the caller's own rows; nothing client-side may promote
 * a slug into an id (the IDOR trap in BL-20260830-08).
 */
export interface MatterRow {
  id: number
  slug: string
  name: string
  stage: string
  issue_tags: string[]
  jurisdiction: string
  updated_at: string | null
}

export interface MatterTaskRow {
  id: number
  title: string
  detail: string
  due_at: string | null
  status: 'open' | 'done' | 'cancelled'
  source_artifact_id: number | null
  reminded_at: string | null
  completed_at: string | null
  created_at: string | null
  /** Present on calendar rows, which span matters. */
  matter_slug?: string
  matter_name?: string
  overdue_days?: number
}

export interface MatterCalendar {
  window_days: number
  generated_at: string
  overdue: MatterTaskRow[]
  today: MatterTaskRow[]
  upcoming: MatterTaskRow[]
  count: number
}

export interface MatterStudyConcept {
  concept_id: string
  name: string
  sections: string[]
  summary: string
  from_tags: string[]
  why: string
  attempts: number
  accuracy: number | null
  status: 'unpractised' | 'weak' | 'solid'
  articles: string[]
  drills: string[]
}

export interface MatterStudyPlan {
  matter: { slug: string; name: string; issue_tags: string[] }
  concepts: MatterStudyConcept[]
  unmapped_tags: string[]
  covered_tags: string[]
}

async function matterFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await apiFetch(path, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: '' }))
    throw new Error(detail?.detail || `Request failed (${res.status})`)
  }
  return (await res.json()) as T
}

/** The caller's own matters. Signed out, this throws rather than inventing rows. */
export function fetchMatters() {
  return matterFetch<{ matters: MatterRow[]; count: number }>('/api/matters')
}

/**
 * Resolve one matter by slug — server-side, inside the caller's rows.
 * Returns `null` when the slug is unknown *or* owned by someone else: the
 * backend makes those indistinguishable, so a failed lookup leaks nothing.
 */
export async function fetchMatter(slug: string): Promise<MatterRow | null> {
  const res = await apiFetch(`/api/matters/${encodeURIComponent(slug)}`, {
    credentials: 'include',
  })
  if (!res.ok) return null
  return (await res.json()) as MatterRow
}

/** Every open dated task the caller owns, bucketed by urgency. */
export function fetchMatterCalendar(days = 30) {
  return matterFetch<MatterCalendar>(`/api/matters/calendar?days=${days}`)
}

export function fetchMatterTasks(slug: string) {
  return matterFetch<{ tasks: MatterTaskRow[] }>(
    `/api/matters/${encodeURIComponent(slug)}/tasks`,
  )
}

export function createMatterTask(
  slug: string,
  body: { title: string; detail?: string; due_at?: string | null },
) {
  return matterFetch<MatterTaskRow>(
    `/api/matters/${encodeURIComponent(slug)}/tasks`,
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function updateMatterTask(
  slug: string,
  taskId: number,
  body: {
    status?: 'open' | 'done' | 'cancelled'
    due_at?: string
    title?: string
    archived?: boolean
  },
) {
  return matterFetch<MatterTaskRow>(
    `/api/matters/${encodeURIComponent(slug)}/tasks/${taskId}`,
    { method: 'PATCH', body: JSON.stringify(body) },
  )
}

/** Doctrine gaps in this matter, mapped onto LSAT study material. */
export function fetchMatterStudyPlan(slug: string) {
  return matterFetch<MatterStudyPlan>(
    `/api/matters/${encodeURIComponent(slug)}/study-plan`,
  )
}

/** The portability bundle for one matter (BL-20260817-01). */
export function fetchMatterExport(slug: string) {
  return matterFetch<Record<string, unknown>>(
    `/api/matters/${encodeURIComponent(slug)}/export`,
  )
}

/** Every matter the caller owns, in one bundle. */
export function fetchAccountExport() {
  return matterFetch<Record<string, unknown>>('/api/account/export')
}

/**
 * Delete the signed-in account. The username must be retyped — an
 * irreversible action on one unconfirmed click is a bug, not a feature.
 */
export function deleteAccount(confirmUsername: string, reason = '') {
  return matterFetch<Record<string, unknown>>('/api/account/delete', {
    method: 'POST',
    body: JSON.stringify({ confirm_username: confirmUsername, reason }),
  })
}

// --- Server-persisted settings (BL-20260830-07 / spec 040) ---

/**
 * One stored setting row, in the same shape as the frontend's own
 * `SettingValue` (`lib/scope/types.ts`). Deliberately identical: the
 * TypeScript `resolveEffective` engine stays the only implementation of
 * precedence and locking, and the server only decides which rows exist.
 */
export interface StoredSettingValue {
  scopeId: string
  key: string
  value: unknown
  locked: boolean
}

export interface SettingValuesResponse {
  /** The caller's scope chain, root-first. */
  scopes: string[]
  values: StoredSettingValue[]
}

/** Rows for the caller's scope chain. Anonymous callers get instance rows. */
export async function fetchSettingValues(): Promise<SettingValuesResponse> {
  const res = await apiFetch('/api/settings/values', {
    credentials: 'include',
  })
  if (!res.ok) {
    throw new Error(`Settings lookup failed (${res.status})`)
  }
  return (await res.json()) as SettingValuesResponse
}

/**
 * Persist one override. `scopeId` may be `user:me`, which the server resolves
 * to the caller — a client never needs to know its own pk.
 */
export async function putSettingValue(
  scopeId: string,
  key: string,
  value: unknown,
  locked = false,
): Promise<StoredSettingValue> {
  const res = await apiFetch(
    `/api/settings/values/${encodeURIComponent(scopeId)}/${encodeURIComponent(key)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ value, locked }),
    },
  )
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: '' }))
    throw new Error(detail?.detail || `Setting write failed (${res.status})`)
  }
  return (await res.json()) as StoredSettingValue
}

/** Clear one override so the scope above it takes over again. */
export async function deleteStoredSettingValue(
  scopeId: string,
  key: string,
): Promise<boolean> {
  const res = await apiFetch(
    `/api/settings/values/${encodeURIComponent(scopeId)}/${encodeURIComponent(key)}`,
    { method: 'DELETE', credentials: 'include' },
  )
  if (res.status === 404) return false
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: '' }))
    throw new Error(detail?.detail || `Setting delete failed (${res.status})`)
  }
  return true
}

export async function getGraph(caseId: string) {
  const res = await apiFetch(`/api/graph/${caseId}`)
  return res.json()
}

// --- Agent ops dashboard (spec 003) ---

export interface AgentInfo {
  name: string
  module: string
}

export interface AgentRun {
  trace_id?: string
  timestamp?: string
  agent?: string
  type?: string
  model?: string
  latency_ms?: number
  confidence?: number
  sources_count?: number
  [key: string]: unknown
}

export interface BacklogItem {
  id: string
  kind: string
  severity: string
  title: string
}

export interface BacklogResponse {
  counts: { open: number; claimed: number; done: number; total: number }
  open: BacklogItem[]
  claimed: BacklogItem[]
  done: BacklogItem[]
}

export interface SpecInfo {
  id: string
  status: string
}

async function getJson<T>(path: string): Promise<T> {
  const res = await apiFetch(path)
  if (!res.ok) throw new Error(`Request failed: ${path} (${res.status})`)
  return (await res.json()) as T
}

export function fetchAgents() {
  return getJson<{ agents: AgentInfo[]; count: number }>('/api/agents')
}

export function fetchRuns(limit = 50) {
  return getJson<{ runs: AgentRun[]; count: number }>(
    `/api/agents/runs?limit=${limit}`,
  )
}

export function fetchBacklog() {
  return getJson<BacklogResponse>('/api/agents/backlog')
}

export function fetchSpecs() {
  return getJson<{ specs: SpecInfo[]; count: number }>('/api/agents/specs')
}

/** One `*.proposed.py` the autonomy loop drafted and nobody has ruled on. */
export interface ProposedTest {
  name: string
  /** Repo-relative path, so a reviewer can open it locally. */
  path: string
  /** File stem of the module under test (dots written as underscores). */
  module: string
  size: number
  mtime: string
  /** False means the skip decorator is missing — it would run if merged. */
  skip_marked: boolean
}

export interface ProposedTestsResponse {
  count: number
  files: ProposedTest[]
  /** False when the proposals directory does not exist in this checkout. */
  available: boolean
}

export function fetchProposedTests() {
  return getJson<ProposedTestsResponse>('/api/agents/proposed-tests')
}

/** One provider tier in LLM_PROVIDER_CHAIN, in the order it is tried. */
export interface LLMProviderStatus {
  provider: string
  position: number
  configured: boolean
  reachable?: boolean
  model?: string
  reason?: string
  error?: string
}

export interface LocalAIHealth {
  ollama: { reachable: boolean; models: string[]; error?: string }
  checkpointer: { kind: string; reachable: boolean; error?: string }
  phoenix: {
    reachable: boolean
    ui_url: string
    enabled: boolean
    error?: string
  }
  /** Ordered provider chain; the first configured + reachable tier serves. */
  llm_chain?: LLMProviderStatus[]
}

export function fetchLocalAIHealth() {
  return getJson<LocalAIHealth>('/api/agents/health/local-ai')
}

export interface AgentMetric {
  agent: string
  count: number
  error_count: number
  latency_p50_ms: number | null
  latency_p95_ms: number | null
  avg_confidence: number | null
  success_rate: number | null
  last_seen: string | null
  last_trace_id: string | null
  last_model: string | null
}

export function fetchAgentMetrics(limit = 500) {
  return getJson<{
    agents: AgentMetric[]
    window_size: number
    errors_total: number
  }>(`/api/agents/metrics?limit=${limit}`)
}

export function fetchRunDetail(traceId: string) {
  return getJson<{ trace_id: string; events: AgentRun[]; count: number }>(
    `/api/agents/runs/${encodeURIComponent(traceId)}`,
  )
}

// --- LSAT Lab (spec 005) ---

export type LsatChoiceLabel = 'A' | 'B' | 'C' | 'D' | 'E'
/**
 * Spec 047 FR-8 widened the scale at both ends. The original three bands are
 * unchanged so no stored item was invalidated; `intro` sits below `easy` and
 * `elite` above `hard`. Order is intro < easy < med < hard < elite — mirrors
 * `DIFFICULTY_ORDER` in the backend's `bank.py`.
 */
export type LsatDifficulty = 'intro' | 'easy' | 'med' | 'hard' | 'elite'
export type LsatSection = 'LR' | 'RC' | 'LG'

export interface LsatChoice {
  label: LsatChoiceLabel
  text: string
}

export interface LsatReference {
  title: string
  url?: string | null
  note?: string | null
}

export interface LsatQuestion {
  id: string
  section: LsatSection
  type: LsatSection
  difficulty: LsatDifficulty
  stem: string
  choices: LsatChoice[]
  concepts?: string[]
  references?: LsatReference[]
  passage_id?: string | null
  /**
   * Signed permutation this serve used (BL-20260606-01). Present only when the
   * question was requested with `shuffle`; echo it back to `gradeLsat` so the
   * answer is read in the order the learner saw.
   */
  remap?: string
}

export interface LsatGradeRequest {
  question_id: string
  choice: LsatChoiceLabel
  /** The serve's signed permutation, when the choices were shuffled. */
  remap?: string
  /** Solve-guide steps revealed before answering (spec 045 FR-5). */
  hints_used?: number
}

export interface LsatGradeResponse {
  question_id: string
  correct: boolean
  correct_choice: LsatChoiceLabel
  explanation: string
  section: LsatSection
  concepts?: string[]
}

export interface LsatStatsBucket {
  attempts: number
  correct: number
  accuracy: number
  /** Attempts graded with hints_used > 0 (spec 045 FR-5). */
  assisted?: number
  unassisted?: number
  /** Library articles read that serve this section (BL-20260903-05). */
  articles_read?: number
}

/** One point on the learner's accuracy trend (equal-count slices, oldest first). */
export interface LsatAccuracyPoint extends LsatStatsBucket {
  from: string
  to: string
}

/** A question the spaced-repetition schedule says is due (BL-20260503-05). */
export interface LsatReviewItem {
  question_id: string
  section: LsatSection | ''
  difficulty?: string
  concepts?: string[]
  /** Consecutive correct answers; 0 means the last attempt was wrong. */
  streak: number
  box: number
  attempts: number
  last_attempt_at: string
  due_at: string
  overdue_days: number
  reason: 'missed' | 'spaced-review'
}

export interface LsatStats extends LsatStatsBucket {
  by_section?: Record<string, LsatStatsBucket>
  /**
   * `'user'` when a signed-in learner's own history answered, `'instance'`
   * for the anonymous audit-log reading. The queue and the trend are only
   * ever populated in the former.
   */
  scope?: 'user' | 'instance'
  accuracy_over_time?: LsatAccuracyPoint[]
  review_queue?: LsatReviewItem[]
  questions_seen?: number
  /**
   * Library articles read (BL-20260903-05). Not the sum of the per-section
   * counts: a cross-cutting article names no section.
   */
  articles_read?: number
  articles_total?: number
  /**
   * Solve-guide reveal depth (BL-20260830-13). Absent on payloads from before
   * per-reveal events existed.
   */
  hints?: {
    reveals: number
    questions_hinted: number
    max_depth: number
    mean_depth: number
    spoiler_reveals: number
  }
  /**
   * Argumentative Writing practice (BL-20260831-27). Every band here was
   * produced by a model against the rubric — the real section is unscored —
   * so `model` and `prompt_version` ride along to be shown where the bands
   * are. Absent when a keyed section was asked for.
   */
  writing?: {
    attempts: number
    by_prompt: Record<string, number>
    latest_band: number | null
    best_band: number | null
    /** Weighted bands in the order they were earned, oldest first. */
    band_trend: number[]
    degraded: number
    model: string | null
    prompt_version: string | null
  }
}

export interface LsatSectionInfo {
  /**
   * Includes `'WS'` — Argumentative Writing is a section the API describes but
   * not one `LsatSection` can name, because it holds prompts rather than keyed
   * questions and none of the question routes accept it.
   */
  code: LsatSection | 'WS'
  name: string
  description: string
  format: string
  timing: string
  scoring: string
  skills: string[]
  tips: string[]
  concepts: string[]
  references: LsatReference[]
  question_count: number
  /** Writing prompts available for WS; 0 for the keyed sections (FR-5). */
  writing_prompt_count?: number
}

export interface LsatConcept {
  id: string
  name: string
  sections: LsatSection[]
  summary: string
  detail?: string | null
  examples: string[]
  see_also: string[]
  references: LsatReference[]
}

export interface LsatPassage {
  id: string
  section: LsatSection
  title: string
  summary?: string | null
  /** RC text. On a comparative set (spec 047 FR-9) this is Passage A. */
  passage?: string | null
  /** Passage B of a comparative RC set; absent on a single-text passage. */
  passage_b?: string | null
  title_a?: string | null
  title_b?: string | null
  setup?: string | null
  rules: string[]
  source: string
}

export interface LsatPassageDetail {
  passage: LsatPassage
  questions: LsatQuestion[]
  count: number
}

/**
 * What the learner actually did on this attempt (BL-20260429-18).
 *
 * The tutor's promise is coaching addressed to *this* reasoning, and none of
 * it is inferable server-side — elimination, hint reveals and time live in the
 * lab. Every field is optional; a caller that captures none of it gets the
 * behaviour it had before the field existed.
 */
export interface LsatTutorTrace {
  /** Choices the learner ruled out before answering. */
  eliminated?: LsatChoiceLabel[]
  /** Solve-assist steps revealed on this question (spec 045). */
  hints_used?: number
  /** Wall-clock seconds spent before asking. */
  seconds_on_question?: number
  /** Answers tried on earlier attempts at this question. */
  prior_choices?: LsatChoiceLabel[]
}

export interface LsatTutorRequest {
  question_id: string
  user_choice?: LsatChoiceLabel | null
  user_question?: string | null
  /** Bypass the server-side walkthrough cache (spec 045 FR-13). */
  refresh?: boolean
  /** The learner's attempt trace, when the lab captured one. */
  trace?: LsatTutorTrace
  /**
   * Client-chosen WebSocket correlation id (BL-20260811-15). Subscribe to
   * `/ws/agents/<stream_id>` before posting and the tutor publishes its
   * progress there instead of leaving the learner on a spinner.
   */
  stream_id?: string
  /**
   * Stream the coaching token by token over `stream_id` (BL-20260503-03).
   * Ignored without one. The streamed variant asks the model for prose rather
   * than JSON, so its wording differs slightly from the buffered reply — the
   * REST body is still the authoritative result either way.
   */
  stream_tokens?: boolean
}

export interface LsatTutorResponse {
  question_id: string
  user_choice: LsatChoiceLabel | null
  correct_choice: LsatChoiceLabel
  is_correct: boolean | null
  explanation: string
  coaching: string
  next_steps: string[]
  concepts: LsatConcept[]
  references: LsatReference[]
  model: string
  used_llm: boolean
  confidence: number
  requires_human_review: boolean
  latency_ms: number
  /** True when served from the stored walkthrough cache (spec 045 FR-13). */
  cached?: boolean
  /** OpenTelemetry trace id for this call, when tracing is on. */
  trace_id?: string | null
  /** Deep link to that trace in Phoenix, when a collector is configured. */
  phoenix_trace_url?: string | null
  /**
   * Always null here (BL-20260503-06): the tutor calls the provider chain
   * directly and runs no LangGraph graph, so there is no checkpointed thread
   * to resume. Present so this response mirrors `AnalysisResponse` field for
   * field — the same trace strip renders against either.
   */
  langgraph_thread_id?: string | null
}

// --- LSAT cross-check + validation (spec 045 FR-14/FR-15) ---

export interface LsatCrossCheck {
  question_id: string
  bank_choice: LsatChoiceLabel
  model_choice: LsatChoiceLabel | null
  /** null when no provider was reachable. */
  agree: boolean | null
  rationale: string
  model: string
  used_llm: boolean
  cached: boolean
  requires_human_review: boolean
  latency_ms: number
}

export async function crossCheckLsat(
  questionId: string,
  opts?: { refresh?: boolean },
): Promise<LsatCrossCheck> {
  const res = await apiFetch(
    `/api/lsat/questions/${encodeURIComponent(questionId)}/cross-check`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(opts?.refresh ? { refresh: true } : {}),
    },
  )
  if (!res.ok) throw new Error(`Cross-check failed (${res.status})`)
  return (await res.json()) as LsatCrossCheck
}

export interface LsatValidationIssue {
  question_id: string
  kind: string
  detail: string
}

export interface LsatValidationReport {
  generated_at: string
  section: LsatSection | null
  question_count: number
  guide_count: number
  issue_count: number
  issues: LsatValidationIssue[]
  answer_distribution: Record<string, Record<string, number>>
  cross_checks: {
    checked: number
    agreements: number
    disagreements: {
      question_id: string
      bank_choice: LsatChoiceLabel
      model_choice: LsatChoiceLabel | null
      model: string
    }[]
  }
}

export function fetchLsatValidation(section?: LsatSection) {
  const qs = section ? `?section=${section}` : ''
  return getJson<LsatValidationReport>(`/api/lsat/validation${qs}`)
}

export interface LsatQuestionFilters {
  limit?: number
  difficulty?: LsatDifficulty
  section?: LsatSection
  passage_id?: string
  /**
   * Only questions tagged with this concept id (BL-20260905-01). What makes
   * the library's "drill them in the lab" link land on the concept rather than
   * on a random item.
   */
  concept?: string
  /** Shuffle the answer choices for this serve (BL-20260606-01). */
  shuffle?: boolean
}

export function fetchLsatQuestions(
  arg1: number | LsatQuestionFilters = 1,
  difficulty?: LsatDifficulty,
) {
  // Back-compat: original signature was (limit, difficulty?). Now also
  // accepts a filter object so callers can scope by section / passage.
  const filters: LsatQuestionFilters =
    typeof arg1 === 'number' ? { limit: arg1, difficulty } : { ...arg1 }
  const qs = new URLSearchParams({ limit: String(filters.limit ?? 1) })
  if (filters.difficulty) qs.set('difficulty', filters.difficulty)
  if (filters.section) qs.set('section', filters.section)
  if (filters.passage_id) qs.set('passage_id', filters.passage_id)
  if (filters.concept) qs.set('concept', filters.concept)
  if (filters.shuffle) qs.set('shuffle', '1')
  return getJson<{ questions: LsatQuestion[]; count: number }>(
    `/api/lsat/questions?${qs.toString()}`,
  )
}

export async function gradeLsat(
  question_id: string,
  choice: LsatChoiceLabel,
  hintsUsed?: number,
  /** The serve's `remap` token, when the choices were shuffled. */
  remap?: string,
): Promise<LsatGradeResponse> {
  const body: LsatGradeRequest = { question_id, choice }
  if (typeof hintsUsed === 'number' && hintsUsed > 0) {
    body.hints_used = hintsUsed
  }
  if (remap) body.remap = remap
  const res = await apiFetch(`/api/lsat/grade`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`Grade failed (${res.status})`)
  return (await res.json()) as LsatGradeResponse
}

export function fetchLsatStats(section?: LsatSection) {
  const qs = new URLSearchParams()
  if (section) qs.set('section', section)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return getJson<LsatStats>(`/api/lsat/stats${suffix}`)
}

export function fetchLsatSections() {
  return getJson<{ sections: LsatSectionInfo[]; count: number }>(
    `/api/lsat/sections`,
  )
}

export function fetchLsatConcepts(section?: LsatSection) {
  const qs = new URLSearchParams()
  if (section) qs.set('section', section)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return getJson<{ concepts: LsatConcept[]; count: number }>(
    `/api/lsat/concepts${suffix}`,
  )
}

/**
 * One concept plus both of its inverses.
 *
 * `taught_in` is the concept → article direction of spec 048 FR-7 (article
 * ids, resolved against the library index client-side). The API has returned
 * it since the library shipped; the catalog is the first surface to render
 * it, which is the point of living inside the library rather than beside it.
 */
export interface LsatConceptDetail {
  concept: LsatConcept
  /** Bank question ids tagged with this concept — capped at 10 server-side. */
  used_in_questions: string[]
  /**
   * How many questions carry the tag in total — the uncapped count, so an
   * entry can name the exact number instead of "10+" (BL-20260905-06). The
   * mirror of an article's `drill_question_count`.
   */
  used_in_count: number
  /** Ids of library articles that teach it, by tag or by inline reference. */
  taught_in: string[]
}

export function fetchLsatConcept(id: string) {
  return getJson<LsatConceptDetail>(
    `/api/lsat/concepts/${encodeURIComponent(id)}`,
  )
}

export function fetchLsatPassages(section?: LsatSection) {
  const qs = new URLSearchParams()
  if (section) qs.set('section', section)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return getJson<{ passages: LsatPassage[]; count: number }>(
    `/api/lsat/passages${suffix}`,
  )
}

/**
 * One passage plus its questions. `shuffle` asks the server to permute each
 * question's choices and mint a `remap` token (BL-20260606-01) — RC and LG are
 * served from here, so without it the key sat in the same position on every
 * attempt for the majority of the bank.
 */
export function fetchLsatPassage(id: string, opts?: { shuffle?: boolean }) {
  const suffix = opts?.shuffle ? '?shuffle=1' : ''
  return getJson<LsatPassageDetail>(
    `/api/lsat/passages/${encodeURIComponent(id)}${suffix}`,
  )
}

// ---------------------------------------------------------------------------
// Argumentative Writing (spec 047 FR-1..FR-4)
//
// The one LSAT task that produces prose rather than a keyed choice, so it has
// its own content type rather than being bent into `LsatQuestion`. The four
// routes below mirror `backend/law_ai/lsat/urls.py`; the prompt payload is
// `PublicWritingPrompt`, which withholds the annotated model response exactly
// as `public_view` withholds an answer key — reading the worked example before
// drafting destroys the exercise.
// ---------------------------------------------------------------------------

export interface LsatWritingPosition {
  id: string
  name: string
  summary: string
}

export interface LsatWritingPerspective {
  id: string
  text: string
}

export interface LsatWritingSelfCheck {
  criterion_id: string
  prompt: string
}

/** `PublicWritingPrompt` — safe to serve before anything has been drafted. */
export interface LsatWritingPrompt {
  id: string
  title: string
  rubric_id: string
  difficulty: LsatDifficulty
  issue: string
  context: string
  positions: LsatWritingPosition[]
  perspectives: LsatWritingPerspective[]
  task: string
  prewriting_minutes: number
  time_limit_minutes: number
  concepts: string[]
  self_check: LsatWritingSelfCheck[]
  references: LsatReference[]
  has_model_response: boolean
}

export interface LsatRubricBand {
  level: number
  label: string
  descriptor: string
}

export interface LsatRubricCriterion {
  id: string
  name: string
  description: string
  weight: number
  look_for: string[]
  /** Band level (as a string key) → what this criterion looks like there. */
  band_notes: Record<string, string>
}

export interface LsatWritingRubric {
  id: string
  name: string
  version: number
  summary: string
  bands: LsatRubricBand[]
  criteria: LsatRubricCriterion[]
  source: string
}

export interface LsatWritingModelResponse {
  position_id: string
  thesis: string
  essay: string
  annotations: { criterion_id: string; note: string }[]
}

export interface LsatWritingPromptDetail {
  prompt: LsatWritingPrompt
  rubric: LsatWritingRubric
  /** Present only when the caller asked for it *after* drafting. */
  model_response?: LsatWritingModelResponse
}

export interface LsatWritingCriterionScore {
  criterion_id: string
  band: number
  evidence: string
  improvement: string
}

export interface LsatWritingEvaluation {
  prompt_id: string
  rubric_id: string
  position_taken: string | null
  summary: string
  criteria: LsatWritingCriterionScore[]
  strengths: string[]
  priorities: string[]
  /** Criterion bands averaged by rubric weight. A study instrument only. */
  weighted_band: number
}

export interface LsatWritingEvaluationResult {
  evaluation: LsatWritingEvaluation
  /** Named at the point of display: these bands are machine-derived. */
  model: string
  prompt_version: string
  confidence: number
  latency_ms: number
  /** True when every provider failed and the deterministic fallback ran. */
  degraded: boolean
  trace_id?: string | null
}

/**
 * Which library articles this deployment has marked read (BL-20260903-05).
 *
 * Reading progress was per-browser `localStorage` on both products, so a
 * learner who read half the library on a laptop started again on a phone. The
 * server keeps the list in the same append-only audit store `lsat_grade` uses;
 * `localStorage` stays the offline fallback and the two are merged on load.
 */
export function fetchLsatReadArticles() {
  return getJson<{ read: string[]; count: number }>('/api/lsat/library/read')
}

/**
 * Record a read/unread for one article. Called fire-and-forget by design:
 * marking an article read must never block on the network or surface an error,
 * because the browser's own copy has already been updated.
 */
export async function recordLsatArticleRead(
  article_id: string,
  read = true,
): Promise<void> {
  const res = await apiFetch('/api/lsat/library/read', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ article_id, read }),
  })
  if (!res.ok) throw new Error(`Read state not recorded (${res.status})`)
}

export function fetchLsatWritingPrompts(difficulty?: LsatDifficulty) {
  const qs = difficulty ? `?difficulty=${difficulty}` : ''
  return getJson<{ prompts: LsatWritingPrompt[]; count: number }>(
    `/api/lsat/writing/prompts${qs}`,
  )
}

/**
 * One prompt, its rubric, and — only when `modelResponse` is asked for — the
 * annotated worked example. The lab asks for it after a draft is submitted.
 */
export function fetchLsatWritingPrompt(
  id: string,
  { modelResponse = false }: { modelResponse?: boolean } = {},
) {
  const qs = modelResponse ? '?model_response=1' : ''
  return getJson<LsatWritingPromptDetail>(
    `/api/lsat/writing/prompts/${encodeURIComponent(id)}${qs}`,
  )
}

export function fetchLsatWritingRubric(id?: string) {
  const qs = id ? `?id=${encodeURIComponent(id)}` : ''
  return getJson<{ rubric: LsatWritingRubric }>(`/api/lsat/writing/rubric${qs}`)
}

export async function evaluateLsatWriting(
  prompt_id: string,
  response: string,
): Promise<LsatWritingEvaluationResult> {
  const res = await apiFetch(`/api/lsat/writing/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_id, response }),
  })
  if (!res.ok) throw new Error(`Writing evaluation failed (${res.status})`)
  return (await res.json()) as LsatWritingEvaluationResult
}

export async function askLsatTutor(
  req: LsatTutorRequest,
): Promise<LsatTutorResponse> {
  const res = await apiFetch(`/api/lsat/tutor`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`Tutor failed (${res.status}): ${detail.slice(0, 200)}`)
  }
  return (await res.json()) as LsatTutorResponse
}

// --- LSAT solve guides (spec 045) ---

export type LsatStepKind =
  | 'orient'
  | 'inventory'
  | 'symbolize'
  | 'diagram'
  | 'infer'
  | 'eliminate'
  | 'answer'

export interface LsatSequenceRep {
  rep_type: 'sequence'
  /** Slot labels, rendered left-to-right (first-to-last). */
  slots: string[]
  entities: string[]
  /** slot label -> entity fixed there. */
  placements: Record<string, string>
  /** slot label -> entities barred from it. */
  exclusions: Record<string, string[]>
  note?: string | null
}

export interface LsatGridCell {
  row: string
  column: string
  mark: 'yes' | 'no' | 'maybe'
  note?: string | null
}

export interface LsatGridRep {
  rep_type: 'grid'
  rows: string[]
  columns: string[]
  cells: LsatGridCell[]
  note?: string | null
}

export interface LsatNotationRule {
  rule_text: string
  symbols: string
  note?: string | null
}

export interface LsatNotationRep {
  rep_type: 'notation'
  rules: LsatNotationRule[]
}

export interface LsatArgumentNode {
  id: string
  role: 'premise' | 'conclusion' | 'assumption' | 'objection'
  text: string
}

export interface LsatArgumentEdge {
  from: string
  to: string
  relation: 'supports' | 'opposes'
}

export interface LsatArgumentMapRep {
  rep_type: 'argument_map'
  nodes: LsatArgumentNode[]
  edges: LsatArgumentEdge[]
}

export interface LsatPassageParagraph {
  paragraph: number
  role: string
  gist: string
}

export interface LsatPassageMapRep {
  rep_type: 'passage_map'
  paragraphs: LsatPassageParagraph[]
}

export type LsatRepresentation =
  | LsatSequenceRep
  | LsatGridRep
  | LsatNotationRep
  | LsatArgumentMapRep
  | LsatPassageMapRep

export interface LsatSolveStep {
  kind: LsatStepKind
  title: string
  spoiler: boolean
  /** True when the server withheld this step's content (spoiler not yet unlocked). */
  locked: boolean
  text?: string
  representation?: LsatRepresentation | null
}

export interface LsatSolveGuide {
  question_id: string
  method: string
  version: number
  source: string
  step_count: number
  steps: LsatSolveStep[]
}

/** 404 from the guide endpoint — carries whether the tutor can stand in. */
export class LsatGuideNotFoundError extends Error {
  hasTutor: boolean
  constructor(hasTutor: boolean) {
    super('no solve guide for this question')
    this.name = 'LsatGuideNotFoundError'
    this.hasTutor = hasTutor
  }
}

/**
 * Record one revealed solve-guide step (BL-20260830-13).
 *
 * Grade-time `hints_used` can only ever say "assisted": a one-hint nudge and a
 * five-hint walkthrough look the same, and hints taken on a question that is
 * never submitted are not in it at all. Called fire-and-forget — a hint must
 * never wait on, or fail because of, an analytics write.
 */
export async function recordLsatHintReveal(
  questionId: string,
  {
    stepIndex,
    revealedCount,
    spoiler = false,
  }: { stepIndex: number; revealedCount: number; spoiler?: boolean },
): Promise<void> {
  const res = await apiFetch(
    `/api/lsat/questions/${encodeURIComponent(questionId)}/hint`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        step_index: stepIndex,
        revealed_count: revealedCount,
        spoiler,
      }),
    },
  )
  if (!res.ok) throw new Error(`Hint not recorded (${res.status})`)
}

export async function fetchLsatGuide(
  questionId: string,
  opts?: { spoilers?: boolean; remap?: string },
): Promise<LsatSolveGuide> {
  const params = new URLSearchParams()
  if (opts?.spoilers) params.set('spoilers', '1')
  // Guide steps name answer labels, so a shuffled serve must remap them too.
  if (opts?.remap) params.set('remap', opts.remap)
  const suffix = params.toString() ? `?${params.toString()}` : ''
  const res = await apiFetch(
    `/api/lsat/questions/${encodeURIComponent(questionId)}/guide${suffix}`,
  )
  if (res.status === 404) {
    const body = (await res.json().catch(() => ({}))) as { has_tutor?: boolean }
    throw new LsatGuideNotFoundError(Boolean(body.has_tutor))
  }
  if (!res.ok) throw new Error(`Guide fetch failed (${res.status})`)
  return (await res.json()) as LsatSolveGuide
}

// --- LSAT Content Authoring (spec 019) ---

export type LsatProposalStatus = 'pending' | 'approved' | 'rejected'

export interface LsatProposalDraft {
  section: LsatSection
  difficulty: LsatDifficulty
  stem: string
  choices: LsatChoice[]
  correct: LsatChoiceLabel
  explanation: string
  concepts: string[]
  passage_id?: string | null
  confidence: number
}

/** Solve-guide draft in the proposal queue (spec 045 FR-9). */
export interface LsatGuideProposalDraft {
  question_id: string
  method: string
  version: number
  source: string
  steps: {
    kind: LsatStepKind
    title: string
    text: string
    spoiler: boolean
    representation?: LsatRepresentation | null
  }[]
}

/**
 * Writing-prompt draft in the proposal queue (BL-20260831-28). The factory can
 * grow the writing section too, and a writing draft has no `choices`, so the
 * queue must recognise it rather than fall through to the question card.
 */
export interface LsatWritingProposalDraft {
  id?: string
  title: string
  rubric_id?: string
  difficulty?: LsatDifficulty
  issue: string
  context: string
  task: string
  positions: { id: string; name: string; summary: string }[]
  perspectives: { id: string; text: string }[]
  concepts?: string[]
  model_response?: { position_id: string; thesis: string; essay: string }
}

/**
 * Cross-check disagreement queued by the sweep (BL-20260831-21). A report,
 * not a draft: approving it records "the key is right after all" and writes
 * nothing to the bank; rejecting it means the question needs a human edit.
 */
export interface LsatCrossCheckProposalDraft {
  question_id: string
  section: LsatSection
  difficulty: LsatDifficulty
  stem: string
  bank_choice: string
  model_choice: string | null
  rationale: string
  model: string
}

export interface LsatProposal {
  id: string
  status: LsatProposalStatus
  created_at: string
  updated_at: string
  /**
   * "question" (default, legacy rows), "guide" (spec 045), "crosscheck"
   * (BL-20260831-21 — a blind-solve disagreement awaiting re-verification) or
   * "writing_prompt" (BL-20260831-28 — a factory-drafted WS task).
   */
  proposal_kind?: 'question' | 'guide' | 'crosscheck' | 'writing_prompt'
  section: LsatSection | null
  difficulty: LsatDifficulty | null
  agent_trace_id: string
  model: string
  confidence: number
  source_concept_ids: string[]
  draft:
    | LsatProposalDraft
    | LsatGuideProposalDraft
    | LsatCrossCheckProposalDraft
    | LsatWritingProposalDraft
  reviewer?: string | null
  note?: string | null
  question_id?: string | null
  /** Producer lineage recorded at draft time (factory mode, balance flag, review). */
  meta?: {
    balance_flag?: string | null
    /**
     * Advisory review attached at draft time. Question proposals carry an
     * `LsatDraftReview` (BL-20260527-04); guide proposals carry an
     * `LsatGuideReview` (BL-20260830-15). Neither ever gates promotion.
     */
    review?: LsatDraftReview | LsatGuideReview | null
    [k: string]: unknown
  } | null
}

/**
 * Blind quality review attached to a question proposal (BL-20260527-04).
 * `ambiguity` is scored so that HIGHER IS BETTER (1.0 = no unintended
 * ambiguity). `flagged` sorts borderline drafts to the top of the queue; it
 * never rejects anything (constitution §5).
 */
/**
 * Pedagogical judge-tier review of a solve-guide draft (BL-20260830-15).
 * Runs after the deterministic `validate_guide_quality` lint and before a
 * human editor. `verdict` is advisory: promotion stays human-triggered, and
 * `unreviewed` means no provider answered — not "approved".
 */
export interface LsatGuideReview {
  verdict: 'pass' | 'revise' | 'reject' | 'unreviewed'
  symbolization_faithful: boolean
  step_findings: { index: number; follows: boolean; note: string }[]
  summary: string
  confidence: number
  model: string
  degraded: boolean
}

export interface LsatDraftReview {
  clarity: number
  ambiguity: number
  single_best_answer: number
  overall: number
  flags: string[]
  rationale: string
  flagged: boolean
  model: string
  degraded: boolean
}

export interface LsatGapRow {
  section: LsatSection
  concept: string
  attempts: number
  correct: number
  accuracy: number
}

export interface GenerateLsatProposalsRequest {
  section: LsatSection
  difficulty: LsatDifficulty
  count?: number
  concepts?: string[]
  passage_id?: string | null
}

export interface GenerateLsatProposalsResponse {
  proposals: LsatProposal[]
  trace_id: string | null
  model: string
  degraded: boolean
  count: number
}

export function fetchLsatProposals(
  status: LsatProposalStatus | 'all' = 'pending',
  limit = 50,
) {
  const qs = new URLSearchParams({ status, limit: String(limit) })
  return getJson<{
    proposals: LsatProposal[]
    count: number
    status: string
  }>(`/api/lsat/proposals?${qs.toString()}`)
}

export async function generateLsatProposals(
  req: GenerateLsatProposalsRequest,
): Promise<GenerateLsatProposalsResponse> {
  const res = await apiFetch(`/api/lsat/proposals/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(
      `Generate proposals failed (${res.status}): ${detail.slice(0, 200)}`,
    )
  }
  return (await res.json()) as GenerateLsatProposalsResponse
}

export async function approveLsatProposal(
  id: string,
  note?: string,
): Promise<LsatProposal> {
  const res = await apiFetch(
    `/api/lsat/proposals/${encodeURIComponent(id)}/approve`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: note ?? null }),
    },
  )
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`Approve failed (${res.status}): ${detail.slice(0, 200)}`)
  }
  return (await res.json()) as LsatProposal
}

export async function rejectLsatProposal(
  id: string,
  note?: string,
): Promise<LsatProposal> {
  const res = await apiFetch(
    `/api/lsat/proposals/${encodeURIComponent(id)}/reject`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: note ?? null }),
    },
  )
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`Reject failed (${res.status}): ${detail.slice(0, 200)}`)
  }
  return (await res.json()) as LsatProposal
}

/**
 * What the content factory will target next (BL-20260702-06).
 *
 * `factory.status()` has answered this for `manage.py lsat_factory status`
 * since spec 024; nothing exposed it over HTTP, so a reviewer working the
 * Authoring queue could see the drafts in front of them and not the coverage
 * holes that produced them. Read-only, and not cheap — it loads the whole bank
 * and lists up to 500 proposals, so do not poll it on an interval.
 */
export interface LsatFactoryDeficit {
  archetype_id: string
  difficulty: string
  have: number
  want: number
}

export interface LsatFactoryStatus {
  bank_total: number
  bank_by_section: Record<string, number>
  writing_prompts: number
  writing_by_difficulty: Record<string, number>
  coverage_cells: number
  cells_with_deficit: number
  /** The next batch's targets, worst deficit first. */
  top_deficits: LsatFactoryDeficit[]
  pending_proposals: number
  pending_from_factory: number
  latest_manifest: string | null
  latest_manifest_summary: {
    manifest_id: string
    created_at: string
    jobs: number
    by_tier: Record<string, number>
    by_archetype: Record<string, number>
  } | null
  /** What the queued factory drafts came through. */
  pending_gates: {
    by_executor: Record<string, number>
    by_tier: Record<string, number>
    answer_balance_flagged: number
  }
}

export function fetchLsatFactoryStatus() {
  return getJson<LsatFactoryStatus>('/api/lsat/factory/status')
}

export function fetchLsatGaps(limit = 10) {
  const qs = new URLSearchParams({ limit: String(limit) })
  return getJson<{ gaps: LsatGapRow[]; count: number; limit: number }>(
    `/api/lsat/gaps?${qs.toString()}`,
  )
}

// --- LSAT knowledge library (spec 048) ---

/**
 * Articles arrive as compiled *typed blocks*, never as Markdown or HTML.
 * `library.py` does the parsing once, at load time, so neither this client
 * nor the static site needs a Markdown dependency and neither ever renders
 * raw markup (spec 048 FR-2/FR-11, NFR-SAFETY-1). Keep these shapes in
 * lockstep with `lsat-static/lib/types.ts` — `tests/test_lsat_site.py`
 * asserts the two renderers cover the same block-type set.
 */
export type LsatSpanKind =
  | 'text'
  | 'strong'
  | 'em'
  | 'code'
  | 'link'
  | 'concept'
  | 'article'
  | 'question'

export interface LsatSpan {
  kind: LsatSpanKind
  text: string
  href?: string | null
  /** Target id on concept / article / question spans; resolved server-side. */
  ref_id?: string | null
}

/** One table cell: a run of spans. */
export type LsatCell = LsatSpan[]

export interface LsatHeadingBlock {
  block_type: 'heading'
  level: number
  text: string
  anchor: string
}

export interface LsatParagraphBlock {
  block_type: 'paragraph'
  spans: LsatSpan[]
}

export interface LsatListBlock {
  block_type: 'list'
  ordered: boolean
  items: LsatCell[]
}

export interface LsatNotationBlock {
  block_type: 'notation'
  lines: string[]
  caption?: string | null
}

export interface LsatTableBlock {
  block_type: 'table'
  headers: LsatCell[]
  rows: LsatCell[][]
}

export type LsatCalloutVariant =
  | 'example'
  | 'trap'
  | 'tip'
  | 'note'
  | 'warning'
  | 'drill'

export interface LsatCalloutBlock {
  block_type: 'callout'
  variant: LsatCalloutVariant
  title: string
  blocks: (LsatParagraphBlock | LsatListBlock | LsatNotationBlock)[]
}

export type LsatBlock =
  | LsatHeadingBlock
  | LsatParagraphBlock
  | LsatListBlock
  | LsatCalloutBlock
  | LsatTableBlock
  | LsatNotationBlock

export type LsatArticleKind =
  | 'orientation'
  | 'section-guide'
  | 'question-type'
  | 'technique'
  | 'strategy'
  | 'foundation'
  | 'review-method'

export type LsatArticleLevel = 'foundation' | 'core' | 'advanced'

/**
 * Wider than `LsatSection`, which is deliberately the multiple-choice subset
 * a `LsatQuestion` can carry. A library article can serve Argumentative
 * Writing, which has no keyed-question form.
 */
export type LsatSectionCode = LsatSection | 'WS'

export interface LsatOutlineEntry {
  level: number
  text: string
  anchor: string
}

/** Index row — no body. `/api/lsat/library` returns these. */
export interface LsatArticleSummary {
  id: string
  title: string
  kind: LsatArticleKind
  level: LsatArticleLevel
  summary: string
  sections: LsatSectionCode[]
  concepts: string[]
  prerequisites: string[]
  related: string[]
  tags: string[]
  status: 'draft' | 'reviewed' | 'needs-review'
  last_reviewed: string
  reading_minutes: number
  word_count: number
}

export interface LsatArticle extends LsatArticleSummary {
  archetypes: string[]
  revision: number
  source: string
  references: { title: string; url?: string | null; note?: string | null }[]
  blocks: LsatBlock[]
  outline: LsatOutlineEntry[]
}

export interface LsatTrack {
  id: string
  name: string
  summary: string
  goal: string
  article_ids: string[]
  tags: string[]
  article_count: number
  estimated_minutes: number
}

export interface LsatLibraryIndex {
  articles: LsatArticleSummary[]
  count: number
}

export interface LsatArticleDetail {
  article: LsatArticle
  concepts: LsatConcept[]
  prerequisites: LsatArticleSummary[]
  related: LsatArticleSummary[]
  tracks: { id: string; name: string }[]
  drill_question_ids: string[]
  drill_question_count: number
}

export interface LsatLibrarySearchHit {
  id: string
  title: string
  kind: LsatArticleKind
  sections: LsatSectionCode[]
  reading_minutes: number
  score: number
  matched_in: string[]
  snippet: string
  anchor: string | null
}

export interface LsatLibraryFilters {
  kind?: LsatArticleKind
  level?: LsatArticleLevel
  section?: LsatSectionCode
  tag?: string
  concept?: string
  track?: string
}

export function fetchLsatLibrary(filters: LsatLibraryFilters = {}) {
  const qs = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value) qs.set(key, value)
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return getJson<LsatLibraryIndex>(`/api/lsat/library${suffix}`)
}

export function fetchLsatArticle(articleId: string) {
  return getJson<LsatArticleDetail>(
    `/api/lsat/library/${encodeURIComponent(articleId)}`,
  )
}

export function fetchLsatTracks() {
  return getJson<{ tracks: LsatTrack[]; count: number }>(
    '/api/lsat/library/tracks',
  )
}

export function searchLsatLibrary(query: string, limit = 20) {
  const qs = new URLSearchParams({ q: query, limit: String(limit) })
  return getJson<{
    query: string
    results: LsatLibrarySearchHit[]
    count: number
  }>(`/api/lsat/library/search?${qs.toString()}`)
}

// --- Knowledge Graph (spec 006) ---

export interface GraphStats {
  available: boolean
  cases: number
  citations: number
  cites_edges: number
}

export interface GraphCase {
  id: string
  title: string | null
  court: string | null
  decided_at: string | null
  /** Provenance the sidebar inspector shows (BL-20260429-23). */
  source?: string | null
  source_url?: string | null
  confidence?: number | null
}

export interface GraphCasesResponse {
  available: boolean
  cases: GraphCase[]
  count: number
}

export type GraphNodeType = 'Case' | 'Citation'
export type GraphEdgeType = 'CITES' | 'HAS_CITATION'

export interface GraphNode {
  data: {
    id: string
    label: string
    type: GraphNodeType
    court?: string | null
    /** Set by /api/graph/path — the node is part of the precedent chain. */
    on_path?: boolean
    /** Full node properties for the sidebar inspector (BL-20260429-23). */
    title?: string | null
    decided_at?: string | null
    source?: string | null
    source_url?: string | null
    confidence?: number | null
    ingest_timestamp?: string | null
    agent_version?: string | null
    normalized?: string | null
    text?: string | null
  }
}

export interface GraphEdge {
  data: {
    id: string
    source: string
    target: string
    type: GraphEdgeType
    /** Set by /api/graph/path — the edge is part of the precedent chain. */
    on_path?: boolean
  }
}

export interface GraphNeighborhood {
  available: boolean
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export function fetchGraphStats() {
  return getJson<GraphStats>('/api/graph/stats')
}

/** Case-picker filters (BL-20260429-23). Empty values are omitted. */
export interface GraphCaseFilters {
  court?: string
  decided_from?: string
  decided_to?: string
}

export function fetchGraphCases(
  q = '',
  limit = 25,
  filters: GraphCaseFilters = {},
) {
  const qs = new URLSearchParams({ limit: String(limit) })
  if (q) qs.set('q', q)
  for (const [key, value] of Object.entries(filters)) {
    if (value) qs.set(key, value)
  }
  return getJson<GraphCasesResponse>(`/api/graph/cases?${qs.toString()}`)
}

export function fetchGraphNeighborhood(caseId: string, limit = 50) {
  const qs = new URLSearchParams({ limit: String(limit) })
  return getJson<GraphNeighborhood>(
    `/api/graph/neighborhood/${encodeURIComponent(caseId)}?${qs.toString()}`,
  )
}

/** Shortest precedent chain between two cases (BL-20260429-22). */
export interface GraphPath {
  available: boolean
  found: boolean
  hops: number
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export function fetchGraphPath(fromId: string, toId: string, maxHops = 6) {
  const qs = new URLSearchParams({
    from: fromId,
    to: toId,
    max_hops: String(maxHops),
  })
  return getJson<GraphPath>(`/api/graph/path?${qs.toString()}`)
}

// --- Autonomy dashboard (BL-20260511-03) ---

/** One LegalBench subset's accuracy across the recorded runs, oldest first. */
export interface AutonomyLegalbenchSeries {
  subset: string
  /** `null` where that run did not measure the subset — the x-axis stays aligned. */
  points: (number | null)[]
  latest: number | null
  /** Percentage points between the first and last measured run; null if <2 runs. */
  delta_pp: number | null
}

export interface AutonomyLegalbenchRun {
  run_id: string | null
  timestamp: string | null
  model: string | null
  accuracies: Record<string, number>
}

export interface AutonomyLegalbenchHistory {
  /** False when `history.jsonl` does not exist yet — report absence, not zero. */
  available: boolean
  runs: AutonomyLegalbenchRun[]
  series: AutonomyLegalbenchSeries[]
  count: number
}

export interface AutonomyCoverageModule {
  module: string
  pct: number
  severity: 'high' | 'med' | 'ok'
  missing_lines: number[]
}

export interface AutonomyCoverage {
  available: boolean
  modules: AutonomyCoverageModule[]
  count: number
  warn_threshold: number
  error_threshold: number
}

export interface AutonomyQuarantineDoc {
  id: string
  source: string
  kind: string
  confidence: number
  reason: string
  created_at: string | null
  reviewed: boolean
  approved: boolean | null
}

export interface AutonomyQuarantine {
  available: boolean
  documents: AutonomyQuarantineDoc[]
  count: number
}

export function fetchAutonomyLegalbenchHistory(limit = 20) {
  return getJson<AutonomyLegalbenchHistory>(
    `/api/agents/autonomy/legalbench-history?limit=${limit}`,
  )
}

export function fetchAutonomyCoverage() {
  return getJson<AutonomyCoverage>('/api/agents/autonomy/lowest-coverage')
}

export function fetchAutonomyQuarantine() {
  return getJson<AutonomyQuarantine>('/api/agents/autonomy/recent-quarantine')
}

// --- Quarantine review queue (BL-20260811-01) ---

/**
 * What state a quarantine row is in, as the backend's `status` filter names
 * them. `failed` is the one a reviewer must not miss: approved by a human,
 * but the graph write threw, so the item is *not* in the corpus.
 */
export type ReviewStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'awaiting_commit'
  | 'committed'
  | 'failed'

export interface ReviewRow {
  id: string
  source: string
  kind: string
  confidence: number
  reason: string
  created_at: string | null
  reviewed_at: string | null
  /** null while the row is still pending — not "rejected". */
  approved: boolean | null
  reviewer: string
  review_note: string
  committed_at: string | null
  commit_error: string
}

/** One row plus the quarantined document itself. */
export interface ReviewDetail extends ReviewRow {
  payload: unknown
}

export interface ReviewQueue {
  status: ReviewStatus
  reviews: ReviewRow[]
  count: number
  /** Row count per status, so the tab bar costs one request, not six. */
  counts: Record<ReviewStatus, number>
}

export interface ReviewDecision {
  review: ReviewRow
  committed: boolean
  edges?: number
  /** Non-empty when the approval stuck but the graph write did not. */
  commit_error?: string
}

export function fetchReviews(
  status: ReviewStatus = 'pending',
  opts?: { kind?: string; source?: string; limit?: number },
): Promise<ReviewQueue> {
  const params = new URLSearchParams({ status })
  if (opts?.kind) params.set('kind', opts.kind)
  if (opts?.source) params.set('source', opts.source)
  if (opts?.limit) params.set('limit', String(opts.limit))
  return getJson<ReviewQueue>(`/api/ingestion/reviews?${params.toString()}`)
}

export function fetchReview(id: string): Promise<ReviewDetail> {
  return getJson<ReviewDetail>(
    `/api/ingestion/reviews/detail?id=${encodeURIComponent(id)}`,
  )
}

/**
 * `PendingReview.id` is routinely a source URL, so the id travels in the body
 * rather than the path — a URL cannot survive a path segment intact.
 */
async function decideReview(
  verb: 'approve' | 'reject',
  id: string,
  body: { reviewer?: string; note?: string },
): Promise<ReviewDecision> {
  const res = await apiFetch(`/api/ingestion/reviews/${verb}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      id,
      reviewer: body.reviewer ?? '',
      note: body.note ?? '',
    }),
  })
  if (!res.ok) throw new Error(`Review ${verb} failed (${res.status})`)
  return (await res.json()) as ReviewDecision
}

export function approveReview(
  id: string,
  body: { reviewer?: string; note?: string } = {},
): Promise<ReviewDecision> {
  return decideReview('approve', id, body)
}

export function rejectReview(
  id: string,
  body: { reviewer?: string; note?: string } = {},
): Promise<ReviewDecision> {
  return decideReview('reject', id, body)
}
