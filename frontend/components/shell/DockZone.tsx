'use client'

import SectionTimerWidget from '@/components/lsat/SectionTimerWidget'
import type { Dock } from '@/lib/settings/catalog'
import type { ComponentType } from 'react'

export interface DockedWidgetProps {
  /** The zone asking to render. The widget draws only if it belongs here. */
  dock: Dock
  onOwnRoute: boolean
  openDocks: Dock[]
}

/**
 * Widgets a module can dock into the shell's panels.
 *
 * Registered here rather than in `lib/modules/catalog.ts` so the catalog stays
 * a plain data module that server components can import. Each widget decides
 * for itself whether it belongs in the asking zone and whether it should show
 * on the current route — the shell stays ignorant of what LSAT is.
 */
const DOCKED_WIDGETS: { id: string; Widget: ComponentType<DockedWidgetProps> }[] =
  [{ id: 'lsat-timer', Widget: SectionTimerWidget }]

export default function DockZone({
  dock,
  onOwnRoute,
  openDocks,
}: DockedWidgetProps) {
  return (
    <>
      {DOCKED_WIDGETS.map(({ id, Widget }) => (
        <Widget
          key={id}
          dock={dock}
          onOwnRoute={onOwnRoute}
          openDocks={openDocks}
        />
      ))}
    </>
  )
}
