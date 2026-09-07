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
 * Every widget a module can dock into the shell's panels, by id.
 *
 * The split is deliberate. A module declares *which* widgets it docks in
 * `lib/modules/catalog.ts` — as ids, so the catalog stays a plain data module
 * a server component can import — and this file, a client module, is the one
 * place that maps an id to the component (BL-20260831-14). Adding a second
 * dockable widget is therefore two data lines and one import, and `DockZone`
 * never learns what LSAT is.
 */
export const DOCK_REGISTRY: Record<string, ComponentType<DockedWidgetProps>> = {
  'lsat-timer': SectionTimerWidget,
}
