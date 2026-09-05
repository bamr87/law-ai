'use client'

import {
  backToTopVisible,
  breadcrumbsVisible,
  inspectorSide,
  libraryContents,
  libraryOutline,
  lsatTimerVisible,
  PAGE_HEADER_MODES,
  pageHeaderMode,
  PANEL_SIDES,
  railVisible,
  scopeSwitcherVisible,
  sidebarSide,
  type PageHeaderMode,
  type PanelSide,
} from '@/lib/settings/catalog'
import { nextRovingIndex } from '@/lib/shell/rovingFocus'
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { useSetting } from './useSetting'

type ItemRole = 'menuitemcheckbox' | 'menuitemradio' | 'menuitem'

interface Item {
  id: string
  label: string
  role: ItemRole
  checked?: boolean
  /** A key hint, when the shell also binds the row to a key. */
  hint?: string
  run: () => void
  /** Actions close the menu; toggles keep it open so several can be flipped. */
  closes?: boolean
}

interface Section {
  id: string
  label?: string
  items: Item[]
}

const SIDE_LABEL: Record<PanelSide, string> = { left: 'Left', right: 'Right' }
const HEADER_LABEL: Record<PageHeaderMode, string> = {
  auto: 'Condense on scroll',
  compact: 'Always compact',
}

/**
 * The masthead's Layout menu: one place to show, hide, and move the shell's
 * parts (spec 051).
 *
 * A menu rather than drag handles, for the reason the timer's dock picker is
 * one (spec 043 NG1): a `role="menu"` of `menuitemcheckbox` and
 * `menuitemradio` rows is keyboard-operable by construction and announces
 * every state. Toggles keep the menu open so a user can flip several in one
 * visit; the one action, Reset, closes it.
 *
 * The sidebar and inspector rows show the *effective* state — URL first,
 * preference second — and toggle through the shell's own handler, so the row,
 * the masthead button, and the `[` / `]` keys can never disagree.
 */
