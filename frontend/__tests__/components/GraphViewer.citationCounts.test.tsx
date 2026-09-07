/**
 * BL-20260803-03 — citation counts, drawn and labelled.
 *
 * Spec 040 shipped `graph.show_citation_counts` (default on) and told users
 * the graph sizes nodes by citation count, with a legend that calls the number
 * litigation frequency; neither half existed. These tests pin both, and the
 * labelling half is the point: constitution §13 permits the signal only while
 * it is named for what it measures, never as importance or authority.
 */
import GraphViewer from '@/components/GraphViewer'
import { showCitationCounts } from '@/lib/settings/catalog'
import { upsertSettingValue } from '@/lib/scope/store'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

interface CyConfig {
  elements: { data: Record<string, unknown> }[]
  style: { selector: string; style: Record<string, unknown> }[]
}

const configs: CyConfig[] = []

vi.mock('cytoscape', () => ({
  default: (config: CyConfig) => {
    configs.push(config)
    return { destroy: vi.fn(), on: vi.fn(), nodes: () => [] }
  },
}))

/** Two cases citing a third, so in-degree is 2 / 0 / 0 and max is 2. */
const elements = {
  nodes: [
    { data: { id: 'case:a', label: 'A', type: 'Case' } },
    { data: { id: 'case:b', label: 'B', type: 'Case' } },
    { data: { id: 'case:c', label: 'C', type: 'Case' } },
  ],
  edges: [
    { data: { id: 'e1', source: 'case:a', target: 'case:c', type: 'CITES' } },
    { data: { id: 'e2', source: 'case:b', target: 'case:c', type: 'CITES' } },
  ],
} as unknown as Parameters<typeof GraphViewer>[0]['elements']

const sizeRule = (config: CyConfig) =>
  config.style.find(
    (rule) =>
      rule.selector === 'node[type = "Case"]' &&
      typeof rule.style.width === 'string' &&
      String(rule.style.width).startsWith('mapData'),
  )

beforeEach(() => {
  configs.length = 0
  localStorage.clear()
})

afterEach(() => {
  localStorage.clear()
})

describe('GraphViewer citation-count sizing', () => {
  it('sizes case nodes by how often they are cited here (default on)', async () => {
    render(<GraphViewer elements={elements} />)
    await waitFor(() => expect(configs).toHaveLength(1))
    const config = configs[0]

    const byId = new Map(
      config.elements.map((el) => [el.data.id as string, el.data]),
    )
    expect(byId.get('case:c')?.cites_in).toBe(2)
    expect(byId.get('case:a')?.cites_in).toBe(0)

    const rule = sizeRule(config)
    expect(rule).toBeDefined()
    expect(rule?.style.width).toBe('mapData(cites_in, 0, 2, 26, 58)')
    expect(rule?.style.height).toBe(rule?.style.width)
  })

  it('names the measure in the canvas description, and never calls it importance', async () => {
    const { getByTestId } = render(<GraphViewer elements={elements} />)
    const label = getByTestId('graph-canvas').getAttribute('aria-label') ?? ''
    expect(label).toMatch(/litigation frequency/i)
    expect(label).not.toMatch(/importance|authority score/i)
  })

  it('leaves every node the same size when the setting is off', async () => {
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: showCitationCounts.key,
      value: false,
      locked: false,
    })
    render(<GraphViewer elements={elements} />)
    await waitFor(() => expect(configs).toHaveLength(1))
    expect(sizeRule(configs[0])).toBeUndefined()
    // The data is still computed; only the mapping is withheld.
    expect(
      configs[0].elements.find((el) => el.data.id === 'case:c')?.data.cites_in,
    ).toBe(2)
  })

  it('does not map a size when nothing is cited (no range to map)', async () => {
    render(
      <GraphViewer
        elements={
          {
            nodes: [{ data: { id: 'case:a', label: 'A', type: 'Case' } }],
            edges: [],
          } as unknown as Parameters<typeof GraphViewer>[0]['elements']
        }
      />,
    )
    await waitFor(() => expect(configs).toHaveLength(1))
    expect(sizeRule(configs[0])).toBeUndefined()
  })
})
