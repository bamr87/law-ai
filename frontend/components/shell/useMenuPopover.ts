'use client'

import { nextRovingIndex } from '@/lib/shell/rovingFocus'
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'

/**
 * The shell's menu-popover behaviour, in one place.
 *
 * Every masthead popover owes the user the same four things: one tab stop with
 * arrows moving inside it (WAI-ARIA roving tabindex), Escape closing it and
 * handing focus back to the trigger, an outside click closing it, and
 * ArrowDown on the trigger opening it with the first row focused. The Layout
 * menu had all of that written into it; the Modules menu (BL-20260905-08) owes
 * the identical contract, and two hand-rolled copies would drift.
 *
 * `count` is the number of focusable rows. It may change between renders — a
 * menu whose rows depend on the route — and the active index is clamped rather
 * than left pointing past the end.
 */
export function useMenuPopover(count: number) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const buttonRef = useRef<HTMLButtonElement | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const itemRefs = useRef<(HTMLElement | null)[]>([])
  const menuId = useId()

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false)
    if (restoreFocus) buttonRef.current?.focus()
  }, [])

  const openMenu = useCallback(() => {
    setActive(0)
    setOpen(true)
  }, [])

  // Focus follows `active` while the menu is open — the roving-tabindex
  // contract, so the group is one tab stop and arrows move inside it.
  useEffect(() => {
    if (open) itemRefs.current[active]?.focus()
  }, [open, active])

  // Outside click closes, like every other popover in the shell.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node
      if (
        !menuRef.current?.contains(target) &&
        !buttonRef.current?.contains(target)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const onMenuKeyDown = useCallback(
    (e: ReactKeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        close(true)
        return
      }
      if (e.key === 'Tab') {
        // Let focus move on naturally; a closed menu is what Tab means here.
        setOpen(false)
        return
      }
      const next = nextRovingIndex(e, active, count, { orientation: 'vertical' })
      if (next === null) return
      e.preventDefault()
      setActive(next)
    },
    [active, close, count],
  )

  const onTriggerKeyDown = useCallback(
    (e: ReactKeyboardEvent) => {
      if (!open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        e.preventDefault()
        openMenu()
      }
    },
    [open, openMenu],
  )

  /** Ref + tabindex for row `index`; the row itself supplies role and label. */
  const itemProps = useCallback(
    (index: number) => ({
      ref: (el: HTMLElement | null) => {
        itemRefs.current[index] = el
      },
      tabIndex: index === active ? 0 : -1,
    }),
    [active],
  )

  return {
    open,
    setOpen,
    active,
    setActive,
    buttonRef,
    menuRef,
    menuId,
    close,
    openMenu,
    onMenuKeyDown,
    onTriggerKeyDown,
    itemProps,
  }
}
