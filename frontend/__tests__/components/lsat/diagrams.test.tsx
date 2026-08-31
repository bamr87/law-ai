/** Renderer tests for the solve-guide diagrams (spec 041 T-007, AC-5). */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import Representation from '@/components/lsat/diagrams/Representation'
import type {
  LsatArgumentMapRep,
  LsatGridRep,
  LsatNotationRep,
  LsatPassageMapRep,
  LsatSequenceRep,
} from '@/lib/api'

describe('SequenceBoard', () => {
  const rep: LsatSequenceRep = {
    rep_type: 'sequence',
    slots: ['1', '2', '3', '4', '5'],
    entities: ['F', 'G', 'H', 'J', 'K'],
    placements: { '4': 'J' },
    exclusions: { '1': ['K'] },
    note: 'J is fixed.',
  }

  it('renders slots left-to-right with placements, exclusions, and an a11y label', () => {
    render(<Representation rep={rep} />)
    const board = screen.getByRole('img')
    const label = board.getAttribute('aria-label') ?? ''
    expect(label).toContain('5 slots')
    expect(label).toContain('Slot 4: J')
    expect(label).toContain('Slot 1 excludes K')
    // Placed entity and exclusion marks are visible in the SVG.
    expect(board.textContent).toContain('J')
    expect(board.textContent).toContain('~K')
    expect(screen.getByText('J is fixed.')).toBeInTheDocument()
  })
})

describe('GroupGrid', () => {
  const rep: LsatGridRep = {
    rep_type: 'grid',
    rows: ['A', 'B'],
    columns: ['[F H]', 'J = 4'],
    cells: [
      { row: 'A', column: '[F H]', mark: 'no', note: 'F and H split.' },
      { row: 'B', column: 'J = 4', mark: 'yes' },
    ],
    note: 'Rows are answer choices.',
  }

  it('renders an accessible table with symbol marks', () => {
    render(<Representation rep={rep} />)
    const table = screen.getByRole('table')
    expect(table).toHaveAccessibleName(/rows are answer choices/i)
    expect(screen.getByRole('rowheader', { name: 'A' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'J = 4' })).toBeInTheDocument()
    // Symbol + sr-only text, never colour alone.
    expect(screen.getAllByText(/✕/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/✓/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/\bno\b/).length).toBeGreaterThan(0)
  })
})

describe('RuleNotation', () => {
  const rep: LsatNotationRep = {
    rep_type: 'notation',
    rules: [
      {
        rule_text: 'If the contract is enforceable, it was signed.',
        symbols: 'E → S',
        note: 'E = enforceable.',
      },
      { rule_text: 'F immediately before H.', symbols: '[F H]' },
    ],
  }

  it('renders symbol strings with their source rules and a legend', () => {
    render(<Representation rep={rep} />)
    expect(screen.getByText('E → S')).toBeInTheDocument()
    expect(
      screen.getByText('If the contract is enforceable, it was signed.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/legend/i)).toBeInTheDocument()
    expect(screen.getByText(/if… then/i)).toBeInTheDocument()
  })
})

describe('ArgumentMap', () => {
  const rep: LsatArgumentMapRep = {
    rep_type: 'argument_map',
    nodes: [
      { id: 'p1', role: 'premise', text: 'All senior partners have argued.' },
      { id: 'c', role: 'conclusion', text: 'Maria has argued.' },
    ],
    edges: [{ from: 'p1', to: 'c', relation: 'supports' }],
  }

  it('renders premise and conclusion boxes with a structural a11y label', () => {
    render(<Representation rep={rep} />)
    const map = screen.getByRole('img')
    expect(map.getAttribute('aria-label')).toContain('supports')
    expect(screen.getByText('Premise')).toBeInTheDocument()
    expect(screen.getByText('Conclusion')).toBeInTheDocument()
    expect(screen.getByText('Maria has argued.')).toBeInTheDocument()
  })
})

describe('PassageMap', () => {
  const rep: LsatPassageMapRep = {
    rep_type: 'passage_map',
    paragraphs: [
      { paragraph: 1, role: 'Problem', gist: 'Writ pleading punished missteps.' },
      { paragraph: 2, role: 'Reform', gist: 'Notice pleading proposed.' },
    ],
  }

  it('renders an ordered list of paragraph roles', () => {
    render(<Representation rep={rep} />)
    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('Problem')).toBeInTheDocument()
    expect(screen.getByText('Notice pleading proposed.')).toBeInTheDocument()
    expect(screen.getByLabelText('Paragraph 2')).toBeInTheDocument()
  })
})
