import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AppShell from '@/components/shell/AppShell'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { listSettingValues, upsertSettingValue } from '@/lib/scope/store'
import {
  inspectorDefaultOpen,
  railVisible,
  sidebarDefaultOpen,
  sidebarSide,
} from '@/lib/settings/catalog'
import { resetLayout } from '@/lib/shell/layout'

const nav = {
  path: '/graph',
  params: new URLSearchParams('inspector=1&sidebar=1'),
  replace: vi.fn(),
}

vi.mock('next/navigation', () => ({
  usePathname: () => nav.path,
  useSearchParams: () => nav.params,
  useRouter: () => ({ replace: nav.replace }),
}))

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

describe('AppShell', () => {
  // The settings store caches its snapshot; delete layout rows through it so
  // one test's preference cannot leak into the next.
  afterEach(() => resetLayout())

  it('keeps inspector open from searchParams and writes toggles to the URL', () => {
    nav.replace.mockClear()
    render(
      <AppShell
        sidebar={<div>SIDEBAR</div>}
        inspector={<div>INSPECTOR</div>}
      >
        <p>MAIN</p>
      </AppShell>,
    )
    expect(screen.getByText('INSPECTOR')).toBeInTheDocument()
    expect(screen.getByText('SIDEBAR')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Skip to main content' })).toHaveAttribute(
      'href',
      '#main',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Collapse inspector' }))
    expect(nav.replace).toHaveBeenCalled()
    const url = String(nav.replace.mock.calls[0][0])
    expect(url).toContain('inspector=0')
  })

  it('gives every masthead control the 44px tap target', () => {
    // WCAG 2.5.8 sets a 24px floor; the masthead is the chrome a thumb hits
    // first at 390px, so it gets the 44px HIG/AAA guideline instead
    // (BL-20260831-11). `.tap-target` supplies the height; `scripts/ux_audit.py`
    // R14 keeps the class on these controls.
    render(
      <AppShell sidebar={<div>SIDEBAR</div>} inspector={<div>INSPECTOR</div>}>
        <p>MAIN</p>
      </AppShell>,
    )
    const masthead = screen.getByTestId('masthead')
    for (const name of [
      'Law AI home',
      'Open command palette',
      'Collapse sidebar',
      'Collapse inspector',
    ]) {
      expect(within(masthead).getByRole(/home/.test(name) ? 'link' : 'button', {
        name,
      })).toHaveClass('tap-target')
    }
  })

  it('closes the inspector by default on a non-UPL route', () => {
    window.localStorage.clear()
    nav.params = new URLSearchParams()
    render(
      <AppShell sidebar={<div>SIDEBAR</div>} inspector={<div>INSPECTOR</div>}>
        <p>MAIN</p>
      </AppShell>,
    )
    expect(screen.queryByText('INSPECTOR')).not.toBeInTheDocument()
  })

  it('opens the inspector when ui.inspector.default_open is set and no param overrides it', async () => {
    window.localStorage.clear()
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: inspectorDefaultOpen.key,
      value: true,
      locked: false,
    })
    nav.params = new URLSearchParams()
    render(
      <AppShell sidebar={<div>SIDEBAR</div>} inspector={<div>INSPECTOR</div>}>
        <p>MAIN</p>
      </AppShell>,
    )
    await waitFor(() =>
      expect(screen.getByText('INSPECTOR')).toBeInTheDocument(),
    )
    window.localStorage.clear()
  })

  it('hides the navigation rail by preference and keeps the compact tab bar', async () => {
    window.localStorage.clear()
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: railVisible.key,
      value: false,
      locked: false,
    })
    nav.path = '/graph'
    nav.params = new URLSearchParams('sidebar=1&inspector=1')
    render(
      <AppShell sidebar={<div>SIDEBAR</div>} inspector={<div>INSPECTOR</div>}>
        <p>MAIN</p>
      </AppShell>,
    )
    await waitFor(() =>
      expect(screen.queryByTestId('nav-rail')).not.toBeInTheDocument(),
    )
    // A phone still needs its primary navigation.
    expect(screen.getByTestId('mobile-tabbar')).toBeInTheDocument()
    // …and a mouse user who does not know ⌘K needs a way to change module
    // that does not depend on the (also hideable) breadcrumb trail
    // (BL-20260905-08).
    expect(screen.getByRole('button', { name: 'Modules' })).toBeInTheDocument()
    window.localStorage.clear()
  })

  it('offers no Modules menu while the rail is showing', () => {
    window.localStorage.clear()
    nav.path = '/graph'
    nav.params = new URLSearchParams()
    render(
      <AppShell sidebar={<div>SIDEBAR</div>} inspector={<div>INSPECTOR</div>}>
        <p>MAIN</p>
      </AppShell>,
    )
    expect(screen.getByTestId('nav-rail')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Modules' }),
    ).not.toBeInTheDocument()
  })

  it('docks the sidebar on the right when asked, outermost', async () => {
    window.localStorage.clear()
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: sidebarSide.key,
      value: 'right',
      locked: false,
    })
    nav.path = '/graph'
    nav.params = new URLSearchParams('sidebar=1&inspector=1')
    render(
      <AppShell sidebar={<div>SIDEBAR</div>} inspector={<div>INSPECTOR</div>}>
        <p>MAIN</p>
      </AppShell>,
    )
    await waitFor(() =>
      expect(document.getElementById('shell-sidebar')).toHaveAttribute(
        'data-side',
        'right',
      ),
    )
    const main = screen.getByRole('main')
    const sidebar = document.getElementById('shell-sidebar') as HTMLElement
    const inspector = document.getElementById('shell-inspector') as HTMLElement
    // Reading order on the right edge: main, then the inspector (inner), then
    // the sidebar (outer).
    expect(
      main.compareDocumentPosition(inspector) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(
      inspector.compareDocumentPosition(sidebar) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(sidebar.className).toContain('border-l')
    expect(inspector).toHaveAttribute('data-side', 'right')
    window.localStorage.clear()
  })

  it('records a panel toggle as the preference for the next page', () => {
    window.localStorage.clear()
    nav.path = '/graph'
    nav.params = new URLSearchParams('sidebar=1&inspector=1')
    render(
      <AppShell sidebar={<div>SIDEBAR</div>} inspector={<div>INSPECTOR</div>}>
        <p>MAIN</p>
      </AppShell>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }))
    const row = listSettingValues().find((r) => r.key === sidebarDefaultOpen.key)
    expect(row?.value).toBe(false)
    // The URL still carries this page's layout.
    expect(String(nav.replace.mock.calls.at(-1)?.[0])).toContain('sidebar=0')
    window.localStorage.clear()
  })

  it('lets a stored inspector choice beat the UPL auto-open, and the URL beat both', async () => {
    window.localStorage.clear()
    nav.path = '/analysis' // a UPL route: opens the inspector when nothing is stored
    nav.params = new URLSearchParams()
    const first = render(
      <AppShell sidebar={<div>SIDEBAR</div>} inspector={<div>INSPECTOR</div>}>
        <p>MAIN</p>
      </AppShell>,
    )
    await waitFor(() => expect(screen.getByText('INSPECTOR')).toBeInTheDocument())
    first.unmount()

    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: inspectorDefaultOpen.key,
      value: false,
      locked: false,
    })
    const second = render(
      <AppShell sidebar={<div>SIDEBAR</div>} inspector={<div>INSPECTOR</div>}>
        <p>MAIN</p>
      </AppShell>,
    )
    await waitFor(() =>
      expect(screen.queryByText('INSPECTOR')).not.toBeInTheDocument(),
    )
    // The disclaimer itself never depends on the panel.
    expect(screen.getByRole('contentinfo')).toHaveTextContent(/not legal advice/i)
    second.unmount()

    nav.params = new URLSearchParams('inspector=1')
    render(
      <AppShell sidebar={<div>SIDEBAR</div>} inspector={<div>INSPECTOR</div>}>
        <p>MAIN</p>
      </AppShell>,
    )
    expect(screen.getByText('INSPECTOR')).toBeInTheDocument()
    window.localStorage.clear()
    nav.path = '/graph'
  })
})
