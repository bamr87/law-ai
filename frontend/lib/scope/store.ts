import {
  mirroredRows,
  NO_ROWS,
  parseScopeId,
  parseSettingRows,
  SETTINGS_SCOPE_KEY as SCOPE_KEY,
  SETTINGS_STORAGE_KEY as STORAGE_KEY,
} from './rows'
import type { SettingValue } from './types'

export { STORAGE_KEY as SETTINGS_STORAGE_KEY, SCOPE_KEY as SETTINGS_SCOPE_KEY }

function canUseStorage(): boolean {
  return (
    typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
  )
}

function readAll(): SettingValue[] {
  if (!canUseStorage()) return []
  try {
    return parseSettingRows(window.localStorage.getItem(STORAGE_KEY))
  } catch {
    return []
  }
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
  mirrorToCookie(cookiePayload(rows))
}

/** What the cookie should hold for `rows`, or `null` for "drop it". */
function cookiePayload(rows: SettingValue[]): string | null {
  const carried = mirroredRows(rows)
  return carried.length > 0 ? JSON.stringify(carried) : null
}

/**
 * Mirror the rows into a cookie so the *server* render can lay the shell out
 * the way the user chose (BL-20260905-09).
 *
 * localStorage stays the source of truth — it is what `useSyncExternalStore`
 * reads after hydration. The cookie exists only so the first paint is already
 * right instead of reflowing once per full load. A cookie is capped near 4KB
 * by every browser, so an oversized blob is dropped rather than truncated into
 * something that would parse as garbage: the layout then reflows, which is the
 * behaviour we had before this existed.
 *
 * Only the layout rows travel (`MIRRORED_SETTING_KEYS`, BL-20260905-29). The
 * whole store used to, which put the first paint one verbose feature setting
 * away from blowing the cap and taking the layout down with it — a cost the
 * server render was never getting anything back for.
 */
const COOKIE_MAX_BYTES = 3500

function mirrorToCookie(json: string | null): void {
  if (typeof document === 'undefined') return
  const base = `${STORAGE_KEY}=`
  if (json === null) {
    document.cookie = `${base}; Path=/; SameSite=Lax; Max-Age=0`
    return
  }
  const encoded = encodeURIComponent(json)
  if (encoded.length > COOKIE_MAX_BYTES) {
    document.cookie = `${base}; Path=/; SameSite=Lax; Max-Age=0`
    return
  }
  document.cookie = `${base}${encoded}; Path=/; SameSite=Lax; Max-Age=31536000`
}

/**
 * Bring the cookie back in line with localStorage.
 *
 * They can only diverge when one of the two is cleared on its own (site data
 * wiped, a cookie expired, a profile copied). localStorage wins, because that
 * is what the running app reads; the cookie is rewritten so the *next* load
 * paints correctly. Returns whether anything changed, which is what the test
 * asserts on.
 */
export function reconcileSettingsCookie(): boolean {
  if (!canUseStorage() || typeof document === 'undefined') return false
  const json = cookiePayload(readAll())
  const current = readSettingsCookie()
  if (current === (json === null ? null : json)) return false
  mirrorToCookie(json)
  return true
}