export default function LayoutMenu({
  pathname,
  sidebarOpen,
  inspectorOpen,
  onToggleSidebar,
  onToggleInspector,
  onReset,
}: {
  pathname: string
  sidebarOpen: boolean
  inspectorOpen: boolean
  onToggleSidebar: () => void
  onToggleInspector: () => void
  onReset: () => void
}) {
  const [rail, setRail] = useSetting(railVisible)
  const [crumbs, setCrumbs] = useSetting(breadcrumbsVisible)
  const [scope, setScope] = useSetting(scopeSwitcherVisible)
  const [top, setTop] = useSetting(backToTopVisible)
  const [timer, setTimer] = useSetting(lsatTimerVisible)
  const [contents, setContents] = useSetting(libraryContents)
  const [outline, setOutline] = useSetting(libraryOutline)
  const [sideOfSidebar, setSideOfSidebar] = useSetting(sidebarSide)
  const [sideOfInspector, setSideOfInspector] = useSetting(inspectorSide)
  const [header, setHeader] = useSetting(pageHeaderMode)

  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const buttonRef = useRef<HTMLButtonElement | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([])
  const menuId = useId()

  // Rows for a module's own parts appear only where those parts can be — a
  // "Section timer" row on the graph page would be a promise about nothing.
  const onLsat = pathname.startsWith('/lsat')
  const onLibrary = pathname.startsWith('/lsat/library')

  const check = (
    id: string,
    label: string,
    checked: boolean,
    run: () => void,
    hint?: string,
  ): Item => ({ id, label, role: 'menuitemcheckbox', checked, run, hint })
  const radio = (
    id: string,
    label: string,
    checked: boolean,
    run: () => void,
  ): Item => ({ id, label, role: 'menuitemradio', checked, run })

  const sections: Section[] = [
    {
      id: 'show',
      label: 'Show',
      items: [
        check('rail', 'Navigation rail', rail, () => setRail(!rail)),
        check('sidebar', 'Contextual sidebar', sidebarOpen, onToggleSidebar, '['),
        check('inspector', 'Inspector', inspectorOpen, onToggleInspector, ']'),
        check('breadcrumbs', 'Breadcrumb trail', crumbs, () => setCrumbs(!crumbs)),
        check('scope', 'Scope switcher', scope, () => setScope(!scope)),
        check('back-to-top', 'Back-to-top button', top, () => setTop(!top)),
        ...(onLsat
          ? [
              check('timer', 'Section timer when idle', timer, () =>
                setTimer(!timer),
              ),
            ]
          : []),
        ...(onLibrary
          ? [
              check('contents', 'Library contents rail', contents, () =>
                setContents(!contents),
              ),
              check('outline', 'Library outline', outline, () =>
                setOutline(!outline),
              ),
            ]
          : []),
      ],
    },
    {
      id: 'sidebar-side',
      label: 'Sidebar edge',
      items: PANEL_SIDES.map((s) =>
        radio(`sidebar-${s}`, SIDE_LABEL[s], sideOfSidebar === s, () =>
          setSideOfSidebar(s),
        ),
      ),
    },
    {
      id: 'inspector-side',
      label: 'Inspector edge',
      items: PANEL_SIDES.map((s) =>
        radio(`inspector-${s}`, SIDE_LABEL[s], sideOfInspector === s, () =>
          setSideOfInspector(s),
        ),
      ),
    },
    {
      id: 'header',
      label: 'Page header',
      items: PAGE_HEADER_MODES.map((m) =>
        radio(`header-${m}`, HEADER_LABEL[m], header === m, () => setHeader(m)),
      ),
    },
    {
      id: 'reset',
      items: [
        {
          id: 'reset',
          label: 'Reset layout',
          role: 'menuitem',
          run: onReset,
          closes: true,
        },
      ],
    },
  ]
  const flat = sections.flatMap((s) => s.items)

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false)
    if (restoreFocus) buttonRef.current?.focus()
  }, [])

  const openMenu = () => {
    setActive(0)
    setOpen(true)
  }

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

  const onMenuKeyDown = (e: React.KeyboardEvent) => {
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
    const next = nextRovingIndex(e, active, flat.length, {
      orientation: 'vertical',
    })
    if (next === null) return
    e.preventDefault()
    setActive(next)
  }

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        title="Show, hide, or move parts of the screen"
        onClick={() => (open ? close(false) : openMenu())}
        onKeyDown={(e) => {
          if (!open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
            e.preventDefault()
            openMenu()
          }
        }}
        className={
          'rounded-md border px-2 py-1 text-xs transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 ' +
          (open
            ? 'border-blue-500/40 bg-blue-600/10 text-blue-200'
            : 'border-slate-700 text-slate-400 hover:border-blue-500/40 hover:text-white')
        }
      >
        Layout
      </button>

      {open && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label="Layout"
          data-testid="layout-menu"
          onKeyDown={onMenuKeyDown}
          style={{ zIndex: 'var(--z-popover)' }}
          className="shell-panel-scroll absolute right-0 top-full mt-1 max-h-[calc(100dvh-var(--shell-masthead-h)-1rem)] w-64 rounded-md border border-slate-700 bg-slate-900 py-1 shadow-xl"
        >
          {sections.map((section, si) => (
            <div
              key={section.id}
              role="group"
              aria-labelledby={
                section.label ? `${menuId}-${section.id}` : undefined
              }
              className={si > 0 ? 'mt-1 border-t border-slate-800 pt-1' : ''}
            >
              {section.label && (
                <p
                  id={`${menuId}-${section.id}`}
                  className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500"
                >
                  {section.label}
                </p>
              )}
              {section.items.map((item) => {
                const index = flat.indexOf(item)
                const mark =
                  item.role === 'menuitem'
                    ? ''
                    : item.checked
                      ? item.role === 'menuitemradio'
                        ? '●'
                        : '✓'
                      : ''
                return (
                  <button
                    key={item.id}
                    ref={(el) => {
                      itemRefs.current[index] = el
                    }}
                    type="button"
                    role={item.role}
                    aria-checked={item.role === 'menuitem' ? undefined : item.checked}
                    tabIndex={index === active ? 0 : -1}
                    onClick={() => {
                      item.run()
                      if (item.closes) close(true)
                      else setActive(index)
                    }}
                    className={
                      'flex w-full items-center justify-between gap-3 px-3 py-1.5 text-left text-xs transition focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-blue-400 ' +
                      (item.checked
                        ? 'text-blue-200'
                        : 'text-slate-300 hover:bg-slate-800')
                    }
                  >
                    <span className="flex items-center gap-2">
                      <span aria-hidden="true" className="w-3 text-center">
                        {mark}
                      </span>
                      {item.label}
                    </span>
                    {item.hint && (
                      <kbd className="font-mono text-[10px] text-slate-500">
                        {item.hint}
                      </kbd>
                    )}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
