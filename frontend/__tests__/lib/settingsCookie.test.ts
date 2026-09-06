import { beforeEach, describe, expect, it } from 'vitest'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { parseSettingRows, SETTINGS_STORAGE_KEY } from '@/lib/scope/rows'
import {
  deleteSettingValue,
  listSettingValues,
  readSettingsCookie,
  reconcileSettingsCookie,
  upsertSettingValue,
} from '@/lib/scope/store'
import { railVisible } from '@/lib/settings/catalog'

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
