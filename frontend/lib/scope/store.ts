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

function writeAll(rows: SettingValue[]): void {
  if (!canUseStorage()) return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(rows))
}

export function listSettingValues(): SettingValue[] {
  return readAll()
}

export function upsertSettingValue(row: SettingValue): SettingValue[] {
  const next = readAll().filter(
    (r) => !(r.scopeId === row.scopeId && r.key === row.key),
  )
  next.push(row)
  writeAll(next)
  return next
}

export function deleteSettingValue(scopeId: string, key: string): SettingValue[] {
  const next = readAll().filter(
    (r) => !(r.scopeId === scopeId && r.key === key),
  )
  writeAll(next)
  return next
}
