'use client'

import { cn } from '@/lib/cn'
import {
  useGraphCases,
  useGraphNeighborhood,
  useGraphStats,
} from '@/lib/queries'
import {
  EmptyState,
  ErrorState,
  Page,
  Panel,
  SearchInput,
  StatGrid,
} from '@/components/ui'
import { useEffect, useMemo, useState } from 'react'
import GraphViewer from './GraphViewer'

const EMPTY = { available: true, nodes: [], edges: [] }

export default function KnowledgeGraph() {
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // Debounce the search term feeding the cases query.
  useEffect(() => {
    const id = setTimeout(() => setSearch(searchInput), 300)
    return () => clearTimeout(id)
  }, [searchInput])

  const statsQ = useGraphStats()
  const casesQ = useGraphCases(search, 25)
  const cases = useMemo(() => casesQ.data?.cases ?? [], [casesQ.data])
  // Effective selection falls back to the first case (derived, no effect).
  const effectiveId = selectedId ?? cases[0]?.id ?? null
  const hoodQ = useGraphNeighborhood(effectiveId, 50)
  const neighborhood = hoodQ.data ?? EMPTY

  const stats = statsQ.data
  const available =
    (statsQ.data?.available ?? true) && (casesQ.data?.available ?? true)
  const selectedCase = useMemo(
    () => cases.find((c) => c.id === effectiveId) ?? null,
    [cases, effectiveId],
  )

  return (
    <Page
      eyebrow="Graph"
      title="Knowledge Graph"
      tagline={
        <>
          Cases, citations, and <code className="text-ink">CITES</code> edges
          from Neo4j. Pick a case to render its 1-hop neighborhood. Backed by{' '}
          <code className="text-ink">/api/graph/*</code>.
        </>
      }
    >
      {!available && (
        <div
          role="alert"
          className="rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning"
        >
          Neo4j is not reachable — showing an empty graph. Start it with{' '}
          <code className="text-ink">docker compose up neo4j</code> and refresh.
        </div>
      )}

      <StatGrid
        items={[
          { label: 'Cases', value: stats?.cases ?? '—' },
          { label: 'Citations', value: stats?.citations ?? '—' },
          { label: 'CITES edges', value: stats?.cites_edges ?? '—' },
        ]}
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[320px_1fr]">
        <Panel
          title="Cases"
          subtitle={`${cases.length} loaded`}
          loading={casesQ.isLoading}
        >
          <SearchInput
            label="Search cases"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search title or id…"
            className="mb-3 w-full"
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
                  className={cn(
                    'w-full rounded-lg px-3 py-2 text-left text-sm transition',
                    selectedId === c.id
                      ? 'bg-brand-soft text-ink shadow-[inset_3px_0_0_0_var(--color-brand)]'
                      : 'text-muted hover:bg-brand-soft hover:text-ink',
                  )}
                >
                  <div className="truncate font-semibold">{c.title || c.id}</div>
                  <div className="mt-0.5 truncate font-mono text-[11px] text-subtle">
                    {c.id}
                    {c.court && <span className="ml-2">· {c.court}</span>}
                  </div>
                </button>
              </li>
            ))}
            {cases.length === 0 && !casesQ.isLoading && (
              <li>
                <EmptyState
                  message={
                    search ? (
                      'No cases match your filter.'
                    ) : (
                      <>
                        No cases ingested yet. Seed a few with{' '}
                        <code className="text-brand">make ingest-sample</code>.
                      </>
                    )
                  }
                  action={
                    search ? (
                      <button
                        type="button"
                        onClick={() => setSearchInput('')}
                        className="rounded-md border border-border bg-surface-2 px-3 py-1 text-xs text-ink hover:border-brand/50"
                      >
                        Clear filter
                      </button>
                    ) : undefined
                  }
                />
              </li>
            )}
          </ul>
        </Panel>

        <Panel
          title="Neighborhood"
          subtitle={
            selectedCase
              ? selectedCase.id + (hoodQ.isFetching ? ' · loading…' : '')
              : 'Select a case →'
          }
        >
          {selectedCase && (
            <div className="mb-3 rounded-lg border border-border bg-surface-2 p-3">
              <div className="text-sm font-semibold text-ink">
                {selectedCase.title || selectedCase.id}
              </div>
              <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-subtle">
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
          <div className="mt-2 flex justify-between text-[11px] text-subtle">
            <span>{neighborhood.nodes.length} nodes</span>
            <span>{neighborhood.edges.length} edges</span>
          </div>
        </Panel>
      </div>

      {(statsQ.isError || hoodQ.isError) && (
        <ErrorState
          message={
            (statsQ.error as Error)?.message ??
            (hoodQ.error as Error)?.message ??
            'Failed to load graph'
          }
        />
      )}
    </Page>
  )
}

function Legend() {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-4 text-[11px] text-subtle">
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-block h-2.5 w-2.5 rounded-sm bg-brand" />
        Case
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-block h-2.5 w-2.5 rotate-45 bg-warning" />
        Citation
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-block h-px w-6 bg-brand" />
        CITES
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-block h-px w-6 border-t border-dashed border-subtle" />
        HAS_CITATION
      </span>
    </div>
  )
}
