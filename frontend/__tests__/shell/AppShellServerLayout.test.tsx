import { describe, expect, it, vi } from 'vitest'
import { renderToString } from 'react-dom/server'
import AppShell from '@/components/shell/AppShell'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import type { SettingValue } from '@/lib/scope/types'
import { inspectorSide, railVisible, sidebarSide } from '@/lib/settings/catalog'

vi.mock('next/navigation', () => ({
  usePathname: () => '/graph',
  useSearchParams: () => new URLSearchParams('sidebar=1&inspector=1'),
  useRouter: () => ({ replace: vi.fn() }),
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

function row(key: string, value: unknown): SettingValue {
  return { scopeId: INSTANCE_SCOPE.id, key, value, locked: false }
}

function serverHtml(rows?: SettingValue[], userScopeId?: string | null) {
  return renderToString(
    <AppShell
      sidebar={<div>SIDEBAR</div>}
      inspector={<div>INSPECTOR</div>}
      initialSettings={rows}
      initialUserScopeId={userScopeId}
    >
      <p>MAIN</p>
    </AppShell>,
  )
}

/**
 * The server render is the first paint (BL-20260905-09). `renderToString` is
 * the only honest way to assert it: a client render reads localStorage, and
 * the whole point of the cookie mirror is what happens *before* that.
 */
describe('AppShell server render (BL-20260905-09)', () => {
  it('paints the default layout when nothing is stored', () => {
    const html = serverHtml()
    expect(html).toContain('data-testid="nav-rail"')
  })

  it('paints a chosen layout on the first render, with no effect tick', () => {
    const html = serverHtml([
      row(railVisible.key, false),
      row(sidebarSide.key, 'right'),
      row(inspectorSide.key, 'right'),
    ])
    // Rail hidden…
    expect(html).not.toContain('data-testid="nav-rail"')
    // …and its replacement in the masthead is there from the start.
    expect(html).toContain('Modules')
    // Both panels on the right edge, sidebar outermost: the sidebar's markup
    // comes after the inspector's in document order.
    expect(html.indexOf('INSPECTOR')).toBeLessThan(html.indexOf('SIDEBAR'))
  })

  it('paints a signed-in visitor’s own layout, not the instance default', () => {
    // BL-20260905-10 moved layout rows to `user:<pk>`. A server resolver that
    // walks the instance scope alone skips every one of them, so the first
    // paint showed the instance default and reflowed after hydration — the
    // exact regression this render exists to prevent.
    const rows: SettingValue[] = [
      {
        scopeId: INSTANCE_SCOPE.id,
        key: railVisible.key,
        value: true,
        locked: false,
      },
      { scopeId: 'user:7', key: railVisible.key, value: false, locked: false },
    ]
    expect(serverHtml(rows, 'user:7')).not.toContain('data-testid="nav-rail"')
    // Without the scope id — signed out — the instance value still wins.
    expect(serverHtml(rows)).toContain('data-testid="nav-rail"')
  })

  it('ignores rows it cannot parse instead of failing the render', () => {
    const html = serverHtml([row(railVisible.key, 'not-a-boolean')])
    expect(html).toContain('data-testid="nav-rail"')
  })
})
