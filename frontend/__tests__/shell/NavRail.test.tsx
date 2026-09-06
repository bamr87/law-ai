import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import NavRail from '@/components/shell/NavRail'
import { MODULE_CATALOG } from '@/lib/modules/catalog'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { upsertSettingValue } from '@/lib/scope/store'
import { railExpanded } from '@/lib/settings/catalog'
import { resetLayout } from '@/lib/shell/layout'

vi.mock('next/link', () => ({
  default: ({
    children,
    href,
    ...rest
  }: {
    children: React.ReactNode
    href: string
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}))

/**
 * `useMediaQuery` asks `window.matchMedia`, which jsdom answers `false` to for
 * everything. Widths are a real input to the rail's markup (BL-20260831-06),
 * so the test says how wide the viewport is.
 */
function setViewportWide(wide: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: wide,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}

function preferLabels() {
  upsertSettingValue({
    scopeId: INSTANCE_SCOPE.id,
    key: railExpanded.key,
    value: true,
    locked: false,
  })
}

const realMatchMedia = window.matchMedia

beforeEach(() => {
  window.localStorage.clear()
  resetLayout()
  setViewportWide(false)
})

afterEach(() => {
  window.matchMedia = realMatchMedia
})

describe('NavRail', () => {
  it('renders every catalog module without AppShell knowing them', () => {
    render(<NavRail pathname="/agents" />)
    for (const mod of MODULE_CATALOG) {
      expect(screen.getByRole('link', { name: mod.nav.label })).toHaveAttribute(
        'href',
        mod.nav.href,
      )
    }
    expect(screen.getByRole('link', { name: 'Agent Ops' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('is glyph-only by default: the label is for screen readers alone', () => {
    setViewportWide(true)
    render(<NavRail pathname="/agents" />)
    const link = screen.getByRole('link', { name: 'Agent Ops' })
    expect(link).toHaveAttribute('title', 'Agent Ops')
    expect(link.querySelector('.sr-only')?.textContent).toBe('Agent Ops')
    expect(screen.getByTestId('nav-rail')).not.toHaveAttribute('data-expanded')
  })

  it('shows visible labels when the preference is set and the viewport is wide', () => {
    preferLabels()
    setViewportWide(true)
    render(<NavRail pathname="/agents" />)
    const rail = screen.getByTestId('nav-rail')
    expect(rail).toHaveAttribute('data-expanded', 'true')
    expect(rail.className).toContain('w-[var(--shell-rail-w-expanded)]')
    for (const mod of MODULE_CATALOG) {
      const link = screen.getByRole('link', { name: mod.nav.label })
      // The name is now on screen, so it is not repeated as a title or an
      // sr-only span — that would announce it twice.
      expect(link).not.toHaveAttribute('title')
      expect(link.querySelector('.sr-only')).toBeNull()
      expect(link.textContent).toContain(mod.nav.label)
    }
  })

  it('stays glyph-only below xl even when the preference is set', () => {
    preferLabels()
    setViewportWide(false)
    render(<NavRail pathname="/agents" />)
    const rail = screen.getByTestId('nav-rail')
    expect(rail).not.toHaveAttribute('data-expanded')
    expect(rail.className).toContain('w-[var(--shell-rail-w)]')
    expect(
      screen.getByRole('link', { name: 'Agent Ops' }),
    ).toHaveAttribute('title', 'Agent Ops')
  })
})
