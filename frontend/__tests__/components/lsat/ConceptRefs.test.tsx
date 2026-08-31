/** Tests for the post-grade concept reference block (spec 041 FR-12). */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import ConceptRefs, {
  resetConceptCatalog,
} from '@/components/lsat/ConceptRefs'

describe('ConceptRefs', () => {
  beforeEach(() => {
    resetConceptCatalog()
  })

  it('resolves concepts to name, summary, and schema examples — never links', async () => {
    render(<ConceptRefs conceptIds={['modus-tollens']} />)
    expect(screen.getByText(/Derived from/i)).toBeInTheDocument()
    const name = await screen.findByText('Modus tollens')
    fireEvent.click(name)
    expect(
      screen.getByText('Deny the consequent to deny the antecedent.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/Schema \/ examples/i)).toBeInTheDocument()
    expect(
      screen.getByText('If P then Q. Not Q. Therefore not P.'),
    ).toBeInTheDocument()
    // The catalog fixture carries an external reference (SEP — Logic); the
    // component must not render it or any anchor at all.
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.queryByText(/SEP — Logic/)).not.toBeInTheDocument()
  })

  it('falls back to an id chip for concepts missing from the catalog', async () => {
    render(<ConceptRefs conceptIds={['modus-tollens', 'unknown-concept']} />)
    await screen.findByText('Modus tollens')
    expect(screen.getByText('unknown-concept')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('renders nothing without concept ids', () => {
    const { container } = render(<ConceptRefs conceptIds={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
