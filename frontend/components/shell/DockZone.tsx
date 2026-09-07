'use client'

import { MODULE_CATALOG, moduleForPath } from '@/lib/modules/catalog'
import type { Dock } from '@/lib/settings/catalog'
import { DOCK_REGISTRY, type DockedWidgetProps } from './dockRegistry'

export type { DockedWidgetProps }

/**
 * One dock zone — a slot in a shell panel where modules park widgets.
 *
 * Which widgets exist is the module catalog's answer (`dockWidgets`), the same
 * way nav and sidebar entries are (BL-20260831-14); this component only asks
 * every module what it contributes and hands each widget the zone. Each widget
 * decides for itself whether it belongs here and whether it should show on the
 * current route, so the shell stays ignorant of what LSAT is — including for
 * "am I on my own route", which is now `moduleForPath` against the module that
 * declared the widget rather than a hard-coded `/lsat` prefix.
 */
export default function DockZone({
  dock,
  pathname,
  openDocks,
}: {
  dock: Dock
  pathname: string
  openDocks: Dock[]
}) {
  const activeModuleId = moduleForPath(pathname).id

  return (
    <>
      {MODULE_CATALOG.flatMap((mod) =>
        (mod.dockWidgets ?? []).map((id) => {
          const Widget = DOCK_REGISTRY[id]
          if (!Widget) {
            // A declared id with no component is a wiring mistake, not a
            // reason to take the shell down: say so once and render nothing.
            if (process.env.NODE_ENV !== 'production') {
              console.warn(
                `DockZone: module "${mod.id}" declares unknown dock widget "${id}"`,
              )
            }
            return null
          }
          return (
            <Widget
              key={id}
              dock={dock}
              onOwnRoute={activeModuleId === mod.id}
              openDocks={openDocks}
            />
          )
        }),
      )}
    </>
  )
}
