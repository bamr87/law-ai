import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import NavRail from '@/components/shell/NavRail'
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
})
