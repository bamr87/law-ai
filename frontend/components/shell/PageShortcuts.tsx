'use client'

import type { ShortcutGroup } from '@/lib/shell/shortcuts'
import { createContext, useContext, useEffect, type ReactNode } from 'react'

/**
 * How a page contributes rows to the shell's `?` sheet (BL-20260901-10).
 *
 * The shell cannot know what keys a screen binds — that is the screen's
 * business, and hard-coding the LSAT drill's keys into `shortcuts.ts` would
 * put a feature's contract in the chrome. So a screen registers a group while
 * it is mounted and drops it on unmount, and the sheet shows the shell's keys
 * plus whatever is on screen right now.
 *
 * Registration is refcounted by title: a reading-comprehension passage stacks
 * several question cards, and the first one to unmount must not take the
 * group away from the others.
 */
export interface ShortcutRegistry {
  register: (group: ShortcutGroup) => void
  unregister: (title: string) => void
}

const PageShortcutsContext = createContext<ShortcutRegistry | null>(null)

export function PageShortcutsProvider({
  registry,
  children,
}: {
  registry: ShortcutRegistry
  children: ReactNode
}) {
  return (
    <PageShortcutsContext.Provider value={registry}>
      {children}
    </PageShortcutsContext.Provider>
  )
}

/**
 * Publish this component's keys to the `?` sheet for as long as it is on
 * screen. Pass a **module-level constant**: the group is identified by its
 * title, and a fresh object every render would register on every render.
 *
 * Outside the shell (a component rendered on its own in a test) there is no
 * registry and this does nothing — a screen must not need the shell to work.
 */
export function usePageShortcuts(group: ShortcutGroup): void {
  const registry = useContext(PageShortcutsContext)
  const title = group.title

  useEffect(() => {
    if (!registry) return
    registry.register(group)
    return () => registry.unregister(title)
    // `group` is required to be a stable constant; `title` is what identifies
    // it to the registry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [registry, title])
}
