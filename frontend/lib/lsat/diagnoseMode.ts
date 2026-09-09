/**
 * "Diagnose first" — the drill setting that asks a learner to name the question
 * type and the strategy before the answer choices appear (spec 053 FR-10).
 *
 * A module-level store rather than component state for the same reason the
 * timer is: the toggle lives in the lab header and the cards that honour it
 * live in whichever drill panel is mounted, and neither should have to be
 * threaded through the other. Persisted per browser so a learner who studies
 * this way keeps studying this way.
 */

import { useSyncExternalStore } from 'react'

const PERSIST_KEY = 'law-ai.lsat.diagnose.v1'

let enabled = readPersisted()
const listeners = new Set<() => void>()

function readPersisted(): boolean {
  try {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem(PERSIST_KEY) === '1'
  } catch {
    return false
  }
}

function emit() {
  for (const l of listeners) l()
}

/** Whether the drill asks for a diagnosis before showing the choices. */
export function getDiagnoseMode(): boolean {
  return enabled
}

export function setDiagnoseMode(next: boolean): void {
  if (enabled === next) return
  enabled = next
  try {
    if (typeof window !== 'undefined') {
      if (next) window.localStorage.setItem(PERSIST_KEY, '1')
      else window.localStorage.removeItem(PERSIST_KEY)
    }
  } catch {
    /* storage unavailable — the setting still holds for this page */
  }
  emit()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Read and set the setting from a component. */
export function useDiagnoseMode(): [boolean, (next: boolean) => void] {
  const value = useSyncExternalStore(subscribe, getDiagnoseMode, () => false)
  return [value, setDiagnoseMode]
}

/** Test hook: back to off, and forget what was persisted. */
export function resetDiagnoseModeForTests(): void {
  enabled = false
  try {
    if (typeof window !== 'undefined') window.localStorage.removeItem(PERSIST_KEY)
  } catch {
    /* ignore */
  }
  emit()
}
