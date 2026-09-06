import type { SettingValue } from './types'

/**
 * Where a setting row lives, and how to read a stored blob of them.
 *
 * Pure and DOM-free on purpose: the same parser runs in the browser over
 * `localStorage` and on the server over the mirrored cookie, so a layout
 * preference means exactly one thing in both renders (BL-20260905-09).
 */
export const SETTINGS_STORAGE_KEY = 'law-ai.settings.v1'

export function isSettingValue(row: unknown): row is SettingValue {
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
 * Rows from a stored JSON blob. Anything malformed — a hand-edited cookie, a
 * blob from an older build — reads as "nothing stored" rather than as an
 * exception in a render.
 */
export function parseSettingRows(raw: string | null | undefined): SettingValue[] {
  if (!raw) return []
  // The cookie is written percent-encoded, and different readers hand it back
  // decoded or not (`next/headers` decodes, `document.cookie` does not), so
  // try it as-is and then decoded rather than depending on which one it was.
  for (const candidate of [raw, tryDecode(raw)]) {
    if (candidate === null) continue
    try {
      const parsed = JSON.parse(candidate) as unknown
      if (Array.isArray(parsed)) return parsed.filter(isSettingValue)
    } catch {
      /* try the next form */
    }
  }
  return []
}

function tryDecode(raw: string): string | null {
  try {
    return decodeURIComponent(raw)
  } catch {
    return null
  }
}

/** Stable empty snapshot — identity matters to `useSyncExternalStore`. */
export const NO_ROWS: SettingValue[] = []
