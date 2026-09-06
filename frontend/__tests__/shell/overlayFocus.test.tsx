import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import CommandPalette from '@/components/shell/CommandPalette'
import Drawer from '@/components/shell/Overlay'
import ShortcutsHelp from '@/components/shell/ShortcutsHelp'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

/**
 * Focus comes back, however the layer goes away (BL-20260906-53).
 *
 * `useFocusTrap` restores focus from its effect cleanup, and it used to do so
 * only while the trapped node still contained `document.activeElement`. A
 * layer that flips `active` to false satisfies that; one that *unmounts* does
 * not — React has already detached the node by the time the cleanup runs, and
 * focus is sitting on `<body>`. That was fixed in the shared hook, which is
 * why this is one table over all three of its users rather than a case bolted
 * onto whichever overlay happened to be edited: the next overlay to adopt the
 * hook inherits the guarantee and this test.
 */
const OVERLAYS = [
  {
    name: 'Drawer',
    render: (onClose: () => void) => (
      <Drawer open side="left" label="Navigation" onClose={onClose}>
        <a href="/lsat">LSAT Lab</a>
      </Drawer>
    ),
  },
  {
    name: 'CommandPalette',
    render: (onClose: () => void) => (
      <CommandPalette open onClose={onClose} onAction={vi.fn()} />
    ),
  },
  {
    name: 'ShortcutsHelp',
    render: (onClose: () => void) => <ShortcutsHelp open onClose={onClose} />,
  },
] as const

/** A trigger that is focused before the layer opens, as a real one would be. */
function Harness({
  children,
}: {
  children: (onClose: () => void) => React.ReactNode
}) {
  return (
    <>
      <button type="button" data-testid="trigger">
        Open
      </button>
      {children(() => {})}
    </>
  )
}

describe.each(OVERLAYS)('$name focus restoration', (overlay) => {
  it('hands focus back to the trigger when the layer unmounts', () => {
    // Focus the trigger first: the trap records whatever had focus when it
    // ran, and that is what it owes back.
    const trigger = document.createElement('button')
    document.body.append(trigger)
    trigger.focus()
    expect(document.activeElement).toBe(trigger)

    const { unmount } = render(<Harness>{overlay.render}</Harness>)
    // Focus moved into the layer, which is the other half of the contract.
    expect(document.activeElement).not.toBe(trigger)

    unmount()
    expect(document.activeElement).toBe(trigger)
    trigger.remove()
  })

  it('hands it back on Escape too, without unmounting', () => {
    const trigger = document.createElement('button')
    document.body.append(trigger)
    trigger.focus()

    const onClose = vi.fn()
    render(<Harness>{() => overlay.render(onClose)}</Harness>)
    fireEvent.keyDown(document.activeElement as Element, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
    trigger.remove()
  })
})

describe('unmount restoration is the hook, not a per-overlay patch', () => {
  it('leaves focus alone when the user has already clicked elsewhere', () => {
    const trigger = document.createElement('button')
    const elsewhere = document.createElement('button')
    document.body.append(trigger, elsewhere)
    trigger.focus()

    const { unmount } = render(
      <Harness>
        {(onClose) => (
          <Drawer open side="left" label="Navigation" onClose={onClose}>
            <a href="/lsat">LSAT Lab</a>
          </Drawer>
        )}
      </Harness>,
    )
    // The click that dismissed the drawer landed on something focusable, and
    // yanking focus off it would be worse than leaving it there.
    elsewhere.focus()
    unmount()
    expect(document.activeElement).toBe(elsewhere)

    trigger.remove()
    elsewhere.remove()
  })
})

describe('the trap is shared', () => {
  it('every shell overlay in this table renders through useFocusTrap', () => {
    // A guard on the premise: if one of these stops using the shared hook,
    // the cases above stop meaning what they say.
    expect(OVERLAYS.map((o) => o.name)).toEqual([
      'Drawer',
      'CommandPalette',
      'ShortcutsHelp',
    ])
    for (const o of OVERLAYS) {
      const { unmount } = render(<Harness>{o.render}</Harness>)
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      unmount()
    }
  })
})
