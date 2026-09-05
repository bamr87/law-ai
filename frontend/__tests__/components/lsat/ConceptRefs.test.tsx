/** Tests for the post-grade concept reference block (spec 041 FR-12). */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import ConceptRefs, {
  resetConceptCatalog,
} from '@/components/lsat/ConceptRefs'

/**
 * FR-12's actual guarantee: a graded question never hands the learner off to
 * a third party. Since the concepts merge the block does carry one anchor —
 * inward, to the concept's entry in the library — so the invariant is "no
 * external href", not "no anchor".
 */
function expectNoExternalLink(): void {
  for (const link of screen.queryAllByRole('link')) {
    expect(link.getAttribute('href')).toMatch(/^\/lsat\/library#catalog-/)
  }
}

describe('ConceptRefs', () => {
  beforeEach(() => {
    resetConceptCatalog()
  })

  it('resolves concepts to name, summary, and schema examples', async () => {
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
    // component must not render it.
    expect(screen.queryByText(/SEP — Logic/)).not.toBeInTheDocument()
    expectNoExternalLink()
  })

  it('offers the one inward link, into the library catalog', async () => {
    render(<ConceptRefs conceptIds={['modus-tollens']} />)
    const link = await screen.findByRole('link', {
      name: /Study Modus tollens in the library/i,
    })
    // The concept's own entry in the merged library, not the article reader
    // and not an outside source: a missed question is exactly when a learner
    // wants the cross-references and the material that teaches the concept.
    expect(link).toHaveAttribute('href', '/lsat/library#catalog-modus-tollens')
  })

  it('falls back to an id chip for concepts missing from the catalog', async () => {
    render(<ConceptRefs conceptIds={['modus-tollens', 'unknown-concept']} />)
    await screen.findByText('Modus tollens')
    expect(screen.getByText('unknown-concept')).toBeInTheDocument()
    // An unresolved id gets a chip and no link — there is nothing in the
    // catalog to link it to.
    expect(screen.getAllByRole('link')).toHaveLength(1)
    expectNoExternalLink()
  })

  it('renders nothing without concept ids', () => {
    const { container } = render(<ConceptRefs conceptIds={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
