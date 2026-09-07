'use client'

import { useSetting } from '@/components/shell/useSetting'
import type { GraphEdge, GraphNode } from '@/lib/api'
import { showCitationCounts } from '@/lib/settings/catalog'
import type { LayoutOptions } from 'cytoscape'
import { useEffect, useMemo, useRef } from 'react'

/** The slice of the Cytoscape instance this component actually touches. */
interface CyNode {
  id: () => string
  select?: () => void
  unselect?: () => void
}

interface CyHandle {
  destroy: () => void
  /** Cytoscape returns a NodeCollection: array-*like*, not an Array. */
  nodes?: () => ArrayLike<CyNode>
}

interface GraphViewerProps {
  elements: { nodes: GraphNode[]; edges: GraphEdge[] }
  height?: number
  /** Called with the node id when a node is tapped (BL-20260429-23). */
  onSelectNode?: (nodeId: string) => void
  /** Overrides the canvas description; defaults to the neighborhood wording. */
  label?: string
}

/**
 * Cytoscape-backed graph canvas (spec 006, closes BL-20260430-05).
 *
 * Cytoscape is dynamically imported so the ~150KB bundle is only loaded
 * on routes that actually mount this component (R-1 in plan.md).
 */
export default function GraphViewer({
  elements,
  height = 600,
  onSelectNode,
  label,
}: GraphViewerProps) {
  // BL-20260803-03 / constitution §13. The setting has always promised that
  // the graph can size nodes by citation count and that the legend will call
  // that number what it is; until now nothing read it and every node was the
  // same size. In-degree is computed here, from the edges already on screen —
  // it is "how often this case is cited *in this neighborhood*", never a
  // ranking of importance, authority or correctness.
  const [showCounts] = useSetting(showCitationCounts)
  const { cyElements, maxCites } = useMemo(() => {
    const indegree = new Map<string, number>()
    for (const edge of elements.edges) {
      if (edge.data.type !== 'CITES') continue
      indegree.set(edge.data.target, (indegree.get(edge.data.target) ?? 0) + 1)
    }
    const nodes = elements.nodes.map((n) => ({
      data: { ...n.data, cites_in: indegree.get(n.data.id) ?? 0 },
    }))
    let max = 0
    for (const count of indegree.values()) max = Math.max(max, count)
    return { cyElements: [...nodes, ...elements.edges], maxCites: max }
  }, [elements])
  const sizedByCitations = showCounts && maxCites > 0

  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<{ destroy: () => void } | null>(null)
  // Which node the keyboard is on (BL-20260831-12). An index, not a node
  // reference, so a re-layout cannot leave it pointing at a destroyed object.
  const cursorRef = useRef(0)
  // Held in a ref so changing the callback never tears down and re-lays-out
  // the graph — only `elements` should do that. Written in an effect, since a
  // ref must not be touched during render.
  const onSelectRef = useRef(onSelectNode)
  useEffect(() => {
    onSelectRef.current = onSelectNode
  }, [onSelectNode])

  useEffect(() => {
    let cancelled = false
    if (!containerRef.current) return
    const container = containerRef.current
    void (async () => {
      const cytoscape = (await import('cytoscape')).default
      if (cancelled) return
      cyRef.current?.destroy()
      const cy = cytoscape({
        container,
        elements: cyElements,
        style: [
          {
            selector: 'node[type = "Case"]',
            style: {
              'background-color': '#3b82f6',
              label: 'data(label)',
              color: '#e2e8f0',
              'font-size': 11,
              'text-wrap': 'wrap',
              'text-max-width': '140px',
              'text-valign': 'bottom',
              'text-margin-y': 6,
              width: 28,
              height: 28,
              'border-width': 2,
              'border-color': '#1e3a8a',
            },
          },
          {
            selector: 'node[type = "Citation"]',
            style: {
              'background-color': '#f59e0b',
              shape: 'diamond',
              label: 'data(label)',
              color: '#fde68a',
              'font-size': 9,
              'text-wrap': 'wrap',
              'text-max-width': '120px',
              'text-valign': 'bottom',
              'text-margin-y': 4,
              width: 18,
              height: 18,
            },
          },
          {
            selector: 'edge[type = "CITES"]',
            style: {
              'curve-style': 'bezier',
              'target-arrow-shape': 'triangle',
              width: 2,
              'line-color': '#60a5fa',
              'target-arrow-color': '#60a5fa',
            },
          },
          {
            selector: 'edge[type = "HAS_CITATION"]',
            style: {
              'curve-style': 'bezier',
              width: 1,
              'line-color': '#475569',
              'line-style': 'dashed',
            },
          },
          // Litigation frequency, drawn (BL-20260803-03). Placed before the
          // precedent-chain rules so a chain still recolours a sized node.
          ...(sizedByCitations
            ? [
                {
                  selector: 'node[type = "Case"]',
                  style: {
                    width: `mapData(cites_in, 0, ${maxCites}, 26, 58)`,
                    height: `mapData(cites_in, 0, ${maxCites}, 26, 58)`,
                  },
                },
              ]
            : []),
          // Precedent chain (BL-20260429-22): nodes and edges returned by
          // /api/graph/path carry `on_path`, so the chain reads as one lit
          // route rather than another blue subgraph.
          {
            selector: 'node[?on_path]',
            style: {
              'background-color': '#34d399',
              'border-color': '#065f46',
              'border-width': 3,
              color: '#d1fae5',
            },
          },
          {
            selector: 'edge[?on_path]',
            style: {
              'line-color': '#34d399',
              'target-arrow-color': '#34d399',
              width: 4,
            },
          },
        ],
        layout: {
          name: 'cose',
          animate: false,
          nodeRepulsion: () => 6000,
          idealEdgeLength: () => 90,
        } as unknown as LayoutOptions,
      })
      cy.on('tap', 'node', (evt: { target: { id: () => string } }) => {
        onSelectRef.current?.(evt.target.id())
      })
      cyRef.current = cy
    })()
    return () => {
      cancelled = true
      cyRef.current?.destroy()
      cyRef.current = null
    }
  }, [cyElements, sizedByCitations, maxCites])

  // Cytoscape paints into bare <canvas> children, which reach a screen reader
  // as three anonymous graphics. Name the region for what it actually shows
  // and point at the case list, which is the equivalent accessible interface.
  const nodes = elements.nodes.length
  const edges = elements.edges.length

  // Progressive enhancement (BL-20260831-12): arrows step through the nodes
  // and Enter selects one, so the canvas is not a dead end for a keyboard.
  // The "Follow a citation" list below it stays the equivalent, tested path —
  // Cytoscape paints to <canvas>, which no assistive tech can read.
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    // Cytoscape's own `Core` type is wider than what this handler touches.
    const handle = cyRef.current as CyHandle | null
    const all = Array.from(handle?.nodes?.() ?? [])
    if (all.length === 0) return
    const step =
      e.key === 'ArrowRight' || e.key === 'ArrowDown'
        ? 1
        : e.key === 'ArrowLeft' || e.key === 'ArrowUp'
          ? -1
          : 0
    if (step !== 0) {
      e.preventDefault()
      const next = (cursorRef.current + step + all.length) % all.length
      cursorRef.current = next
      for (const node of all) node.unselect?.()
      all[next]?.select?.()
      return
    }
    if (e.key === 'Enter' || e.key === ' ') {
      const node = all[cursorRef.current]
      if (!node) return
      e.preventDefault()
      onSelectRef.current?.(node.id())
    }
  }

  return (
    <div
      ref={containerRef}
      data-testid="graph-canvas"
      role="img"
      tabIndex={0}
      onKeyDown={onKeyDown}
      aria-label={
        label ??
        `Citation neighborhood: ${nodes} case${nodes === 1 ? '' : 's'}, ` +
          `${edges} citation edge${edges === 1 ? '' : 's'}. ` +
          (sizedByCitations
            ? 'Node size shows how often a case is cited within this ' +
              'neighborhood — a measure of litigation frequency, not of ' +
              'legal correctness or authority. '
            : '') +
          'Arrow keys step through nodes and Enter selects one; the case list ' +
          'and the "Follow a citation" list beside this canvas are the ' +
          'equivalent accessible view.'
      }
      className="w-full rounded-2xl border border-slate-800 bg-slate-950 focus-ring"
      style={{ height }}
    />
  )
}
