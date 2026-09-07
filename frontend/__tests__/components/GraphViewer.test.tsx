/**
 * GraphViewer — canvas configuration.
 *
 * The component talks to Cytoscape, which needs a real canvas; jsdom has
 * none. The mock therefore captures the config object instead, which is the
 * part worth pinning: the layout must not animate (BL-20260831-03 —
 * `prefers-reduced-motion` cannot reach a canvas animation, so the layout is
 * simply never animated for anyone).
 */
import GraphViewer from '@/components/GraphViewer'
import { render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

interface CyConfig {
  layout: { name: string; animate: boolean }
  style: Array<Record<string, unknown>>
  elements: unknown[]
}

const configs: CyConfig[] = []

vi.mock('cytoscape', () => ({
  default: (config: CyConfig) => {
    configs.push(config)
    return { destroy: vi.fn(), on: vi.fn() }
  },
}))

const elements = {
  nodes: [
    { data: { id: 'case:a', label: 'A v. B', type: 'Case' } },
    { data: { id: 'case:b', label: 'C v. D', type: 'Case' } },
  ],
  edges: [{ data: { source: 'case:a', target: 'case:b', type: 'CITES' } }],
} as unknown as Parameters<typeof GraphViewer>[0]['elements']

beforeEach(() => {
  configs.length = 0
})

describe('GraphViewer', () => {
  it('lays the graph out without animation (BL-20260831-03)', async () => {
    render(<GraphViewer elements={elements} />)
    await waitFor(() => expect(configs).toHaveLength(1))
    expect(configs[0].layout.animate).toBe(false)
  })

  it('names the canvas and points at the accessible equivalent', () => {
    const { getByTestId } = render(<GraphViewer elements={elements} />)
    const canvas = getByTestId('graph-canvas')
    expect(canvas).toHaveAttribute('role', 'img')
    expect(canvas.getAttribute('aria-label')).toMatch(
      /2 cases, 1 citation edge/,
    )
  })
})
