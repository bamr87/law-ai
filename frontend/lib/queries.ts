'use client'

/**
 * React Query data layer — one hook per backend capability.
 *
 * Replaces the hand-rolled `useState` + `setInterval` + `cancelled`-flag
 * polling that was duplicated across every page (the audit counted 21 copies).
 * Polling hooks take a `live` flag so a "Pause" control just flips the
 * refetchInterval off; caching/dedup/retry/background-pause come from the
 * QueryClient defaults in `app/providers.tsx`.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query'
import * as api from './api'
import type {
  AnalysisRequest,
  GenerateLsatProposalsRequest,
  LsatChoiceLabel,
  LsatQuestionFilters,
  LsatSection,
  LsatTutorRequest,
} from './api'

// Poll cadences — fast-moving data refreshes often, slow-moving rarely.
const FAST = 5_000
const SLOW = 30_000
const SLOWER = 60_000

const interval = (live: boolean, ms: number): number | false =>
  live ? ms : false

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------
export const qk = {
  agents: ['agents'] as const,
  runs: (limit: number) => ['agents', 'runs', limit] as const,
  runDetail: (traceId: string) => ['agents', 'run', traceId] as const,
  metrics: (limit: number) => ['agents', 'metrics', limit] as const,
  backlog: ['agents', 'backlog'] as const,
  specs: ['agents', 'specs'] as const,
  health: ['agents', 'health'] as const,
  autonomy: ['agents', 'autonomy'] as const,
  sessions: (p: unknown) => ['agents', 'sessions', p] as const,
  session: (id: string) => ['agents', 'session', id] as const,
  graphStats: ['graph', 'stats'] as const,
  graphCases: (q: string, limit: number) => ['graph', 'cases', q, limit] as const,
  graphNeighborhood: (id: string, limit: number) =>
    ['graph', 'neighborhood', id, limit] as const,
  lsatQuestions: (f: unknown) => ['lsat', 'questions', f] as const,
  lsatStats: (s?: string) => ['lsat', 'stats', s ?? 'all'] as const,
  lsatSections: ['lsat', 'sections'] as const,
  lsatConcepts: (s?: string) => ['lsat', 'concepts', s ?? 'all'] as const,
  lsatConcept: (id: string) => ['lsat', 'concept', id] as const,
  lsatPassages: (s?: string) => ['lsat', 'passages', s ?? 'all'] as const,
  lsatPassage: (id: string) => ['lsat', 'passage', id] as const,
  lsatProposals: (status: string, limit: number) =>
    ['lsat', 'proposals', status, limit] as const,
  lsatGaps: (limit: number) => ['lsat', 'gaps', limit] as const,
}

// ---------------------------------------------------------------------------
// Agent Ops
// ---------------------------------------------------------------------------
export const useAgents = (live = true) =>
  useQuery({
    queryKey: qk.agents,
    queryFn: api.fetchAgents,
    refetchInterval: interval(live, SLOW),
  })

export const useRuns = (limit = 50, live = true) =>
  useQuery({
    queryKey: qk.runs(limit),
    queryFn: () => api.fetchRuns(limit),
    refetchInterval: interval(live, FAST),
  })

export const useRunDetail = (traceId: string | null) =>
  useQuery({
    queryKey: qk.runDetail(traceId ?? ''),
    queryFn: () => api.fetchRunDetail(traceId as string),
    enabled: !!traceId,
  })

export const useAgentMetrics = (limit = 500, live = true) =>
  useQuery({
    queryKey: qk.metrics(limit),
    queryFn: () => api.fetchAgentMetrics(limit),
    refetchInterval: interval(live, FAST),
  })

export const useBacklog = (live = true) =>
  useQuery({
    queryKey: qk.backlog,
    queryFn: api.fetchBacklog,
    refetchInterval: interval(live, SLOWER),
  })

export const useSpecs = (live = true) =>
  useQuery({
    queryKey: qk.specs,
    queryFn: api.fetchSpecs,
    refetchInterval: interval(live, SLOWER),
  })

export const useLocalAIHealth = (live = true) =>
  useQuery({
    queryKey: qk.health,
    queryFn: api.fetchLocalAIHealth,
    refetchInterval: interval(live, SLOW),
  })

export const useAutonomy = (live = true) =>
  useQuery({
    queryKey: qk.autonomy,
    queryFn: api.fetchAutonomy,
    refetchInterval: interval(live, SLOW),
  })

export const useSessions = (
  params?: { limit?: number; status?: string; source?: string },
  live = true,
) =>
  useQuery({
    queryKey: qk.sessions(params ?? {}),
    queryFn: () => api.fetchSessions(params),
    refetchInterval: interval(live, SLOW),
  })

export const useSessionDetail = (sessionId: string | null) =>
  useQuery({
    queryKey: qk.session(sessionId ?? ''),
    queryFn: () => api.fetchSessionDetail(sessionId as string),
    enabled: !!sessionId,
  })

// ---------------------------------------------------------------------------
// Analysis
// ---------------------------------------------------------------------------
export const useRunAnalysis = () =>
  useMutation({ mutationFn: (input: AnalysisRequest) => api.runAnalysis(input) })

// ---------------------------------------------------------------------------
// Knowledge Graph
// ---------------------------------------------------------------------------
export const useGraphStats = (live = true) =>
  useQuery({
    queryKey: qk.graphStats,
    queryFn: api.fetchGraphStats,
    refetchInterval: interval(live, SLOW),
  })

export const useGraphCases = (q = '', limit = 25) =>
  useQuery({
    queryKey: qk.graphCases(q, limit),
    queryFn: () => api.fetchGraphCases(q, limit),
    placeholderData: (prev) => prev,
  })

export const useGraphNeighborhood = (caseId: string | null, limit = 50) =>
  useQuery({
    queryKey: qk.graphNeighborhood(caseId ?? '', limit),
    queryFn: () => api.fetchGraphNeighborhood(caseId as string, limit),
    enabled: !!caseId,
  })

// ---------------------------------------------------------------------------
// LSAT
// ---------------------------------------------------------------------------
export const useLsatQuestions = (filters: LsatQuestionFilters) =>
  useQuery({
    queryKey: qk.lsatQuestions(filters),
    queryFn: () => api.fetchLsatQuestions(filters),
  })

export const useLsatStats = (section?: LsatSection) =>
  useQuery({
    queryKey: qk.lsatStats(section),
    queryFn: () => api.fetchLsatStats(section),
  })

export const useLsatSections = () =>
  useQuery({ queryKey: qk.lsatSections, queryFn: api.fetchLsatSections })

export const useLsatConcepts = (section?: LsatSection) =>
  useQuery({
    queryKey: qk.lsatConcepts(section),
    queryFn: () => api.fetchLsatConcepts(section),
  })

export const useLsatConcept = (id: string | null) =>
  useQuery({
    queryKey: qk.lsatConcept(id ?? ''),
    queryFn: () => api.fetchLsatConcept(id as string),
    enabled: !!id,
  })

export const useLsatPassages = (section?: LsatSection) =>
  useQuery({
    queryKey: qk.lsatPassages(section),
    queryFn: () => api.fetchLsatPassages(section),
  })

export const useLsatPassage = (id: string | null) =>
  useQuery({
    queryKey: qk.lsatPassage(id ?? ''),
    queryFn: () => api.fetchLsatPassage(id as string),
    enabled: !!id,
  })

export const useLsatProposals = (status = 'pending', limit = 50) =>
  useQuery({
    queryKey: qk.lsatProposals(status, limit),
    queryFn: () =>
      api.fetchLsatProposals(status as api.LsatProposalStatus | 'all', limit),
  })

export const useLsatGaps = (limit = 10) =>
  useQuery({ queryKey: qk.lsatGaps(limit), queryFn: () => api.fetchLsatGaps(limit) })

export const useGradeLsat = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      questionId,
      choice,
    }: {
      questionId: string
      choice: LsatChoiceLabel
    }) => api.gradeLsat(questionId, choice),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lsat', 'stats'] }),
  })
}

export const useAskTutor = () =>
  useMutation({ mutationFn: (req: LsatTutorRequest) => api.askLsatTutor(req) })

export const useGenerateProposals = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (req: GenerateLsatProposalsRequest) =>
      api.generateLsatProposals(req),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lsat', 'proposals'] }),
  })
}

export const useReviewProposal = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      action,
      note,
    }: {
      id: string
      action: 'approve' | 'reject'
      note?: string
    }) =>
      action === 'approve'
        ? api.approveLsatProposal(id, note)
        : api.rejectLsatProposal(id, note),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lsat', 'proposals'] }),
  })
}

export type { UseQueryResult }
