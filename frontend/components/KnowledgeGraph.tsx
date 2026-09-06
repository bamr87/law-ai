'use client'

import {
  fetchGraphCases,
  fetchGraphNeighborhood,
  fetchGraphPath,
  fetchGraphStats,
  type GraphCase,
  type GraphEdge,
  type GraphNeighborhood,
  type GraphNode,
  type GraphPath,
  type GraphStats,
} from '@/lib/api'
import { showCitationCounts } from '@/lib/settings/catalog'
import { useUrlState, useUrlWrite } from '@/lib/shell/viewState'
import { useSetting } from './shell/useSetting'
import { useEffect, useMemo, useState } from 'react'
import GraphViewer from './GraphViewer'

const EMPTY_NEIGHBORHOOD: GraphNeighborhood = {
  available: true,
  nodes: [],
  edges: [],
}

/**
 * Overlay a precedent chain (BL-20260429-22) onto the neighborhood.
 *
 * Nodes and edges the chain shares with the neighborhood are re-flagged
 * `on_path` in place; the rest of the chain is appended so the whole route is
 * visible even when it leaves the 1-hop neighborhood.
 */
/** Union of the courts seen so far with those in a freshly loaded page. */
export function collectCourts(previous: string[], rows: GraphCase[]): string[] {
  const set = new Set(previous)
  for (const row of rows) if (row.court) set.add(row.court)
  return Array.from(set).sort((a, b) => a.localeCompare(b))
}

export function mergePath(
  hood: { nodes: GraphNode[]; edges: GraphEdge[] },
  path: GraphPath | null,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  if (!path || !path.found) return hood
  const onPathNodes = new Set(path.nodes.map((n) => n.data.id))
  const onPathEdges = new Set(path.edges.map((e) => e.data.id))
  const nodes: GraphNode[] = hood.nodes.map((n) =>
    onPathNodes.has(n.data.id) ? { data: { ...n.data, on_path: true } } : n,
  )
  const edges: GraphEdge[] = hood.edges.map((e) =>
    onPathEdges.has(e.data.id) ? { data: { ...e.data, on_path: true } } : e,
  )
  const haveNode = new Set(hood.nodes.map((n) => n.data.id))
  const haveEdge = new Set(hood.edges.map((e) => e.data.id))
  for (const n of path.nodes) if (!haveNode.has(n.data.id)) nodes.push(n)
  for (const e of path.edges) if (!haveEdge.has(e.data.id)) edges.push(e)
  return { nodes, edges }
}

