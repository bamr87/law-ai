import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { listSettingValues } from '@/lib/scope/store'
import type { SettingDefinition } from '@/lib/scope/types'

/**
 * The Layout menu renders the rows a *module* declares (BL-20260905-07).
 *
 * The proof has to come from a module the shell has never heard of: asserting
 * on the LSAT rows would pass just as well against the old hard-coded
 * `pathname.startsWith('/lsat')`. So the catalog is mocked with a fabricated
 * module and a fabricated setting, and the menu is asked to render them.
 */
const { fakeSetting } = vi.hoisted(() => ({
  fakeSetting: {
    key: 'fake.widget.visible',
    label: 'Fake module widget',
    default: true,
    settableAt: ['instance'],
    lockable: false,
    parse: (raw: unknown) => (typeof raw === 'boolean' ? raw : undefined),
  } as SettingDefinition<boolean>,
}))

vi.mock('@/lib/modules/catalog', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/lib/modules/catalog')>()
  return {
    ...actual,
    layoutRowsForPath: (pathname: string) =>
      pathname.startsWith('/fake')
        ? [{ id: 'widget', label: 'Fake module widget', setting: fakeSetting }]
        : [],
  }
})

import LayoutMenu from '@/components/shell/LayoutMenu'

function openMenuFor(pathname: string) {
  render(
    <LayoutMenu
      pathname={pathname}
      sidebarOpen
      inspectorOpen={false}
      onToggleSidebar={vi.fn()}
      onToggleInspector={vi.fn()}
      onReset={vi.fn()}
    />,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Layout' }))
  return screen.getByRole('menu', { name: 'Layout' })
}

beforeEach(() => {
  window.localStorage.clear()
})

describe('LayoutMenu module rows (BL-20260905-07)', () => {
  it('renders whatever the active module declares, and writes its setting', () => {
    const menu = openMenuFor('/fake/anything')
    const row = within(menu).getByRole('menuitemcheckbox', {
      name: 'Fake module widget',
    })
    expect(row).toHaveAttribute('aria-checked', 'true')

    fireEvent.click(row)
    expect(
      listSettingValues().find(
        (r) => r.scopeId === INSTANCE_SCOPE.id && r.key === 'fake.widget.visible',
      )?.value,
    ).toBe(false)
    expect(
      screen.getByRole('menuitemcheckbox', { name: 'Fake module widget' }),
    ).toHaveAttribute('aria-checked', 'false')
  })

  it('shows no module rows where the module declares none', () => {
    const menu = openMenuFor('/graph')
    expect(
      within(menu).queryByRole('menuitemcheckbox', {
        name: 'Fake module widget',
      }),
    ).not.toBeInTheDocument()
    // The shell's own rows are unaffected — they are not module-contributed.
    expect(
      within(menu).getByRole('menuitemcheckbox', { name: 'Navigation rail' }),
    ).toBeInTheDocument()
  })
})
