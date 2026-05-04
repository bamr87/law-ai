'use client'

import {
  fetchGraphCases,
  fetchGraphNeighborhood,
  fetchGraphStats,
  type GraphCase,
  type GraphNeighborhood,
  type GraphStats,
} from '@/lib/api'
import { useEffect, useMemo, useState } from 'react'
import GraphViewer from './GraphViewer'

const EMPTY_NEIGHBORHOOD: GraphNeighborhood = {
  available: true,
  nodes: [],
  edges: [],
}

export default function KnowledgeGraph() {
  const [stats, setStats] = useState<GraphStats | null>(null)
  const [cases, setCases] = useState<GraphCase[]>([])
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [neighborhood, setNeighborhood] = useState<GraphNeighborhood>(
    EMPTY_NEIGHBORHOOD,
  )
  const [available, setAvailable] = useState<boolean>(true)
  const [loadingCases, setLoadingCases] = useState(false)
  const [loadingHood, setLoadingHood] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Initial stats + cases load
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const [s, c] = await Promise.all([
          fetchGraphStats(),
          fetchGraphCases('', 25),
        ])
        if (cancelled) return
        setStats(s)
        setCases(c.cases)
        setAvailable(s.available && c.available)
        if (!selectedId && c.cases.length > 0) {
          setSelectedId(c.cases[0].id)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load graph')
        }
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Debounced search
  useEffect(() => {
    if (search === '' && cases.length > 0) return
    const id = setTimeout(() => {
      void (async () => {
        setLoadingCases(true)
        try {
          const c = await fetchGraphCases(search, 25)
          setCases(c.cases)
        } catch {
          // soft-fail; banner already shown if needed
        } finally {
          setLoadingCases(false)
        }
      })()
    }, 250)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  // Fetch neighborhood when selection changes
  useEffect(() => {
    if (!selectedId) return
    let cancelled = false
    setLoadingHood(true)
    void (async () => {
      try {
        const n = await fetchGraphNeighborhood(selectedId, 50)
        if (!cancelled) setNeighborhood(n)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load neighborhood')
        }
      } finally {
        if (!cancelled) setLoadingHood(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedId])

  const selectedCase = useMemo(
    () => cases.find((c) => c.id === selectedId) ?? null,
    [cases, selectedId],
  )

  return (
    <div className="space-y-6">
      {!available && (
        <div
          role="alert"
          className="rounded-xl border border-amber-700/50 bg-amber-950/40 px-4 py-3 text-sm text-amber-200"
        >
          Neo4j is not reachable — showing empty graph. Start the database with{' '}
          <code className="rounded bg-slate-900 px-1 py-0.5 text-xs">
            docker compose up neo4j
          </code>{' '}
          and refresh.
        </div>
      )}

      <StatsStrip stats={stats} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        <section
          aria-labelledby="cases-heading"
          className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4"
        >
          <header className="mb-3 flex items-center justify-between">
            <h2
              id="cases-heading"
              className="text-sm font-semibold uppercase tracking-wider text-slate-300"
            >
              Cases
            </h2>
            <span className="text-[10px] text-slate-500">
              {cases.length} loaded
            </span>
          </header>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search title or id…"
            className="mb-3 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-blue-500 focus:outline-none"
          />
          <ul
            data-testid="case-list"
            className="max-h-[520px] space-y-1 overflow-auto pr-1"
          >
            {cases.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(c.id)}
                  className={`w-full rounded-md border px-3 py-2 text-left text-xs transition ${
                    selectedId === c.id
                      ? 'border-blue-500/60 bg-blue-500/10 text-blue-100'
                      : 'border-slate-800 bg-slate-950/40 text-slate-300 hover:border-slate-700 hover:bg-slate-900/80'
                  }`}
                >
                  <div className="truncate font-medium">
                    {c.title || c.id}
                  </div>
                  <div className="mt-0.5 truncate font-mono text-[10px] text-slate-500">
                    {c.id}
                    {c.court && <span className="ml-2">· {c.court}</span>}
                  </div>
                </button>
              </li>
            ))}
            {cases.length === 0 && !loadingCases && (
              <li className="space-y-3 rounded-md border border-dashed border-slate-800 px-3 py-5 text-xs text-slate-400">
                <div className="text-center font-medium text-slate-300">
                  {search
                    ? 'No cases match your filter.'
                    : 'No cases ingested yet.'}
                </div>
                {search ? (
                  <button
                    type="button"
                    onClick={() => setSearch('')}
                    className="mx-auto block rounded-md border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-200 hover:border-blue-500/50 hover:text-white"
                  >
                    Clear filter
                  </button>
                ) : (
                  <>
                    <p className="text-center leading-relaxed">
                      Run the sample ingestion to populate Neo4j with a few
                      cases and citations:
                    </p>
                    <code className="block overflow-x-auto rounded bg-slate-950 px-2 py-1.5 text-center font-mono text-[11px] text-blue-300">
                      make ingest-sample
                    </code>
                  </>
                )}
              </li>
            )}
          </ul>
        </section>

        <section
          aria-labelledby="hood-heading"
          className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4"
        >
          <header className="mb-3 flex items-center justify-between">
            <h2
              id="hood-heading"
              className="text-sm font-semibold uppercase tracking-wider text-slate-300"
            >
              Neighborhood
            </h2>
            <div className="text-xs text-slate-500">
              {selectedCase ? (
                <span className="font-mono">{selectedCase.id}</span>
              ) : (
                'Select a case →'
              )}
              {loadingHood && (
                <span className="ml-2 text-slate-600">loading…</span>
              )}
            </div>
          </header>
          {selectedCase && (
            <div className="mb-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
              <div className="text-sm font-semibold text-slate-100">
                {selectedCase.title || selectedCase.id}
              </div>
              <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-slate-500">
                {selectedCase.court && <span>{selectedCase.court}</span>}
                {selectedCase.decided_at && (
                  <span>Decided {selectedCase.decided_at}</span>
                )}
                <span className="font-mono">{selectedCase.id}</span>
              </div>
            </div>
          )}
          <Legend />
          <GraphViewer elements={neighborhood} />
          <div className="mt-2 flex justify-between text-[10px] text-slate-500">
            <span>{neighborhood.nodes.length} nodes</span>
            <span>{neighborhood.edges.length} edges</span>
          </div>
        </section>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-red-700/50 bg-red-950/40 px-4 py-3 text-sm text-red-200"
        >
          {error}
        </div>
      )}
    </div>
  )
}

