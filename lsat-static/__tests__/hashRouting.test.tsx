/**
 * The destination is in the URL (#223).
 *
 * `app/page.tsx` kept the destination in React state alone, so the address
 * bar never said where the reader was. A cold `#article-<id>` permalink (the
 * thing BL-20260905-04 built to be shared) opened Overview, a reload reset to
 * Overview, and Back left the site. The Library's own fragment handling,
 * which `Library.test.tsx` covers, only runs once the page has mounted the
 * Library, and on a cold load it never did. So these cases drive `Page`, the
 * way `pageShortcuts.test.tsx` and `drillPosition.test.tsx` do.
 *
 * A cold load is simulated by setting the fragment with `replaceState` before
 * render: the same URL state, without the `hashchange` that jsdom's
 * `location.hash` setter queues for later. A change from outside the page (a
 * link, Back, an edited address) is simulated the way the browser does it: a
 * new fragment, then `hashchange`.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { renderToString } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'

import Page from '@/app/page'
import { content } from '@/lib/data'

vi.mock('@/lib/data', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/data')>()
  const f = await import('./fixtures')
  return { ...actual, questionsFor: () => f.QUESTIONS, guideFor: () => undefined }
})

afterEach(() => {
  vi.restoreAllMocks()
})

/** The accessible name of the destination the nav marks as current. */
function current(): string {
  const nav = screen.getByRole('navigation', { name: 'Sections' })
  return nav.querySelector('[aria-current="page"]')?.getAttribute('aria-label') ?? '(none)'
}

/** Click a destination in the nav. */
function pick(name: string | RegExp): void {
  const nav = screen.getByRole('navigation', { name: 'Sections' })
  fireEvent.click(within(nav).getByRole('button', { name }))
}

/** Put `url` in the address bar, as a cold load of it would. */
function openAt(url: string): void {
  window.history.replaceState(null, '', url)
}

/** The address changes from outside the page, and the browser says so. */
function followTo(url: string): void {
  act(() => {
    window.history.replaceState(null, '', url)
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  })
}

/** The address with no fragment: what a bare `/law-ai/` load shows. */
function bare(): string {
  return window.location.pathname + window.location.search
}

describe('a cold load opens the destination its fragment names', () => {
  const concept = content.concepts[0]?.id ?? 'missing'

  it.each([
    ['#article-lsat-exam-architecture', 'Library & concepts'],
    [`#catalog-${concept}`, 'Library & concepts'],
    ['#lr', 'Logical Reasoning'],
    ['#rc', 'Reading Comprehension'],
    ['#lg', 'Logic Games'],
    ['#writing', 'Argumentative Writing'],
    ['#stats', 'Stats'],
    ['#library', 'Library & concepts'],
    ['#LR', 'Logical Reasoning'],
    ['#Stats', 'Stats'],
  ])('%s opens %s', (hash, name) => {
    openAt(hash)
    render(<Page />)
    expect(current()).toContain(name)
  })

  it('opens Overview on #overview and on no fragment at all', () => {
    openAt('#overview')
    const first = render(<Page />)
    expect(current()).toBe('Overview')
    first.unmount()

    openAt(bare())
    render(<Page />)
    expect(current()).toBe('Overview')
  })

  it('falls back to Overview on a fragment that names no destination', () => {
    openAt('#nope')
    expect(() => render(<Page />)).not.toThrow()
    expect(current()).toBe('Overview')
  })

  it('still prerenders Overview, whatever the fragment says', () => {
    // The fragment is read in an effect. The export is rendered where there is
    // no URL, so a first render that followed it would not match the HTML the
    // reader's browser hydrates (the warning at app/page.tsx's header pin).
    openAt('#stats')
    const html = renderToString(<Page />)
    const doc = new DOMParser().parseFromString(html, 'text/html')
    const active = doc.querySelector('nav [aria-current="page"]')
    expect(active?.getAttribute('aria-label')).toBe('Overview')
  })
})

