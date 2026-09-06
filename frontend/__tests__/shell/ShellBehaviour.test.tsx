import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AppShell from '@/components/shell/AppShell'
import CommandPalette from '@/components/shell/CommandPalette'
import PageLayout, { StickyToolbar } from '@/components/shell/PageLayout'
import ShortcutsHelp from '@/components/shell/ShortcutsHelp'
import { usePageShortcuts } from '@/components/shell/PageShortcuts'
import { ShellScrollProvider } from '@/components/shell/ShellScroll'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { upsertSettingValue } from '@/lib/scope/store'
import { breadcrumbsVisible, pageHeaderMode } from '@/lib/settings/catalog'
import { resetLayout } from '@/lib/shell/layout'

const nav = {
  path: '/agents',
  params: new URLSearchParams('sidebar=1&inspector=1'),
  replace: vi.fn(),
  push: vi.fn(),
}

vi.mock('next/navigation', () => ({
  usePathname: () => nav.path,
  useSearchParams: () => nav.params,
  useRouter: () => ({ replace: nav.replace, push: nav.push }),
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

/** A page's contributed group, module-level as `usePageShortcuts` requires. */
const DRILL = {
  title: 'Practice drill',
  rows: [{ keys: 'N', label: 'Next question' }],
}

function renderShell() {
  return render(
    <AppShell sidebar={<div>SIDEBAR</div>} inspector={<div>INSPECTOR</div>}>
      <p>MAIN</p>
    </AppShell>,
  )
}

beforeEach(() => {
  nav.path = '/agents'
  nav.params = new URLSearchParams('sidebar=1&inspector=1')
  nav.replace.mockClear()
  nav.push.mockClear()
  window.localStorage.clear()
  window.sessionStorage.clear()
  // The settings store caches its snapshot; clearing storage is not enough.
  resetLayout()
})

describe('shell scroll contract (spec 041 FR-1)', () => {
  it('locks the viewport and gives main the only content scroller', () => {
    const { container } = renderShell()
    const root = container.querySelector('div.h-dvh')
    expect(root).not.toBeNull()
    expect(root?.className).toContain('overflow-hidden')

    const main = screen.getByRole('main')
    expect(main.className).toContain('shell-scroll')
  })

  it('keeps the chrome outside the scrolling element', () => {
    renderShell()
    const main = screen.getByRole('main')
    // If any of these were inside main they would scroll away with content.
    expect(main.contains(screen.getByTestId('masthead'))).toBe(false)
    expect(main.contains(screen.getByTestId('nav-rail'))).toBe(false)
    expect(main.contains(screen.getByLabelText('Contextual navigation'))).toBe(
      false,
    )
    expect(main.contains(screen.getByLabelText('Inspector'))).toBe(false)
  })

  it('scrolls panels independently of the page', () => {
    renderShell()
    expect(screen.getByTestId('nav-rail').className).toContain(
      'shell-panel-scroll',
    )
  })

  it('renders the UPL disclaimer footer inside the scroll region', () => {
    renderShell()
    const footer = screen.getByRole('contentinfo')
    expect(screen.getByRole('main').contains(footer)).toBe(true)
    expect(footer).toHaveTextContent(/not legal advice/i)
  })

  it('restores the remembered offset for the route', async () => {
    window.sessionStorage.setItem(
      'lawai.shell.scroll',
      JSON.stringify({ '/agents': 320 }),
    )
    renderShell()
    await waitFor(() => expect(screen.getByRole('main').scrollTop).toBe(320))
  })
})

describe('shell keyboard contract (spec 041 FR-4)', () => {
  it('toggles the sidebar on "[" and the inspector on "]"', () => {
    renderShell()
    fireEvent.keyDown(window, { key: '[' })
    expect(String(nav.replace.mock.calls[0][0])).toContain('sidebar=0')

    nav.replace.mockClear()
    fireEvent.keyDown(window, { key: ']' })
    expect(String(nav.replace.mock.calls[0][0])).toContain('inspector=0')
  })

  it('does not steal a bare key typed into a field', () => {
    renderShell()
    const field = document.createElement('textarea')
    document.body.appendChild(field)
    field.focus()
    fireEvent.keyDown(field, { key: '[', bubbles: true })
    expect(nav.replace).not.toHaveBeenCalled()
    field.remove()
  })

  it('opens the palette on ⌘K and the help sheet on ?', async () => {
    renderShell()
    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    await waitFor(() =>
      expect(screen.getByTestId('command-palette')).toBeInTheDocument(),
    )
    fireEvent.keyDown(window, { key: 'Escape' })

    fireEvent.keyDown(window, { key: '?' })
    await waitFor(() =>
      expect(screen.getByTestId('shortcuts-help')).toBeInTheDocument(),
    )
  })

  it('shows the rows the page registered, and drops them when it leaves', async () => {
    // BL-20260901-10: a page's own keys are discoverable from the same sheet
    // as the shell's, for exactly as long as that page is on screen.
    function Drilling() {
      usePageShortcuts(DRILL)
      return <p>DRILL</p>
    }

    const { rerender } = render(
      <AppShell sidebar={<div>SIDEBAR</div>} inspector={<div>INSPECTOR</div>}>
        <Drilling />
      </AppShell>,
    )
    fireEvent.keyDown(window, { key: '?' })
    const sheet = await screen.findByTestId('shortcuts-help')
    expect(within(sheet).getByText('Practice drill')).toBeInTheDocument()
    expect(within(sheet).getByText('Next question')).toBeInTheDocument()
    // The shell's own keys are still first.
    expect(within(sheet).getByText('Anywhere')).toBeInTheDocument()

    rerender(
      <AppShell sidebar={<div>SIDEBAR</div>} inspector={<div>INSPECTOR</div>}>
        <p>SOMETHING ELSE</p>
      </AppShell>,
    )
    await waitFor(() =>
      expect(
        within(screen.getByTestId('shortcuts-help')).queryByText('Practice drill'),
      ).not.toBeInTheDocument(),
    )
    expect(
      within(screen.getByTestId('shortcuts-help')).getByText('Anywhere'),
    ).toBeInTheDocument()
  })
})

describe('masthead (spec 041 FR-5)', () => {
  it('names where the user is with a breadcrumb trail', () => {
    renderShell()
    const trail = screen.getByRole('navigation', { name: 'Breadcrumb' })
    expect(within(trail).getByText('Agent Ops')).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(
      within(trail).getByRole('link', { name: 'Dashboard' }),
    ).toHaveAttribute('href', '/')
  })

  it('wires the panel toggles to the panels they control', () => {
    renderShell()
    const toggle = screen.getByRole('button', { name: 'Collapse sidebar' })
    expect(toggle).toHaveAttribute('aria-controls', 'shell-sidebar')
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(document.getElementById('shell-sidebar')).not.toBeNull()
  })

  it('drops the breadcrumb trail by preference but never the way home', async () => {
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: breadcrumbsVisible.key,
      value: false,
      locked: false,
    })
    renderShell()
    await waitFor(() =>
      expect(
        screen.queryByRole('navigation', { name: 'Breadcrumb' }),
      ).not.toBeInTheDocument(),
    )
    expect(screen.getByRole('link', { name: 'Law AI home' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Layout' })).toBeInTheDocument()
  })

  it('toggles the rail from the palette (spec 051)', async () => {
    renderShell()
    expect(screen.getByTestId('nav-rail')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    const input = await screen.findByRole('combobox')
    fireEvent.change(input, { target: { value: 'navigation rail' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() =>
      expect(screen.queryByTestId('nav-rail')).not.toBeInTheDocument(),
    )
  })
})

describe('PageLayout (spec 041 FR-2)', () => {
  it('pins the page header and condenses it once the region scrolls', () => {
    const { rerender } = render(
      <ShellScrollProvider
        value={{
          scrolled: false,
          scrollTop: 0,
          scrollToTop: () => {},
        }}
      >
        <PageLayout eyebrow="Ops" title="Agent Operations" description="Body">
          <p>content</p>
        </PageLayout>
      </ShellScrollProvider>,
    )
    const header = screen.getByTestId('page-header')
    expect(header.className).toContain('shell-sticky-header')
    expect(header).toHaveAttribute('data-condensed', 'false')

    rerender(
      <ShellScrollProvider
        value={{
          scrolled: true,
          scrollTop: 400,
          scrollToTop: () => {},
        }}
      >
        <PageLayout eyebrow="Ops" title="Agent Operations" description="Body">
          <p>content</p>
        </PageLayout>
      </ShellScrollProvider>,
    )
    expect(screen.getByTestId('page-header')).toHaveAttribute(
      'data-condensed',
      'true',
    )
    // The title survives condensing; it is the whole point of the bar.
    expect(
      screen.getByRole('heading', { name: 'Agent Operations' }),
    ).toBeInTheDocument()
  })

  it('keeps the header condensed from the first paint on "compact" (spec 051)', async () => {
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: pageHeaderMode.key,
      value: 'compact',
      locked: false,
    })
    render(
      <ShellScrollProvider
        value={{ scrolled: false, scrollTop: 0, scrollToTop: () => {} }}
      >
        <PageLayout eyebrow="Ops" title="Agent Operations" description="Body">
          <p>content</p>
        </PageLayout>
      </ShellScrollProvider>,
    )
    await waitFor(() =>
      expect(screen.getByTestId('page-header')).toHaveAttribute(
        'data-condensed',
        'true',
      ),
    )
    expect(
      screen.getByRole('heading', { name: 'Agent Operations' }),
    ).toBeInTheDocument()
  })

  it('parks a toolbar on the sticky stack, not a magic offset', () => {
    render(
      <StickyToolbar label="Polling controls">
        <button type="button">Pause</button>
      </StickyToolbar>,
    )
    const bar = screen.getByTestId('sticky-toolbar')
    expect(bar.className).toContain('shell-sticky-sub')
    expect(bar).toHaveAttribute('aria-label', 'Polling controls')
  })
})

describe('CommandPalette (BL-20260830-09)', () => {
  it('filters, arrows, and navigates on Enter', async () => {
    render(<CommandPalette open onClose={() => {}} onAction={() => {}} />)
    const input = screen.getByRole('combobox')
    fireEvent.change(input, { target: { value: 'graph' } })
    const options = await screen.findAllByRole('option')
    expect(options[0]).toHaveTextContent('Knowledge Graph')

    fireEvent.keyDown(input, { key: 'Enter' })
    expect(nav.push).toHaveBeenCalledWith('/graph')
  })

  it('runs a layout action instead of navigating', async () => {
    const onAction = vi.fn()
    render(<CommandPalette open onClose={() => {}} onAction={onAction} />)
    fireEvent.change(screen.getByRole('combobox'), {
      target: { value: 'inspector' },
    })
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'Enter' })
    expect(onAction).toHaveBeenCalledWith('toggle-inspector')
    expect(nav.push).not.toHaveBeenCalled()
  })

  it('says so when nothing matches', () => {
    render(<CommandPalette open onClose={() => {}} onAction={() => {}} />)
    fireEvent.change(screen.getByRole('combobox'), {
      target: { value: 'zzzzz' },
    })
    expect(screen.queryAllByRole('option')).toHaveLength(0)
    expect(screen.getByText(/nothing matches/i)).toBeInTheDocument()
  })

  it('is a modal dialog that closes on Escape', () => {
    const onClose = vi.fn()
    render(<CommandPalette open onClose={onClose} onAction={() => {}} />)
    const dialog = screen.getByRole('dialog', { name: 'Command palette' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})

describe('ShortcutsHelp', () => {
  it('lists the bindings and closes on Escape', () => {
    const onClose = vi.fn()
    render(<ShortcutsHelp open onClose={onClose} />)
    expect(screen.getByText('Open the command palette')).toBeInTheDocument()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('renders nothing when closed', () => {
    render(<ShortcutsHelp open={false} onClose={() => {}} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
