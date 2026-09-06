'use client'

import { layoutRowsForPath } from '@/lib/modules/catalog'
import {
  backToTopVisible,
  breadcrumbsVisible,
  inspectorSide,
  PAGE_HEADER_MODES,
  pageHeaderMode,
  PANEL_SIDES,
  railExpanded,
  railVisible,
  scopeSwitcherVisible,
  sidebarSide,
  type PageHeaderMode,
  type PanelSide,
} from '@/lib/settings/catalog'
import { useMenuPopover } from './useMenuPopover'
import { useSetting, useSettingList } from './useSetting'

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
 * parts (spec 050).
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
  const [railLabels, setRailLabels] = useSetting(railExpanded)
  const [crumbs, setCrumbs] = useSetting(breadcrumbsVisible)
  const [scope, setScope] = useSetting(scopeSwitcherVisible)
  const [top, setTop] = useSetting(backToTopVisible)
  const [sideOfSidebar, setSideOfSidebar] = useSetting(sidebarSide)
  const [sideOfInspector, setSideOfInspector] = useSetting(inspectorSide)
  const [header, setHeader] = useSetting(pageHeaderMode)

  // Rows for a module's own parts appear only where those parts can be. Which
  // rows those are is the module catalog's answer, not the menu's: the shell
  // does not know what "/lsat/library" is (spec 040; BL-20260905-07).
  const moduleRows = layoutRowsForPath(pathname)
  const moduleValues = useSettingList(moduleRows.map((r) => r.setting))

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
        // Only meaningful with the rail on, and only in effect at `xl`; the
        // row stays visible either way so the choice is discoverable where it
        // is made rather than only where it applies.
        check('rail-labels', 'Labelled rail (wide screens)', railLabels, () =>
          setRailLabels(!railLabels),
        ),
        check('sidebar', 'Contextual sidebar', sidebarOpen, onToggleSidebar, '['),
        check('inspector', 'Inspector', inspectorOpen, onToggleInspector, ']'),
        check('breadcrumbs', 'Breadcrumb trail', crumbs, () => setCrumbs(!crumbs)),
        check('scope', 'Scope switcher', scope, () => setScope(!scope)),
        check('back-to-top', 'Back-to-top button', top, () => setTop(!top)),
        ...moduleRows.map((row, i) => {
          const [on, set] = moduleValues[i]
          return check(row.id, row.label, on, () => set(!on))
        }),
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

  // One tab stop, Escape, outside click, ArrowDown-to-open — the shell's menu
  // contract, shared with the Modules menu rather than written twice.
  const {
    open,
    setActive,
    buttonRef,
    menuRef,
    menuId,
    close,
    openMenu,
    onMenuKeyDown,
    onTriggerKeyDown,
    itemProps,
  } = useMenuPopover(flat.length)

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
        onKeyDown={onTriggerKeyDown}
        className={
          'tap-target rounded-md border px-2.5 text-xs transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 ' +
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
                    {...itemProps(index)}
                    type="button"
                    role={item.role}
                    aria-checked={item.role === 'menuitem' ? undefined : item.checked}
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
