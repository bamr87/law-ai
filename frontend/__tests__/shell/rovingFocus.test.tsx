import { fireEvent, render, screen, within } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { nextRovingIndex } from '@/lib/shell/rovingFocus'
import { useRovingTabIndex } from '@/components/shell/useRovingTabIndex'

describe('nextRovingIndex', () => {
  it('moves and wraps horizontally', () => {
    expect(nextRovingIndex({ key: 'ArrowRight' }, 0, 3)).toBe(1)
    expect(nextRovingIndex({ key: 'ArrowRight' }, 2, 3)).toBe(0)
    expect(nextRovingIndex({ key: 'ArrowLeft' }, 0, 3)).toBe(2)
  })

  it('honours orientation', () => {
    expect(nextRovingIndex({ key: 'ArrowDown' }, 0, 3)).toBeNull()
    expect(
      nextRovingIndex({ key: 'ArrowDown' }, 0, 3, { orientation: 'vertical' }),
    ).toBe(1)
    expect(
      nextRovingIndex({ key: 'ArrowRight' }, 0, 3, { orientation: 'vertical' }),
    ).toBeNull()
  })

  it('supports Home and End', () => {
    expect(nextRovingIndex({ key: 'End' }, 0, 4)).toBe(3)
    expect(nextRovingIndex({ key: 'Home' }, 3, 4)).toBe(0)
  })

  it('never steals a modified chord', () => {
    expect(nextRovingIndex({ key: 'ArrowRight', metaKey: true }, 0, 3)).toBeNull()
    expect(nextRovingIndex({ key: 'ArrowRight', ctrlKey: true }, 0, 3)).toBeNull()
    expect(nextRovingIndex({ key: 'ArrowRight', altKey: true }, 0, 3)).toBeNull()
  })

  it('returns null for keys it does not own, and for an empty group', () => {
    expect(nextRovingIndex({ key: 'a' }, 0, 3)).toBeNull()
    expect(nextRovingIndex({ key: 'ArrowRight' }, 0, 0)).toBeNull()
  })

  it('can stop at the ends instead of wrapping', () => {
    expect(nextRovingIndex({ key: 'ArrowRight' }, 2, 3, { loop: false })).toBe(2)
    expect(nextRovingIndex({ key: 'ArrowLeft' }, 0, 3, { loop: false })).toBe(0)
  })
})

const ITEMS = ['Overview', 'Reasoning', 'Games']

function Tabs({ onActivate }: { onActivate?: (i: number) => void }) {
  const [active, setActive] = useState(0)
  const roving = useRovingTabIndex({
    count: ITEMS.length,
    activeIndex: active,
    onActivate: (i: number) => {
      setActive(i)
      onActivate?.(i)
    },
  })
  return (
    <div role="tablist" aria-label="Sections">
      {ITEMS.map((label, i) => (
        <button
          key={label}
          {...roving.itemProps(i)}
          role="tab"
          aria-selected={i === active}
          aria-controls={`panel-${i}`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

describe('useRovingTabIndex (the pattern the LSAT tab bar was missing)', () => {
  it('makes the whole group a single tab stop', () => {
    render(<Tabs />)
    const tabs = screen.getAllByRole('tab')
    // Exactly one item is tabbable; the rest are reached with arrows.
    expect(tabs.filter((t) => t.tabIndex === 0)).toHaveLength(1)
    expect(tabs[0].tabIndex).toBe(0)
    expect(tabs[1].tabIndex).toBe(-1)
    expect(tabs[2].tabIndex).toBe(-1)
  })

  it('moves focus and selection with arrow keys', () => {
    const onActivate = vi.fn()
    render(<Tabs onActivate={onActivate} />)
    const tabs = screen.getAllByRole('tab')
    tabs[0].focus()

    fireEvent.keyDown(tabs[0], { key: 'ArrowRight' })
    expect(onActivate).toHaveBeenCalledWith(1)
    expect(document.activeElement).toBe(screen.getAllByRole('tab')[1])
    expect(screen.getAllByRole('tab')[1]).toHaveAttribute('aria-selected', 'true')
  })

  it('wraps at the end so the group is never a dead end', () => {
    render(<Tabs />)
    let tabs = screen.getAllByRole('tab')
    tabs[0].focus()
    fireEvent.keyDown(tabs[0], { key: 'ArrowLeft' })
    expect(document.activeElement).toBe(screen.getAllByRole('tab')[2])
  })

  it('keeps the tab stop reachable when nothing is selected yet', () => {
    function Unselected() {
      const roving = useRovingTabIndex({ count: 3, activeIndex: -1 })
      return (
        <div role="radiogroup" aria-label="Answer choices">
          {ITEMS.map((l, i) => (
            <button key={l} {...roving.itemProps(i)} role="radio" aria-checked={false}>
              {l}
            </button>
          ))}
        </div>
      )
    }
    render(<Unselected />)
    const radios = within(
      screen.getByRole('radiogroup', { name: 'Answer choices' }),
    ).getAllByRole('radio')
    // An all -1 group would be unreachable by keyboard entirely.
    expect(radios.filter((r) => r.tabIndex === 0)).toHaveLength(1)
  })
})