describe('picking a destination', () => {
  it('pushes one history entry, with the destination as its fragment', () => {
    const push = vi.spyOn(window.history, 'pushState')
    render(<Page />)

    pick(/Logical Reasoning/)
    expect(push).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenLastCalledWith(null, '', '#lr')
    expect(window.location.hash).toBe('#lr')

    pick('Stats')
    expect(push).toHaveBeenCalledTimes(2)
    expect(push).toHaveBeenLastCalledWith(null, '', '#stats')
    expect(current()).toBe('Stats')
  })

  it('pushes nothing when the destination is already current', () => {
    const push = vi.spyOn(window.history, 'pushState')
    render(<Page />)
    pick('Overview')
    expect(push).not.toHaveBeenCalled()

    pick(/Logical Reasoning/)
    pick(/Logical Reasoning/)
    expect(push).toHaveBeenCalledTimes(1)
  })

  it('pushes before the Library rewrites its own entry with replaceState', () => {
    // The Library writes `#article-<id>` with replaceState as it mounts. A push
    // made after that (from an effect) would leave the Library overwriting the
    // previous destination's entry, and Back would skip it.
    const push = vi.spyOn(window.history, 'pushState')
    const replace = vi.spyOn(window.history, 'replaceState')
    render(<Page />)
    pick(/Logical Reasoning/)
    pick(/Library/)

    expect(push).toHaveBeenCalledTimes(2)
    expect(push).toHaveBeenLastCalledWith(null, '', '#library')
    const rewrite = replace.mock.calls.findIndex(([, , url]) =>
      String(url).startsWith('#article-'),
    )
    expect(rewrite).toBeGreaterThanOrEqual(0)
    expect(push.mock.invocationCallOrder[1]).toBeLessThan(
      replace.mock.invocationCallOrder[rewrite],
    )
    expect(window.location.hash).toMatch(/^#article-/)
  })

  it('pushes for the [ and ] shortcuts and for an Overview card too', () => {
    const push = vi.spyOn(window.history, 'pushState')
    render(<Page />)
    fireEvent.keyDown(window, { key: ']' })
    expect(push).toHaveBeenLastCalledWith(null, '', '#lr')
    fireEvent.keyDown(window, { key: '[' })
    expect(push).toHaveBeenLastCalledWith(null, '', '#overview')

    fireEvent.click(screen.getByRole('button', { name: /Start RC drill/ }))
    expect(push).toHaveBeenLastCalledWith(null, '', '#rc')
    expect(current()).toContain('Reading Comprehension')
    expect(push).toHaveBeenCalledTimes(3)
  })

  it('lets Back walk destinations: Overview, LR, Library, Back lands on LR', async () => {
    render(<Page />)
    pick(/Logical Reasoning/)
    pick(/Library/)
    expect(current()).toContain('Library & concepts')

    act(() => {
      window.history.back()
    })
    await waitFor(() => expect(current()).toContain('Logical Reasoning'))
    expect(window.location.hash).toBe('#lr')

    act(() => {
      window.history.back()
    })
    await waitFor(() => expect(current()).toBe('Overview'))
  })
})

describe('a fragment change from outside the page', () => {
  it('switches to Stats on hashchange, without pushing an entry of its own', () => {
    const push = vi.spyOn(window.history, 'pushState')
    render(<Page />)
    followTo('#stats')
    expect(current()).toBe('Stats')
    expect(push).not.toHaveBeenCalled()
  })

  it('opens the Library on an #article- link followed from another view', () => {
    render(<Page />)
    pick('Stats')
    followTo('#article-lsat-exam-architecture')
    expect(current()).toContain('Library & concepts')
  })

  it('returns to Overview when the address loses its fragment', () => {
    render(<Page />)
    pick(/Logical Reasoning/)
    followTo(bare())
    expect(current()).toBe('Overview')
  })

  it('leaves the view alone on a fragment that names no destination', () => {
    // The skip link's target, and the in-article anchors the Library renders,
    // are fragments too. Following one must not throw the reader out of the
    // drill or the article they are in.
    render(<Page />)
    pick(/Logical Reasoning/)
    followTo('#view')
    expect(current()).toContain('Logical Reasoning')
    followTo(`#concept-${content.concepts[0]?.id ?? 'missing'}`)
    expect(current()).toContain('Logical Reasoning')
  })
})
