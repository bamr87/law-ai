import type { SettingValue } from './types'

/**
 * Where a setting row lives, and how to read a stored blob of them.
 *
 * Pure and DOM-free on purpose: the same parser runs in the browser over
 * `localStorage` and on the server over the mirrored cookie, so a layout
 * preference means exactly one thing in both renders (BL-20260905-09).
 */
export const SETTINGS_STORAGE_KEY = 'law-ai.settings.v1'

/**
 * Cookie naming the scope the rows were resolved *against* (BL-20260905-10).
 *
 * Layout preferences moved to the user scope, and a row written at `user:<pk>`
 * is invisible to a resolver walking `[instance]` alone — which is what the
 * server render walks, since it cannot see the client's session state. Without
 * this the first paint dropped a signed-in user's layout and reflowed on every
 * full load, undoing the guarantee BL-20260905-09's row mirror exists for. The
 * id is the server's own (`/api/settings/values` names it); the cookie is a
 * mirror, never an authority — a write is still authorised server-side.
 */
export const SETTINGS_SCOPE_KEY = 'law-ai.settings.scope.v1'

/**
 * A user scope id from a stored cookie, or `null`.
 *
 * Only the `user:<id>` shape is accepted: anything else — a hand-edited
 * cookie, a shape from a later build — reads as "signed out", which resolves
 * exactly as it did before user scopes existed.
 */
export function parseScopeId(raw: string | null | undefined): string | null {
  if (!raw) return null
  const decoded = tryDecode(raw) ?? raw
  const value = decoded.trim()
  if (!/^user:[A-Za-z0-9_-]{1,64}$/.test(value)) return null
  return value
}

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
export function parseSettingRows(
  raw: string | null | undefined,
): SettingValue[] {
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
