'use client'

import { MODULE_CATALOG, moduleForPath } from '@/lib/modules/catalog'
import Link from 'next/link'
import { useMenuPopover } from './useMenuPopover'

/**
 * The masthead's Modules menu: every module, one click away, when the rail is
 * hidden (BL-20260905-08).
 *
 * With `ui.rail.visible` off — and the breadcrumb trail hideable too — a mouse
 * user who does not know ⌘K had no way left to change module. This is that
 * way. It is generated from `MODULE_CATALOG`, like the rail and the palette,
 * so a new module appears here for free and the shell still learns no route
 * names.
 *
 * A `role="menu"` of `menuitem` links, sharing the shell's menu-popover
 * contract with the Layout menu (`useMenuPopover`): one tab stop, arrows
 * inside it, Escape back to the trigger. Hidden below `md`, where
 * `MobileTabBar` already carries the same catalog in thumb reach.
 */
export default function ModulesMenu({ pathname }: { pathname: string }) {
  const activeId = moduleForPath(pathname).id
  const {
    open,
    buttonRef,
    menuRef,
    menuId,
    close,
    openMenu,
    onMenuKeyDown,
    onTriggerKeyDown,
    itemProps,
  } = useMenuPopover(MODULE_CATALOG.length)

  return (
    <div className="relative hidden shrink-0 md:block">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        title="Go to another module"
        onClick={() => (open ? close(false) : openMenu())}
        onKeyDown={onTriggerKeyDown}
        className={
          'tap-target flex items-center gap-1.5 rounded-md border px-2.5 text-xs transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 ' +
          (open
            ? 'border-blue-500/40 bg-blue-600/10 text-blue-200'
            : 'border-slate-700 text-slate-400 hover:border-blue-500/40 hover:text-white')
        }
      >
        <span aria-hidden="true">☰</span>
        Modules
      </button>

      {open && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label="Modules"
          data-testid="modules-menu"
          onKeyDown={onMenuKeyDown}
          style={{ zIndex: 'var(--z-popover)' }}
          className="shell-panel-scroll absolute left-0 top-full mt-1 max-h-[calc(100dvh-var(--shell-masthead-h)-1rem)] w-56 rounded-md border border-slate-700 bg-slate-900 py-1 shadow-xl"
        >
          {MODULE_CATALOG.map((mod, index) => {
            const current = mod.id === activeId
            return (
              <Link
                key={mod.id}
                {...itemProps(index)}
                href={mod.nav.href}
                role="menuitem"
                aria-current={current ? 'page' : undefined}
                onClick={() => close(false)}
                className={
                  'flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs transition focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-blue-400 ' +
                  (current
                    ? 'text-blue-200'
                    : 'text-slate-300 hover:bg-slate-800')
                }
              >
                <span aria-hidden="true" className="w-6 text-center font-semibold">
                  {mod.nav.glyph}
                </span>
                {mod.nav.label}
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
