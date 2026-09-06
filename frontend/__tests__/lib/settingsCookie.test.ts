import { beforeEach, describe, expect, it } from 'vitest'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import {
  MIRRORED_SETTING_KEYS,
  parseSettingRows,
  SETTINGS_STORAGE_KEY,
} from '@/lib/scope/rows'
import {
  deleteSettingValue,
  listSettingValues,
  readSettingsCookie,
  reconcileSettingsCookie,
  upsertSettingValue,
} from '@/lib/scope/store'
import { hitlThreshold, railVisible } from '@/lib/settings/catalog'
import { LAYOUT_SETTINGS } from '@/lib/shell/layout'

/**
 * The store mirrors its rows into a cookie so the server render can lay the
 * shell out the way the user chose (BL-20260905-09). localStorage stays the
 * source of truth; the cookie is a copy for the first paint.
 */
function clearCookie() {
  document.cookie = `${SETTINGS_STORAGE_KEY}=; Path=/; Max-Age=0`
}

beforeEach(() => {
  window.localStorage.clear()
  clearCookie()
})

describe('settings cookie mirror', () => {
  it('writes the rows to the cookie on every store write', () => {
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: railVisible.key,
      value: false,
      locked: false,
    })
    const rows = parseSettingRows(readSettingsCookie())
    expect(rows).toEqual(listSettingValues())
    expect(rows.find((r) => r.key === railVisible.key)?.value).toBe(false)
  })

  it('parses the cookie the way the server will read it', () => {
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: railVisible.key,
      value: false,
      locked: false,
    })
    const raw = document.cookie
      .split(';')
      .map((p) => p.trim())
      .find((p) => p.startsWith(`${SETTINGS_STORAGE_KEY}=`))
    expect(raw).toBeTruthy()
    const encoded = (raw as string).slice(SETTINGS_STORAGE_KEY.length + 1)
    // Percent-encoded on the wire, and readable either way — `next/headers`
    // hands the value back decoded, `document.cookie` does not.
    expect(parseSettingRows(encoded)).toEqual(listSettingValues())
    expect(parseSettingRows(decodeURIComponent(encoded))).toEqual(
      listSettingValues(),
    )
  })

  it('drops the cookie when the last row goes away', () => {
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: railVisible.key,
      value: false,
      locked: false,
    })
    expect(readSettingsCookie()).toBeTruthy()
    deleteSettingValue(INSTANCE_SCOPE.id, railVisible.key)
    expect(readSettingsCookie()).toBeNull()
  })

  /**
   * BL-20260905-29: the cookie carries the layout and nothing else.
   *
   * A cookie is capped near 4KB, so mirroring the whole store put the first
   * paint one verbose feature setting away from blowing the cap — at which
   * point `mirrorToCookie` drops the blob and every visitor is back to the
   * reflow this mirror exists to prevent.
   */
  it('mirrors only the keys the server render lays out with', () => {
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: railVisible.key,
      value: false,
      locked: false,
    })
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: hitlThreshold.key,
      value: 0.42,
      locked: false,
    })
    // Both are stored…
    expect(listSettingValues()).toHaveLength(2)
    // …one travels.
    const carried = parseSettingRows(readSettingsCookie())
    expect(carried.map((r) => r.key)).toEqual([railVisible.key])
  })

  it('keeps the layout in the cookie however big the feature settings grow', () => {
    // Comfortably past COOKIE_MAX_BYTES on its own: mirroring the whole store
    // would drop the cookie entirely and lose the layout with it.
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: hitlThreshold.key,
      value: 'x'.repeat(8_000),
      locked: false,
    })
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: railVisible.key,
      value: false,
      locked: false,
    })
    const carried = parseSettingRows(readSettingsCookie())
    expect(carried.map((r) => r.key)).toEqual([railVisible.key])
  })

  it('drops the cookie when only unmirrored rows are left', () => {
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: hitlThreshold.key,
      value: 0.42,
      locked: false,
    })
    expect(readSettingsCookie()).toBeNull()
    // …and reconciling agrees there is nothing to write.
    expect(reconcileSettingsCookie()).toBe(false)
  })

  it('mirrors exactly the layout group — no drift between the two lists', () => {
    expect([...MIRRORED_SETTING_KEYS].sort()).toEqual(
      LAYOUT_SETTINGS.map((d) => d.key).sort(),
    )
  })

  it('reads nothing out of a malformed cookie rather than throwing', () => {
    document.cookie = `${SETTINGS_STORAGE_KEY}=not-json; Path=/`
    expect(parseSettingRows(readSettingsCookie())).toEqual([])
    document.cookie = `${SETTINGS_STORAGE_KEY}=${encodeURIComponent('[{"nope":1}]')}; Path=/`
    expect(parseSettingRows(readSettingsCookie())).toEqual([])
  })

  it('rewrites a cookie that has drifted from localStorage', () => {
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: railVisible.key,
      value: false,
      locked: false,
    })
    clearCookie()
    expect(readSettingsCookie()).toBeNull()

    expect(reconcileSettingsCookie()).toBe(true)
    expect(parseSettingRows(readSettingsCookie())).toEqual(listSettingValues())
    // Already in step: nothing to do.
    expect(reconcileSettingsCookie()).toBe(false)
  })
})
