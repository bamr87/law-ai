'use client'

import type { GraphEdge, GraphNode } from '@/lib/api'
import type { LayoutOptions } from 'cytoscape'
import { useEffect, useRef } from 'react'

interface GraphViewerProps {
  elements: { nodes: GraphNode[]; edges: GraphEdge[] }
  height?: number
}

/**
 * Cytoscape-backed graph canvas (spec 006, closes BL-20260430-05).
 *
 * Cytoscape is dynamically imported so the ~150KB bundle is only loaded
 * on routes that actually mount this component (R-1 in plan.md).
 */
export default function GraphViewer({ elements, height = 600 }: GraphViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<{ destroy: () => void } | null>(null)

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
        elements: [...elements.nodes, ...elements.edges],
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
        ],
        layout: {
          name: 'cose',
          animate: false,
          nodeRepulsion: () => 6000,
          idealEdgeLength: () => 90,
        } as unknown as LayoutOptions,
      })
      cyRef.current = cy
    })()
    return () => {
      cancelled = true
      cyRef.current?.destroy()
      cyRef.current = null
    }
  }, [elements])

  // Cytoscape paints into bare <canvas> children, which reach a screen reader
  // as three anonymous graphics. Name the region for what it actually shows
  // and point at the case list, which is the equivalent accessible interface.
  const nodes = elements.nodes.length
  const edges = elements.edges.length

  return (
    <div
      ref={containerRef}
      data-testid="graph-canvas"
      role="img"
      aria-label={
        `Citation neighborhood: ${nodes} case${nodes === 1 ? '' : 's'}, ` +
        `${edges} citation edge${edges === 1 ? '' : 's'}. ` +
        'The case list beside this canvas is the equivalent accessible view.'
      }
      className="w-full rounded-2xl border border-slate-800 bg-slate-950"
      style={{ height }}
    />
  )
}