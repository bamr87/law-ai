import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AppShell from '@/components/shell/AppShell'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { upsertSettingValue } from '@/lib/scope/store'
import { inspectorDefaultOpen } from '@/lib/settings/catalog'

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
})
