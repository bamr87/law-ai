'use client'

import {
  nextRovingIndex,
  type RovingOrientation,
} from '@/lib/shell/rovingFocus'
import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Makes a composite widget (tab bar, radiogroup) a single tab stop with
 * arrow-key movement inside it — the WAI-ARIA Authoring Practices pattern the
 * static LSAT site already implements and the platform did not.
 *
 * Selection follows focus, matching `lsat-static/components/QuestionCard.tsx`:
 * for both tabs and radios the APG allows it, and it is what the LSAT drill
 * already trained its users on. Diverging between the two products for the
 * same widget is worse than either choice.
 *
 * Usage:
 *
 *     const roving = useRovingTabIndex({
 *       count: TABS.length,
 *       activeIndex: TABS.findIndex((t) => t.id === tab),
 *       onActivate: (i) => onChange(TABS[i].id),
 *     })
 *     ...
 *     <button {...roving.itemProps(i)} role="tab" aria-selected={active} />
 */
export function useRovingTabIndex({
  count,
  activeIndex,
  orientation = 'horizontal',
  onActivate,
}: {
  count: number
  /** Index of the selected item; -1 when nothing is selected yet. */
  activeIndex: number
  orientation?: RovingOrientation
  onActivate?: (index: number) => void
}) {
  const items = useRef<(HTMLElement | null)[]>([])
  // Nothing selected yet → the first item is the tab stop, so the widget is
  // always reachable. (An all -1 group is a keyboard dead end.)
  const [focusIndex, setFocusIndex] = useState(activeIndex < 0 ? 0 : activeIndex)

  useEffect(() => {
    setFocusIndex(activeIndex < 0 ? 0 : activeIndex)
  }, [activeIndex])

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const next = nextRovingIndex(e, focusIndex, count, { orientation })
      if (next === null) return
      e.preventDefault()
      setFocusIndex(next)
      items.current[next]?.focus()
      onActivate?.(next)
    },
    [count, focusIndex, onActivate, orientation],
  )

  const itemProps = useCallback(
    (index: number) => ({
      ref: (el: HTMLElement | null) => {
        items.current[index] = el
      },
      tabIndex: index === focusIndex ? 0 : -1,
      onKeyDown,
    }),
    [focusIndex, onKeyDown],
  )

  return { itemProps, focusIndex }
}
