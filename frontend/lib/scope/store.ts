import type { SettingValue } from './types'

const STORAGE_KEY = 'law-ai.settings.v1'

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

function readAll(): SettingValue[] {
  if (!canUseStorage()) return []
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed.filter(isSettingValue)
  } catch {
    return []
  }
}

function isSettingValue(row: unknown): row is SettingValue {
  if (row === null || typeof row !== 'object') return false
  const r = row as Record<string, unknown>
  return (
    typeof r.scopeId === 'string' &&
    typeof r.key === 'string' &&
    typeof r.locked === 'boolean' &&
    'value' in r
  )
}

/**
 * Cached snapshot. `useSyncExternalStore` compares snapshots by identity, so
 * `listSettingValues()` must return the *same* array until something actually
 * writes — re-parsing localStorage on every render would loop forever.
 */
let snapshot: SettingValue[] | null = null
const listeners = new Set<() => void>()

function invalidate(): void {
  snapshot = null
  for (const l of listeners) l()
}

function writeAll(rows: SettingValue[]): void {
  if (!canUseStorage()) return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(rows))
}

export function subscribeSettings(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function listSettingValues(): SettingValue[] {
  if (snapshot === null) snapshot = readAll()
  return snapshot
}

/** Server render sees no localStorage; hand back a stable empty list. */
const EMPTY: SettingValue[] = []
export function getSettingsServerSnapshot(): SettingValue[] {
  return EMPTY
}

export function upsertSettingValue(row: SettingValue): SettingValue[] {
  const next = readAll().filter(
    (r) => !(r.scopeId === row.scopeId && r.key === row.key),
  )
  next.push(row)
  writeAll(next)
  invalidate()
  return next
}

export function deleteSettingValue(scopeId: string, key: string): SettingValue[] {
  const next = readAll().filter(
    (r) => !(r.scopeId === scopeId && r.key === key),
  )
  writeAll(next)
  invalidate()
  return next
}
