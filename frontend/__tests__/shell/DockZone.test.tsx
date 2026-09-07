import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import DockZone from '@/components/shell/DockZone'
import { DOCK_REGISTRY } from '@/components/shell/dockRegistry'
import { MODULE_CATALOG } from '@/lib/modules/catalog'
import { __resetTimerStore, startTimer } from '@/lib/lsat/timerStore'

/**
 * Dock widgets are contributed by modules as data (BL-20260831-14): the
 * catalog says which ids a module docks, the registry says what an id renders,
 * and `DockZone` knows neither LSAT nor `/lsat`.
 */
beforeEach(() => {
  __resetTimerStore()
  window.localStorage.clear()
})

afterEach(() => {
  __resetTimerStore()
  vi.restoreAllMocks()
})

describe('dock widget registration', () => {
  it('resolves every id the catalog declares', () => {
    const declared = MODULE_CATALOG.flatMap((m) => m.dockWidgets ?? [])
    expect(declared).toContain('lsat-timer')
    for (const id of declared) {
      expect(DOCK_REGISTRY[id]).toBeTypeOf('function')
    }
  })

  it('registers no widget the catalog does not ask for', () => {
    const declared = new Set(MODULE_CATALOG.flatMap((m) => m.dockWidgets ?? []))
    for (const id of Object.keys(DOCK_REGISTRY)) {
      expect(declared.has(id)).toBe(true)
    }
  })
})

describe('DockZone', () => {
  it('renders a module’s widget on that module’s own route', () => {
    render(<DockZone dock="sidebar" pathname="/lsat" openDocks={['sidebar']} />)
    expect(screen.getByTestId('lsat-timer')).toBeInTheDocument()
  })

  it('treats a nested route as the module’s own, like the rail does', () => {
    render(
      <DockZone dock="sidebar" pathname="/lsat/library" openDocks={['sidebar']} />,
    )
    expect(screen.getByTestId('lsat-timer')).toBeInTheDocument()
  })

  it('is off-route elsewhere — the widget hides until a section runs', () => {
    const { rerender } = render(
      <DockZone dock="sidebar" pathname="/graph" openDocks={['sidebar']} />,
    )
    expect(screen.queryByTestId('lsat-timer')).not.toBeInTheDocument()

    act(() => {
      startTimer()
    })
    rerender(<DockZone dock="sidebar" pathname="/graph" openDocks={['sidebar']} />)
    // Spec 043 FR-5: a running clock follows the user off the module's routes.
    expect(screen.getByTestId('lsat-timer')).toBeInTheDocument()
  })

  it('warns and renders nothing for a declared id with no component', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const [mod] = MODULE_CATALOG.filter((m) => m.dockWidgets?.length)
    const original = mod.dockWidgets
    mod.dockWidgets = ['not-registered']
    try {
      render(<DockZone dock="sidebar" pathname="/lsat" openDocks={['sidebar']} />)
      expect(screen.queryByTestId('lsat-timer')).not.toBeInTheDocument()
      expect(warn).toHaveBeenCalledWith(
        expect.stringContaining('not-registered'),
      )
    } finally {
      mod.dockWidgets = original
    }
  })
})
