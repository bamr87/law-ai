import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ModulesMenu from '@/components/shell/ModulesMenu'
import { MODULE_CATALOG } from '@/lib/modules/catalog'

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

function open(pathname = '/graph') {
  render(<ModulesMenu pathname={pathname} />)
  fireEvent.click(screen.getByRole('button', { name: 'Modules' }))
  return screen.getByRole('menu', { name: 'Modules' })
}

function rows(menu: HTMLElement): HTMLElement[] {
  return within(menu).getAllByRole('menuitem')
}

beforeEach(() => {
  window.localStorage.clear()
})

describe('ModulesMenu (BL-20260905-08)', () => {
  it('lists every catalog module as a link, and marks the current one', () => {
    const menu = open('/graph')
    expect(rows(menu)).toHaveLength(MODULE_CATALOG.length)
    for (const mod of MODULE_CATALOG) {
      expect(
        within(menu).getByRole('menuitem', { name: mod.nav.label }),
      ).toHaveAttribute('href', mod.nav.href)
    }
    expect(
      within(menu).getByRole('menuitem', { name: 'Knowledge Graph' }),
    ).toHaveAttribute('aria-current', 'page')
    expect(
      within(menu).getByRole('menuitem', { name: 'LSAT Lab' }),
    ).not.toHaveAttribute('aria-current')
  })

  it('marks the owning module on a nested route', () => {
    const menu = open('/lsat/library')
    expect(
      within(menu).getByRole('menuitem', { name: 'LSAT Lab' }),
    ).toHaveAttribute('aria-current', 'page')
  })

  it('is one tab stop: arrows move inside it, Escape hands focus back', () => {
    render(<ModulesMenu pathname="/graph" />)
    const button = screen.getByRole('button', { name: 'Modules' })
    fireEvent.click(button)
    const menu = screen.getByRole('menu', { name: 'Modules' })
    const items = rows(menu)
    expect(document.activeElement).toBe(items[0])
    expect(items.filter((el) => el.getAttribute('tabindex') === '0')).toHaveLength(
      1,
    )

    fireEvent.keyDown(menu, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[1])
    fireEvent.keyDown(menu, { key: 'End' })
    expect(document.activeElement).toBe(items[items.length - 1])

    fireEvent.keyDown(menu, { key: 'Escape' })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(document.activeElement).toBe(button)
  })

  it('opens from the trigger with ArrowDown and closes on an outside click', () => {
    render(<ModulesMenu pathname="/" />)
    const button = screen.getByRole('button', { name: 'Modules' })
    fireEvent.keyDown(button, { key: 'ArrowDown' })
    expect(screen.getByRole('menu', { name: 'Modules' })).toBeInTheDocument()

    fireEvent.mouseDown(document.body)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('closes when a destination is chosen', () => {
    const menu = open('/graph')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'LSAT Lab' }))
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})
