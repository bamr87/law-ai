import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LayoutMenu from '@/components/shell/LayoutMenu'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { listSettingValues } from '@/lib/scope/store'
import { railExpanded, railVisible, sidebarSide } from '@/lib/settings/catalog'
import { resetLayout } from '@/lib/shell/layout'

function stored(key: string) {
  return listSettingValues().find(
    (r) => r.scopeId === INSTANCE_SCOPE.id && r.key === key,
  )
}

function renderMenu(over: Partial<Parameters<typeof LayoutMenu>[0]> = {}) {
  const props = {
    pathname: '/lsat/library',
    sidebarOpen: true,
    inspectorOpen: false,
    onToggleSidebar: vi.fn(),
    onToggleInspector: vi.fn(),
    onReset: vi.fn(),
    ...over,
  }
  render(<LayoutMenu {...props} />)
  return props
}

function openMenu() {
  fireEvent.click(screen.getByRole('button', { name: 'Layout' }))
  return screen.getByRole('menu', { name: 'Layout' })
}

function items(menu: HTMLElement): HTMLElement[] {
  return Array.from(menu.querySelectorAll<HTMLElement>('[role^="menuitem"]'))
}

beforeEach(() => {
  window.localStorage.clear()
  resetLayout()
})

describe('LayoutMenu (spec 051)', () => {
  it('is a named menu of checkbox and radio rows that reflect the shell', () => {
    renderMenu()
    const menu = openMenu()
    expect(
      screen.getByRole('button', { name: 'Layout' }),
    ).toHaveAttribute('aria-expanded', 'true')
    expect(
      within(menu).getByRole('menuitemcheckbox', { name: /Contextual sidebar/ }),
    ).toHaveAttribute('aria-checked', 'true')
    expect(
      within(menu).getByRole('menuitemcheckbox', { name: /^Inspector/ }),
    ).toHaveAttribute('aria-checked', 'false')
    expect(
      within(menu).getByRole('menuitemcheckbox', { name: 'Navigation rail' }),
    ).toHaveAttribute('aria-checked', 'true')
    expect(
      within(menu).getByRole('group', { name: 'Sidebar edge' }),
    ).toBeInTheDocument()
    // Module rows only on the module's own routes.
    expect(
      within(menu).getByRole('menuitemcheckbox', { name: 'Library outline' }),
    ).toBeInTheDocument()
  })

  it('writes a toggle to the settings store and stays open for the next one', () => {
    renderMenu()
    const menu = openMenu()
    fireEvent.click(
      within(menu).getByRole('menuitemcheckbox', { name: 'Navigation rail' }),
    )
    expect(stored(railVisible.key)?.value).toBe(false)
    expect(screen.getByRole('menu', { name: 'Layout' })).toBeInTheDocument()
    expect(
      screen.getByRole('menuitemcheckbox', { name: 'Navigation rail' }),
    ).toHaveAttribute('aria-checked', 'false')
  })

  it('remembers the labelled-rail choice (BL-20260831-06)', () => {
    renderMenu()
    const menu = openMenu()
    const row = within(menu).getByRole('menuitemcheckbox', {
      name: 'Labelled rail (wide screens)',
    })
    expect(row).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(row)
    expect(stored(railExpanded.key)?.value).toBe(true)
    expect(
      screen.getByRole('menuitemcheckbox', { name: 'Labelled rail (wide screens)' }),
    ).toHaveAttribute('aria-checked', 'true')
  })

  it('makes the labelled-rail row inert while the rail is hidden (BL-20260905-30)', () => {
    renderMenu()
    let menu = openMenu()
    // Hide the rail from the row above it.
    fireEvent.click(
      within(menu).getByRole('menuitemcheckbox', { name: 'Navigation rail' }),
    )
    menu = screen.getByRole('menu', { name: 'Layout' })
    const row = within(menu).getByRole('menuitemcheckbox', {
      name: /Labelled rail/,
    })
    // It says why rather than disappearing, and it is not a live toggle.
    expect(row).toHaveAttribute('aria-disabled', 'true')
    expect(row).toHaveAttribute('title', expect.stringContaining('rail'))
    expect(row).toHaveTextContent('needs the rail')
    fireEvent.click(row)
    expect(stored(railExpanded.key)).toBeUndefined()
    expect(row).toHaveAttribute('aria-checked', 'false')

    // Still one tab stop with every row arrow-reachable: `aria-disabled`, not
    // `disabled`, precisely so the inert row keeps its place in the ring.
    expect(row).not.toBeDisabled()
    expect(items(menu)).toContain(row)

    // Bring the rail back and it is a live toggle again.
    fireEvent.click(
      within(menu).getByRole('menuitemcheckbox', { name: 'Navigation rail' }),
    )
    const live = screen.getByRole('menuitemcheckbox', { name: /Labelled rail/ })
    expect(live).not.toHaveAttribute('aria-disabled')
    fireEvent.click(live)
    expect(stored(railExpanded.key)?.value).toBe(true)
  })

  it('moves a panel with a radio row', () => {
    renderMenu()
    const group = within(openMenu()).getByRole('group', { name: 'Sidebar edge' })
    expect(within(group).getByRole('menuitemradio', { name: 'Left' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    fireEvent.click(within(group).getByRole('menuitemradio', { name: 'Right' }))
    expect(stored(sidebarSide.key)?.value).toBe('right')
    expect(within(group).getByRole('menuitemradio', { name: 'Right' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
  })

  it('routes the panel rows through the shell, not the store', () => {
    const props = renderMenu()
    const menu = openMenu()
    fireEvent.click(
      within(menu).getByRole('menuitemcheckbox', { name: /Contextual sidebar/ }),
    )
    expect(props.onToggleSidebar).toHaveBeenCalledTimes(1)
    fireEvent.click(within(menu).getByRole('menuitemcheckbox', { name: /^Inspector/ }))
    expect(props.onToggleInspector).toHaveBeenCalledTimes(1)
  })

  it('leaves the module rows out off their routes', () => {
    renderMenu({ pathname: '/graph' })
    const menu = openMenu()
    expect(
      within(menu).queryByRole('menuitemcheckbox', { name: /Section timer/ }),
    ).not.toBeInTheDocument()
    expect(
      within(menu).queryByRole('menuitemcheckbox', { name: 'Library outline' }),
    ).not.toBeInTheDocument()
  })

  it('is one tab stop: arrows move focus, Escape closes and hands it back', () => {
    renderMenu()
    const button = screen.getByRole('button', { name: 'Layout' })
    const menu = openMenu()
    const rows = items(menu)
    expect(rows.length).toBeGreaterThan(5)
    expect(document.activeElement).toBe(rows[0])
    expect(rows.filter((el) => el.getAttribute('tabindex') === '0')).toHaveLength(1)

    fireEvent.keyDown(menu, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(rows[1])
    fireEvent.keyDown(menu, { key: 'End' })
    expect(document.activeElement).toBe(rows[rows.length - 1])
    fireEvent.keyDown(menu, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(rows[0])

    fireEvent.keyDown(menu, { key: 'Escape' })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(document.activeElement).toBe(button)
  })

  it('resets through the shell and closes', () => {
    const props = renderMenu()
    fireEvent.click(within(openMenu()).getByRole('menuitem', { name: 'Reset layout' }))
    expect(props.onReset).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})
