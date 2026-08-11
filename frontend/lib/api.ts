const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

/**
 * Centralised fetch wrapper (specs 008 + 009).
 *
 * - Always prepends `API_BASE` to the path.
 * - Injects `X-API-Key: ${NEXT_PUBLIC_AGENT_API_KEY}` when that env var is
 *   set, regardless of which feature router is being called. This lets a
 *   single shared key gate `/api/agents/*`, `/api/analysis`, `/api/graph/*`
 *   and `/api/lsat/*`. Per-router overrides set on the backend still work
 *   because the same value is sent on every request.
 * - When the env var is empty/unset (local dev), no header is added — keeps
 *   the local-first posture from constitution §1.
 */
export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const apiKey = process.env.NEXT_PUBLIC_AGENT_API_KEY
  const headers = new Headers(init.headers)
  if (apiKey) {
    headers.set('X-API-Key', apiKey)
  }
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
    resolved_case_id?: string | null
    [k: string]: unknown
  }[]
  confidence: number
  /** True when no real analysis ran (unimplemented/offline/engine down). */
  degraded?: boolean
  /** Structured HITL flag — not inferred from prose. */
  requires_review?: boolean
  retrieval?: RetrievalStats | null
  reasoning_trace: string[]
  trace_id?: string | null
}

export interface Precedent {
  case_id: string
  title: string
  court: string
  year: number
  relevance_score: number
  distinguishing_factors: string[]
  url: string
}

export interface PrecedentList {
  precedents: Precedent[]
  summary: string
  confidence: number
  /** True when no real retrieval ran — never present as search results. */
  degraded?: boolean
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
}

export interface AnalysisRequest {
  text: string
  jurisdiction?: string
  case_id?: string
  use_langgraph?: boolean
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

export interface LocalAIHealth {
  ollama: { reachable: boolean; models: string[]; error?: string }
  checkpointer: { kind: string; reachable: boolean; error?: string }
  phoenix: { reachable: boolean; ui_url: string; enabled: boolean; error?: string }
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
  return getJson<{ agents: AgentMetric[]; window_size: number; errors_total: number }>(
    `/api/agents/metrics?limit=${limit}`,
  )
}

export function fetchRunDetail(traceId: string) {
  return getJson<{ trace_id: string; events: AgentRun[]; count: number }>(
    `/api/agents/runs/${encodeURIComponent(traceId)}`,
  )
}

// --- LSAT Lab (spec 005) ---

export type LsatChoiceLabel = 'A' | 'B' | 'C' | 'D' | 'E'
export type LsatDifficulty = 'easy' | 'med' | 'hard'
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
}

export interface LsatStats extends LsatStatsBucket {
  by_section?: Record<string, LsatStatsBucket>
}

export interface LsatSectionInfo {
  code: LsatSection
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
  passage?: string | null
  setup?: string | null
  rules: string[]
  source: string
}

export interface LsatPassageDetail {
  passage: LsatPassage
  questions: LsatQuestion[]
  count: number
}

export interface LsatTutorRequest {
  question_id: string
  user_choice?: LsatChoiceLabel | null
  user_question?: string | null
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
}

export interface LsatQuestionFilters {
  limit?: number
  difficulty?: LsatDifficulty
  section?: LsatSection
  passage_id?: string
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
  return getJson<{ questions: LsatQuestion[]; count: number }>(
    `/api/lsat/questions?${qs.toString()}`,
  )
}

export async function gradeLsat(
  question_id: string,
  choice: LsatChoiceLabel,
): Promise<LsatGradeResponse> {
  const res = await apiFetch(`/api/lsat/grade`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question_id, choice }),
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

export function fetchLsatConcept(id: string) {
  return getJson<{ concept: LsatConcept; used_in_questions: string[] }>(
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

export function fetchLsatPassage(id: string) {
  return getJson<LsatPassageDetail>(
    `/api/lsat/passages/${encodeURIComponent(id)}`,
  )
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

export interface LsatProposal {
  id: string
  status: LsatProposalStatus
  created_at: string
  updated_at: string
  section: LsatSection
  difficulty: LsatDifficulty
  agent_trace_id: string
  model: string
  confidence: number
  source_concept_ids: string[]
  draft: LsatProposalDraft
  reviewer?: string | null
  note?: string | null
  question_id?: string | null
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

export function fetchLsatGaps(limit = 10) {
  const qs = new URLSearchParams({ limit: String(limit) })
  return getJson<{ gaps: LsatGapRow[]; count: number; limit: number }>(
    `/api/lsat/gaps?${qs.toString()}`,
  )
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
  }
}

export interface GraphEdge {
  data: {
    id: string
    source: string
    target: string
    type: GraphEdgeType
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

export function fetchGraphCases(q = '', limit = 25) {
  const qs = new URLSearchParams({ limit: String(limit) })
  if (q) qs.set('q', q)
  return getJson<GraphCasesResponse>(`/api/graph/cases?${qs.toString()}`)
}

export function fetchGraphNeighborhood(caseId: string, limit = 50) {
  const qs = new URLSearchParams({ limit: String(limit) })
  return getJson<GraphNeighborhood>(
    `/api/graph/neighborhood/${encodeURIComponent(caseId)}?${qs.toString()}`,
  )
}