export default function KnowledgeGraph() {
  const [stats, setStats] = useState<GraphStats | null>(null)
  const [cases, setCases] = useState<GraphCase[]>([])
  const [search, setSearch] = useState('')
  // Picker filters (BL-20260429-23). Court values are free-form strings, so
  // the option list is derived from the data rather than a fixed enum.
  const [court, setCourt] = useState('')
  const [decidedFrom, setDecidedFrom] = useState('')
  const [decidedTo, setDecidedTo] = useState('')
  const [courtOptions, setCourtOptions] = useState<string[]>([])
  // Which node the inspector describes. Defaults to the selected case; a tap
  // on the canvas moves it without changing the neighborhood being shown.
  const [inspectedId, setInspectedId] = useState('')
  // The selected case is URL state (BL-20260831-02), so a neighborhood can be
  // linked to and Back walks the cases you looked at. `''` means "none yet".
  const [selectedId, setSelectedId] = useUrlState<string>('case', {
    fallback: '',
  })
  const [neighborhood, setNeighborhood] =
    useState<GraphNeighborhood>(EMPTY_NEIGHBORHOOD)
  // Precedent chain (BL-20260429-22). The second endpoint is URL state too, so
  // a chain can be linked to exactly like a neighborhood.
  const [compareId, setCompareId] = useUrlState<string>('compare', {
    fallback: '',
  })
  const [path, setPath] = useState<GraphPath | null>(null)
  const [loadingPath, setLoadingPath] = useState(false)
  const [available, setAvailable] = useState<boolean>(true)
  const [loadingCases, setLoadingCases] = useState(false)
  const [loadingHood, setLoadingHood] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // What the URL asked for on arrival. The initial load runs once, and a
  // shared link must beat the auto-select — capturing it here keeps that
  // decision out of the effect's dependencies.
  const [linkedCaseId] = useState(selectedId)
  // The auto-select is not a navigation: nobody chose the first case, so it
  // must not become a history entry (BL-20260831-02). Pushing it made Back
  // *inside* the screen land on `/graph` with nothing selected and nothing to
  // re-select it — a dead end you had to press Back twice to leave. Replacing
  // keeps `/graph` and `/graph?case=<first>` as one entry, so Back still
  // steps out of cases you actually clicked, then out of the screen.
  const replaceView = useUrlWrite('replace')

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
        setCourtOptions(collectCourts([], c.cases))
        setAvailable(s.available && c.available)
        // Auto-select the first case only when the URL did not name one —
        // a shared link must land on the case it names.
        if (!linkedCaseId && c.cases.length > 0) {
          replaceView({ case: c.cases[0].id })
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

  // Debounced search + filters
  useEffect(() => {
    const filtersActive = Boolean(court || decidedFrom || decidedTo)
    if (search === '' && !filtersActive && cases.length > 0) return
    const id = setTimeout(() => {
      void (async () => {
        setLoadingCases(true)
        try {
          const c = await fetchGraphCases(search, 25, {
            court,
            decided_from: decidedFrom,
            decided_to: decidedTo,
          })
          setCases(c.cases)
          // Keep every court we have ever seen in the dropdown: filtering by
          // one must not erase the others from the list.
          setCourtOptions((prev) => collectCourts(prev, c.cases))
        } catch {
          // soft-fail; banner already shown if needed
        } finally {
          setLoadingCases(false)
        }
      })()
    }, 250)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, court, decidedFrom, decidedTo])

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
          setError(
            err instanceof Error ? err.message : 'Failed to load neighborhood',
          )
        }
      } finally {
        if (!cancelled) setLoadingHood(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedId])

  // Fetch the precedent chain whenever both endpoints are chosen. A stale
  // result is masked by `activePath` below rather than cleared here, so this
  // effect never sets state synchronously.
  useEffect(() => {
    if (!selectedId || !compareId) return
    let cancelled = false
    setLoadingPath(true)
    void (async () => {
      try {
        const p = await fetchGraphPath(selectedId, compareId)
        if (!cancelled) setPath(p)
      } catch (err) {
        if (!cancelled) {
          setPath(null)
          setError(err instanceof Error ? err.message : 'Failed to load path')
        }
      } finally {
        if (!cancelled) setLoadingPath(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedId, compareId, setError])

  const selectedCase = useMemo(
    () => cases.find((c) => c.id === selectedId) ?? null,
    [cases, selectedId],
  )

  // Only show a chain while both of its endpoints are still chosen.
  const activePath = selectedId && compareId ? path : null

  const elements = useMemo(
    () => mergePath(neighborhood, activePath),
    [neighborhood, activePath],
  )

  // The inspected node, resolved from the canvas payload first (it carries
  // the full property set) and falling back to the picker row.
  const inspected = useMemo(() => {
    const wanted = inspectedId || selectedId
    if (!wanted) return null
    const node = elements.nodes.find((n) => n.data.id === wanted)
    if (node) return node.data
    const row = cases.find((c) => c.id === wanted)
    return row
      ? { ...row, label: row.title ?? row.id, type: 'Case' as const }
      : null
  }, [elements, cases, inspectedId, selectedId])

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
        {/* Pinned case picker: on a wide screen the list is the navigation for
         * the graph beside it, so it holds position and scrolls itself
         * instead of riding the page away from the canvas.
         *
         * `lg:self-start` is load-bearing, not cosmetic: a grid item defaults
         * to `align-self: stretch`, which makes it exactly as tall as its row
         * — leaving `position: sticky` no distance to travel, so it silently
         * does nothing. */}
        <section
          aria-labelledby="cases-heading"
          className="flex flex-col rounded-2xl border border-slate-800 bg-slate-900/40 p-4 lg:sticky lg:top-[calc(var(--shell-pageheader-h)+1rem)] lg:max-h-[calc(100dvh-var(--shell-masthead-h)-var(--shell-pageheader-h)-3rem)] lg:self-start"
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
          {/* A placeholder is not a label: it vanishes the moment the user
           * types, and it is the only thing that named this control. */}
          <input
            type="search"
            aria-label="Search cases by title or id"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search title or id…"
            className="mb-3 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-blue-500 focus-ring"
          />
          <CaseFilters
            court={court}
            courtOptions={courtOptions}
            decidedFrom={decidedFrom}
            decidedTo={decidedTo}
            onCourt={setCourt}
            onDecidedFrom={setDecidedFrom}
            onDecidedTo={setDecidedTo}
          />
          <ul
            data-testid="case-list"
            className="shell-panel-scroll max-h-[520px] flex-1 space-y-1 pr-1 lg:max-h-none"
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
                  <div className="truncate font-medium">{c.title || c.id}</div>
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
          <PathPicker
            cases={cases}
            selectedId={selectedId}
            compareId={compareId}
            onCompare={setCompareId}
            path={activePath}
            loading={loadingPath}
          />
          <Legend hasPath={Boolean(activePath?.found)} />
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_260px]">
            <div>
              <GraphViewer elements={elements} onSelectNode={setInspectedId} />
              <div className="mt-2 flex justify-between text-[10px] text-slate-500">
                <span>{elements.nodes.length} nodes</span>
                <span>{elements.edges.length} edges</span>
              </div>
              {/* BL-20260831-12: the canvas is a picture. Following a CITES
                  edge — the actual research move — needs a control, so the
                  neighbours are buttons a keyboard can reach. */}
              <CitesTraversal
                elements={elements}
                selectedId={selectedId}
                onSelect={setSelectedId}
              />
            </div>
            <NodeInspector node={inspected} />
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

/** Court + decided-date filters for the case picker (BL-20260429-23). */
function CaseFilters({
  court,
  courtOptions,
  decidedFrom,
  decidedTo,
  onCourt,
  onDecidedFrom,
  onDecidedTo,
}: {
  court: string
  courtOptions: string[]
  decidedFrom: string
  decidedTo: string
  onCourt: (v: string) => void
  onDecidedFrom: (v: string) => void
  onDecidedTo: (v: string) => void
}) {
  const active = Boolean(court || decidedFrom || decidedTo)
  return (
    <div className="mb-3 space-y-2">
      <div>
        <label
          htmlFor="graph-court"
          className="mb-1 block text-[10px] uppercase tracking-wider text-slate-500"
        >
          Court
        </label>
        <select
          id="graph-court"
          value={court}
          onChange={(e) => onCourt(e.target.value)}
          className="w-full rounded-md border border-slate-800 bg-slate-950 px-2 py-1.5 text-xs text-slate-200 focus-ring"
        >
          <option value="">All courts</option>
          {courtOptions.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label
            htmlFor="graph-decided-from"
            className="mb-1 block text-[10px] uppercase tracking-wider text-slate-500"
          >
            Decided from
          </label>
          <input
            id="graph-decided-from"
            type="date"
            value={decidedFrom}
            onChange={(e) => onDecidedFrom(e.target.value)}
            className="w-full rounded-md border border-slate-800 bg-slate-950 px-2 py-1.5 text-xs text-slate-200 focus-ring"
          />
        </div>
        <div>
          <label
            htmlFor="graph-decided-to"
            className="mb-1 block text-[10px] uppercase tracking-wider text-slate-500"
          >
            Decided to
          </label>
          <input
            id="graph-decided-to"
            type="date"
            value={decidedTo}
            onChange={(e) => onDecidedTo(e.target.value)}
            className="w-full rounded-md border border-slate-800 bg-slate-950 px-2 py-1.5 text-xs text-slate-200 focus-ring"
          />
        </div>
      </div>
      {active && (
        <button
          type="button"
          onClick={() => {
            onCourt('')
            onDecidedFrom('')
            onDecidedTo('')
          }}
          className="w-full rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-300 hover:border-blue-500/50 hover:text-white"
        >
          Reset filters
        </button>
      )}
    </div>
  )
}

/** Human labels for the raw graph property keys the inspector lists. */
const INSPECTOR_LABELS: Record<string, string> = {
  id: 'ID',
  type: 'Type',
  title: 'Title',
  court: 'Court',
  decided_at: 'Decided',
  normalized: 'Normalized',
  text: 'Citation text',
  source: 'Source',
  confidence: 'Confidence',
  ingest_timestamp: 'Ingested',
  agent_version: 'Agent version',
}

/**
 * Sidebar inspector for the selected node (BL-20260429-23).
 *
 * Lists every property the graph actually carries — `label`, `on_path` and
 * `source_url` excepted: the first two are rendering state, and the URL is
 * shown as a link at the end rather than as raw text.
 */
function NodeInspector({
  node,
}: {
  node: (Record<string, unknown> & { id: string }) | null
}) {
  const entries = node
    ? Object.entries(node).filter(
        ([key, value]) =>
          !['label', 'on_path', 'source_url'].includes(key) &&
          value !== null &&
          value !== undefined &&
          value !== '',
      )
    : []
  const sourceUrl =
    node && typeof node.source_url === 'string' ? node.source_url : null

  return (
    <aside
      aria-labelledby="inspector-heading"
      data-testid="node-inspector"
      className="rounded-lg border border-slate-800 bg-slate-950/60 p-3"
    >
      <h3
        id="inspector-heading"
        className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400"
      >
        Inspector
      </h3>
      {!node ? (
        <p className="text-[11px] text-slate-500">
          Select a case, or click a node on the canvas, to see its full
          properties.
        </p>
      ) : (
        <>
          <dl className="space-y-1.5 text-[11px]">
            {entries.map(([key, value]) => (
              <div key={key}>
                <dt className="text-slate-500">
                  {INSPECTOR_LABELS[key] ?? key}
                </dt>
                <dd className="break-words font-mono text-slate-200">
                  {String(value)}
                </dd>
              </div>
            ))}
          </dl>
          {sourceUrl && (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noreferrer noopener"
              className="mt-3 inline-block rounded-md border border-slate-700 px-2 py-1 text-[11px] text-blue-300 hover:border-blue-500/50 hover:text-blue-200 focus-ring"
            >
              Open source ↗
            </a>
          )}
        </>
      )}
    </aside>
  )
}

function StatsStrip({ stats }: { stats: GraphStats | null }) {
  const items = [
    { label: 'Cases', value: stats?.cases ?? '—', tone: 'text-blue-300' },
    {
      label: 'Citations',
      value: stats?.citations ?? '—',
      tone: 'text-amber-300',
    },
    {
      label: 'CITES edges',
      value: stats?.cites_edges ?? '—',
      tone: 'text-emerald-300',
    },
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

/**
 * Second endpoint for the precedent chain (BL-20260429-22).
 *
 * The result line is deliberately explicit about "no chain within N hops":
 * an empty highlight and an unreachable pair look identical on the canvas.
 */
function PathPicker({
  cases,
  selectedId,
  compareId,
  onCompare,
  path,
  loading,
}: {
  cases: GraphCase[]
  selectedId: string
  compareId: string
  onCompare: (id: string) => void
  path: GraphPath | null
  loading: boolean
}) {
  const options = cases.filter((c) => c.id !== selectedId)
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs">
      <label htmlFor="graph-compare" className="text-slate-400">
        Precedent chain to
      </label>
      <select
        id="graph-compare"
        value={compareId}
        onChange={(e) => onCompare(e.target.value)}
        disabled={!selectedId}
        className="min-w-[12rem] rounded-md border border-slate-800 bg-slate-950 px-2 py-1 text-slate-200 focus-ring disabled:opacity-50"
      >
        <option value="">None</option>
        {options.map((c) => (
          <option key={c.id} value={c.id}>
            {c.title || c.id}
          </option>
        ))}
      </select>
      {compareId && (
        <button
          type="button"
          onClick={() => onCompare('')}
          className="rounded-md border border-slate-700 px-2 py-1 text-slate-300 hover:border-blue-500/50 hover:text-white"
        >
          Clear chain
        </button>
      )}
      <span role="status" className="text-slate-500">
        {loading
          ? 'Finding chain…'
          : !compareId
            ? ''
            : path?.found
              ? `Chain found: ${path.hops} hop${path.hops === 1 ? '' : 's'}`
              : 'No chain within 6 hops'}
      </span>
    </div>
  )
}

/**
 * Keyboard-operable traversal of the `CITES` edges around the selected case
 * (BL-20260831-12).
 *
 * The canvas is `role="img"` and the case list beside it covers *reading* the
 * corpus; neither lets you do the thing citation research is: step from a case
 * to one it cites, then to one that cites *that*. Each neighbour is a plain
 * button that re-selects the case, so the trail is walkable with Tab and Enter
 * and the Back button unwinds it (the selection is URL state).
 *
 * `Citation` nodes are shown as text, not controls: they are not cases and
 * selecting one would load nothing.
 */
function CitesTraversal({
  elements,
  selectedId,
  onSelect,
}: {
  elements: { nodes: GraphNode[]; edges: GraphEdge[] }
  selectedId: string
  onSelect: (id: string) => void
}) {
  const { cites, citedBy } = useMemo(() => {
    const byId = new Map(elements.nodes.map((n) => [n.data.id, n]))
    const out: GraphNode[] = []
    const inc: GraphNode[] = []
    const seenOut = new Set<string>()
    const seenIn = new Set<string>()
    for (const edge of elements.edges) {
      if (edge.data.type !== 'CITES') continue
      if (edge.data.source === selectedId) {
        const node = byId.get(edge.data.target)
        if (node && !seenOut.has(node.data.id)) {
          seenOut.add(node.data.id)
          out.push(node)
        }
      } else if (edge.data.target === selectedId) {
        const node = byId.get(edge.data.source)
        if (node && !seenIn.has(node.data.id)) {
          seenIn.add(node.data.id)
          inc.push(node)
        }
      }
    }
    return { cites: out, citedBy: inc }
  }, [elements, selectedId])

  if (!selectedId) return null

  return (
    <div className="mt-3" data-testid="cites-traversal">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        Follow a citation
      </h3>
      <div className="mt-2 grid gap-3 sm:grid-cols-2">
        <TraversalList
          label="This case cites"
          nodes={cites}
          empty="No outgoing citations in this neighborhood."
          onSelect={onSelect}
        />
        <TraversalList
          label="Cited by"
          nodes={citedBy}
          empty="No citing cases in this neighborhood."
          onSelect={onSelect}
        />
      </div>
    </div>
  )
}

function TraversalList({
  label,
  nodes,
  empty,
  onSelect,
}: {
  label: string
  nodes: GraphNode[]
  empty: string
  onSelect: (id: string) => void
}) {
  return (
    <div>
      <h4 className="text-[10px] uppercase tracking-wider text-slate-600">
        {label}
      </h4>
      {nodes.length === 0 ? (
        <p className="mt-1 text-[11px] text-slate-600">{empty}</p>
      ) : (
        <ul aria-label={label} className="mt-1 space-y-1">
          {nodes.map((node) => (
            <li key={node.data.id}>
              {node.data.type === 'Case' ? (
                <button
                  type="button"
                  onClick={() => onSelect(node.data.id)}
                  className="w-full rounded border border-slate-800 bg-slate-950/60 px-2 py-1 text-left text-xs text-slate-300 hover:border-blue-500/50 hover:text-blue-200 focus-ring"
                >
                  {node.data.title || node.data.label || node.data.id}
                  {node.data.court && (
                    <span className="ml-1 text-[10px] text-slate-500">
                      {node.data.court}
                    </span>
                  )}
                </button>
              ) : (
                <span className="block px-2 py-1 text-xs text-slate-500">
                  {node.data.label || node.data.id}{' '}
                  <span className="text-[10px] uppercase tracking-wider">
                    citation
                  </span>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Legend({ hasPath = false }: { hasPath?: boolean }) {
  // The graph sizes case nodes by how often they are cited here
  // (BL-20260803-03). Constitution §13 allows the signal only if it is
  // labelled as what it measures, so the legend names it — "litigation
  // frequency", never "importance" or "authority" — whenever it is on.
  const [showCounts] = useSetting(showCitationCounts)
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
      {showCounts && (
        <span
          data-testid="legend-citation-size"
          title="Bigger node = cited more often by the other cases shown here. Citation volume measures litigation frequency and repeat-player resources, not legal correctness or authority (constitution §13)."
          className="inline-flex items-center gap-1.5"
        >
          <span className="inline-flex items-end gap-0.5" aria-hidden>
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-500" />
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-blue-500" />
          </span>
          Node size = litigation frequency (times cited here), not importance
        </span>
      )}
      {hasPath && (
        <span className="inline-flex items-center gap-1.5 text-emerald-300">
          <span className="inline-block h-px w-6 bg-emerald-400" />
          Precedent chain
        </span>
      )}
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