/** The mirrored blob as the browser currently holds it, or `null`. */
export function readSettingsCookie(): string | null {
  if (typeof document === 'undefined') return null
  for (const part of document.cookie.split(';')) {
    const [name, ...rest] = part.trim().split('=')
    if (name === STORAGE_KEY) {
      const raw = rest.join('=')
      if (!raw) return null
      try {
        return decodeURIComponent(raw)
      } catch {
        return null
      }
    }
  }
  return null
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

/**
 * Server render sees no localStorage. The rows the server *does* have come
 * from the mirrored cookie and reach `useSetting` through
 * `SettingsSnapshotProvider`; with no provider — a bare component in a test —
 * this stable empty list is the answer.
 */
export function getSettingsServerSnapshot(): SettingValue[] {
  return NO_ROWS
}

/**
 * Server persistence (BL-20260830-07). Off until :func:`hydrateSettingValues`
 * succeeds, so an anonymous visitor — and every existing test — keeps the
 * localStorage-only behaviour byte-identical. Once a signed-in session has
 * hydrated, local writes are mirrored to the server optimistically: the UI
 * never waits on the network, and a failed mirror leaves localStorage as the
 * cache it always was.
 */
let serverScopeId: string | null = null

/** The scope local writes mirror to, or `null` when persistence is off. */
export function serverSyncScope(): string | null {
  return serverScopeId
}

/**
 * Scopes the server said this caller may write (BL-20260906-73).
 *
 * `null` means "not answered": either nothing has hydrated yet, or the backend
 * predates the field. Callers must treat that as "assume writable" — refusing
 * a write the server would have accepted is the worse failure.
 */
let writableScopeIds: string[] | null = null

/** The scopes the server will accept a write for, or `null` when unknown. */
export function serverWritableScopes(): string[] | null {
  return writableScopeIds
}

/**
 * Whether a write to `scopeId` will be accepted server-side.
 *
 * Optimistic while the answer is unknown, so signed-out and offline behaviour
 * stays exactly what it was before the field existed.
 */
export function mayWriteScope(scopeId: string): boolean {
  return writableScopeIds === null || writableScopeIds.includes(scopeId)
}

/** Turn server persistence off again (sign-out, or a failing backend). */
export function disableServerSync(): void {
  serverScopeId = null
  writableScopeIds = null
  writeScopeCookie(null)
}

/**
 * Mirror the caller's scope id for the *server* render (BL-20260905-10).
 *
 * The rows cookie says what was chosen; this one says who chose it. A layout
 * row now lives at `user:<pk>`, and a server resolver walking `[instance]`
 * alone skips it — so without this the first paint is the instance default and
 * the page reflows into the user's own layout on every load.
 */
function writeScopeCookie(scopeId: string | null): void {
  if (typeof document === 'undefined') return
  const base = `${SCOPE_KEY}=`
  if (scopeId === null) {
    document.cookie = `${base}; Path=/; SameSite=Lax; Max-Age=0`
    return
  }
  document.cookie = `${base}${encodeURIComponent(scopeId)}; Path=/; SameSite=Lax; Max-Age=31536000`
}

/** The mirrored scope id as the browser currently holds it, or `null`. */
export function readSettingsScopeCookie(): string | null {
  if (typeof document === 'undefined') return null
  for (const part of document.cookie.split(';')) {
    const [name, ...rest] = part.trim().split('=')
    if (name === SCOPE_KEY) return parseScopeId(rest.join('='))
  }
  return null
}

/**
 * Pull the caller's stored rows and merge them under the local ones.
 *
 * Server rows win for a key the server knows about — they are the durable
 * record — while purely local rows survive, so a preference set before
 * signing in is not silently dropped. Returns the number of rows applied, or
 * `null` when the backend is unreachable and nothing changed.
 */
export async function hydrateSettingValues(): Promise<number | null> {
  let payload
  try {
    const { fetchSettingValues } = await import('@/lib/api')
    payload = await fetchSettingValues()
  } catch {
    return null
  }
  const own = payload.scopes.find((s) => s.startsWith('user:')) ?? null
  serverScopeId = own
  writableScopeIds = payload.writableScopes ?? null
  // So the *next* server render resolves the same chain this one does.
  writeScopeCookie(own)
  const local = readAll()
  const merged = local.filter(
    (row) =>
      !payload.values.some(
        (r) => r.scopeId === row.scopeId && r.key === row.key,
      ),
  )
  for (const row of payload.values) {
    merged.push({
      scopeId: row.scopeId,
      key: row.key,
      value: row.value,
      locked: Boolean(row.locked),
    })
  }
  writeAll(merged)
  invalidate()
  return payload.values.length
}

function mirrorUpsert(row: SettingValue): void {
  if (serverScopeId === null) return
  void import('@/lib/api')
    .then(({ putSettingValue }) =>
      putSettingValue(row.scopeId, row.key, row.value, row.locked),
    )
    .catch(() => {
      /* localStorage remains the cache; a failed mirror is not the user's problem */
    })
}

function mirrorDelete(scopeId: string, key: string): void {
  if (serverScopeId === null) return
  void import('@/lib/api')
    .then(({ deleteStoredSettingValue }) =>
      deleteStoredSettingValue(scopeId, key),
    )
    .catch(() => {
      /* see mirrorUpsert */
    })
}

export function upsertSettingValue(row: SettingValue): SettingValue[] {
  const next = readAll().filter(
    (r) => !(r.scopeId === row.scopeId && r.key === row.key),
  )
  next.push(row)
  writeAll(next)
  invalidate()
  mirrorUpsert(row)
  return next
}

export function deleteSettingValue(
  scopeId: string,
  key: string,
): SettingValue[] {
  const next = readAll().filter(
    (r) => !(r.scopeId === scopeId && r.key === key),
  )
  writeAll(next)
  invalidate()
  mirrorDelete(scopeId, key)
  return next
}
