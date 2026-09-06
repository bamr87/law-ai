import { describe, expect, it, vi } from 'vitest'
import { renderToString } from 'react-dom/server'
import AppShell from '@/components/shell/AppShell'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import type { SettingValue } from '@/lib/scope/types'
import {
  inspectorSide,
  railVisible,
  sidebarSide,
} from '@/lib/settings/catalog'

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

function serverHtml(rows?: SettingValue[]) {
  return renderToString(
    <AppShell
      sidebar={<div>SIDEBAR</div>}
      inspector={<div>INSPECTOR</div>}
      initialSettings={rows}
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

  it('ignores rows it cannot parse instead of failing the render', () => {
    const html = serverHtml([row(railVisible.key, 'not-a-boolean')])
    expect(html).toContain('data-testid="nav-rail"')
  })
})
