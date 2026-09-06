/**
 * Server-persisted settings on the client (BL-20260830-07).
 *
 * Two invariants: the resolver engine is untouched, and an anonymous visitor
 * behaves exactly as before — no server write leaves the browser until a
 * signed-in hydrate has happened.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'

import { server } from '@/mocks/server'
import {
  deleteSettingValue,
  disableServerSync,
  hydrateSettingValues,
  listSettingValues,
  serverSyncScope,
  upsertSettingValue,
  SETTINGS_STORAGE_KEY,
} from '@/lib/scope/store'

const VALUES_URL = 'http://localhost:8000/api/settings/values'

beforeEach(() => {
  window.localStorage.clear()
  disableServerSync()
})

afterEach(() => {
  disableServerSync()
})

describe('hydrateSettingValues', () => {
  it('merges server rows over local ones and keeps purely local rows', async () => {
    upsertSettingValue({
      scopeId: 'instance:local',
      key: 'shell.density',
      value: 'compact',
      locked: false,
    })
    upsertSettingValue({
      scopeId: 'instance:local',
      key: 'shell.local-only',
      value: 1,
      locked: false,
    })
    server.use(
      http.get(VALUES_URL, () =>
        HttpResponse.json({
          scopes: ['instance:local', 'user:7'],
          values: [
            {
              scopeId: 'instance:local',
              key: 'shell.density',
              value: 'cosy',
              locked: true,
            },
          ],
        }),
      ),
    )

    expect(await hydrateSettingValues()).toBe(1)
    const rows = listSettingValues()
    const density = rows.find((r) => r.key === 'shell.density')
    expect(density?.value).toBe('cosy')
    expect(density?.locked).toBe(true)
    // A row the server has never heard of survives.
    expect(rows.some((r) => r.key === 'shell.local-only')).toBe(true)
  })

  it('enables mirroring only when the chain includes a user scope', async () => {
    server.use(
      http.get(VALUES_URL, () =>
        HttpResponse.json({ scopes: ['instance:local'], values: [] }),
      ),
    )
    await hydrateSettingValues()
    expect(serverSyncScope()).toBeNull()

    server.use(
      http.get(VALUES_URL, () =>
        HttpResponse.json({ scopes: ['instance:local', 'user:7'], values: [] }),
      ),
    )
    await hydrateSettingValues()
    expect(serverSyncScope()).toBe('user:7')
  })

  it('is a no-op when the backend is unreachable', async () => {
    server.use(http.get(VALUES_URL, () => HttpResponse.error()))
    expect(await hydrateSettingValues()).toBeNull()
    expect(serverSyncScope()).toBeNull()
  })
})

describe('local writes', () => {
  it('sends nothing to the server for an anonymous visitor', async () => {
    const seen: string[] = []
    server.use(
      http.put('http://localhost:8000/api/settings/values/*', ({ request }) => {
        seen.push(request.url)
        return HttpResponse.json({})
      }),
    )
    upsertSettingValue({
      scopeId: 'instance:local',
      key: 'shell.rail',
      value: false,
      locked: false,
    })
    await new Promise((r) => setTimeout(r, 10))
    expect(seen).toEqual([])
    // …and the row is still in localStorage, exactly as before.
    expect(window.localStorage.getItem(SETTINGS_STORAGE_KEY)).toContain('shell.rail')
  })

  it('mirrors an upsert and a delete once hydrated as a user', async () => {
    server.use(
      http.get(VALUES_URL, () =>
        HttpResponse.json({ scopes: ['instance:local', 'user:7'], values: [] }),
      ),
    )
    await hydrateSettingValues()

    const puts: unknown[] = []
    const deletes: string[] = []
    server.use(
      http.put(
        'http://localhost:8000/api/settings/values/user%3A7/shell.rail',
        async ({ request }) => {
          puts.push(await request.json())
          return HttpResponse.json({
            scopeId: 'user:7',
            key: 'shell.rail',
            value: false,
            locked: false,
          })
        },
      ),
      http.delete(
        'http://localhost:8000/api/settings/values/user%3A7/shell.rail',
        ({ request }) => {
          deletes.push(request.url)
          return HttpResponse.json({ deleted: true })
        },
      ),
    )

    upsertSettingValue({
      scopeId: 'user:7',
      key: 'shell.rail',
      value: false,
      locked: false,
    })
    await new Promise((r) => setTimeout(r, 20))
    expect(puts[0]).toMatchObject({ value: false, locked: false })

    deleteSettingValue('user:7', 'shell.rail')
    await new Promise((r) => setTimeout(r, 20))
    expect(deletes).toHaveLength(1)
  })

  it('keeps the local write when the mirror fails', async () => {
    server.use(
      http.get(VALUES_URL, () =>
        HttpResponse.json({ scopes: ['instance:local', 'user:7'], values: [] }),
      ),
      http.put('http://localhost:8000/api/settings/values/*', () =>
        HttpResponse.error(),
      ),
    )
    await hydrateSettingValues()

    upsertSettingValue({
      scopeId: 'user:7',
      key: 'shell.rail',
      value: true,
      locked: false,
    })
    await new Promise((r) => setTimeout(r, 20))
    expect(listSettingValues().some((r) => r.key === 'shell.rail')).toBe(true)
  })
})
