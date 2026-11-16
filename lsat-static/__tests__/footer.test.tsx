/**
 * The footer's "source" link (law-ai#116).
 *
 * The footer sits under every destination, next to the line saying progress
 * is stored only in this browser, and its "source" link is where a visitor
 * checks that claim. The Overview's "open source" link has been pinned by
 * `Overview.test.tsx` since BL-20260831-25; this one was pinned by nothing.
 * While the repository was private, GitHub answered both links with a 404
 * for every visitor who was not a collaborator, and no test was in a position
 * to notice the footer half. The repository is public under the MIT licence
 * now, so both links resolve and the "open source" claim is true.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import Page from '@/app/page'

vi.mock('@/lib/data', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/data')>()
  const f = await import('./fixtures')
  return { ...actual, questionsFor: () => f.QUESTIONS, guideFor: () => undefined }
})

/** The URL `Overview.test.tsx` pins for the "open source" link. */
const REPOSITORY = 'https://github.com/bamr87/law-ai'

function footerSourceLink(): HTMLElement {
  // Deliberately not a <footer> (see app/page.tsx), so there is no landmark
  // role to find it by.
  const footer = document.querySelector<HTMLElement>('.site-footer')
  if (!footer) throw new Error('the page rendered no .site-footer')
  return within(footer).getByRole('link', { name: 'source' })
}

describe('the site footer', () => {
  it('links "source" to the public repository', () => {
    render(<Page />)
    expect(footerSourceLink()).toHaveAttribute('href', REPOSITORY)
  })

  it('keeps the link under every destination, not only the Overview', () => {
    render(<Page />)
    const nav = screen.getByRole('navigation', { name: 'Sections' })
    for (const destination of within(nav).getAllByRole('button')) {
      fireEvent.click(destination)
      expect(destination).toHaveAttribute('aria-current', 'page')
      expect(footerSourceLink()).toHaveAttribute('href', REPOSITORY)
    }
  })
})