function StatsStrip({ stats }: { stats: GraphStats | null }) {
  const items = [
    { label: 'Cases', value: stats?.cases ?? '—', tone: 'text-blue-300' },
    { label: 'Citations', value: stats?.citations ?? '—', tone: 'text-amber-300' },
    { label: 'CITES edges', value: stats?.cites_edges ?? '—', tone: 'text-emerald-300' },
  ]
  return (
    <div className="grid grid-cols-3 gap-3">
      {items.map((it) => (
        <div
          key={it.label}
          className="rounded-2xl border border-slate-800 bg-slate-900/40 px-4 py-3"
        >
          <div className="text-[10px] uppercase tracking-wider text-slate-500">
            {it.label}
          </div>
          <div className={`mt-1 text-2xl font-semibold ${it.tone}`}>
            {it.value}
          </div>
        </div>
      ))}
    </div>
  )
}

function Legend() {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-4 text-[10px] text-slate-500">
      <LegendDot color="bg-blue-500" label="Case" />
      <LegendDot color="bg-amber-500" label="Citation" shape="rotate-45" />
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-block h-px w-6 bg-blue-400" />
        CITES
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-block h-px w-6 border-t border-dashed border-slate-500" />
        HAS_CITATION
      </span>
    </div>
  )
}

function LegendDot({
  color,
  label,
  shape = '',
}: {
  color: string
  label: string
  shape?: string
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-2.5 w-2.5 ${color} ${shape}`} />
      {label}
    </span>
  )
}
