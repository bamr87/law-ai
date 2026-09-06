import { renderHook, act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { useSetting } from '@/components/shell/useSetting'
import {
  INSTANCE_SCOPE,
  settingsChain,
  userScopeFor,
} from '@/lib/scope/instance'
import { resolveEffective, writeTargetIn } from '@/lib/scope/resolver'
import {
  disableServerSync,
  hydrateSettingValues,
  listSettingValues,
  upsertSettingValue,
} from '@/lib/scope/store'
import { railExpanded, hitlThreshold } from '@/lib/settings/catalog'
import { resetLayout } from '@/lib/shell/layout'
import { server } from '@/mocks/server'
import { http, HttpResponse } from 'msw'

/**
 * BL-20260905-10. Layout is a personal preference, and settings became
 * server-persisted in BL-20260830-07 — which is when "instance-scoped" started
 * meaning "everyone on this box shares one layout". These lock in the move to
 * user scope *and* that nothing changes for a signed-out visitor.
 */

async function signIn(userScopeId = 'user:7', values: unknown[] = []) {
  server.use(
    http.get('*/api/settings/values', () =>
      HttpResponse.json({ scopes: [INSTANCE_SCOPE.id, userScopeId], values }),
    ),
    http.put('*/api/settings/values', () => HttpResponse.json({ ok: true })),
    http.delete('*/api/settings/values', () => HttpResponse.json({ ok: true })),
  )
  await hydrateSettingValues()
}

beforeEach(() => {
  disableServerSync()
  window.localStorage.clear()
})

afterEach(() => {
  disableServerSync()
  window.localStorage.clear()
})

describe('scope chain', () => {
  it('is the single instance scope when nobody is signed in', () => {
    expect(settingsChain(userScopeFor(null))).toEqual([INSTANCE_SCOPE])
  })

  it('puts the user under the instance so instance reads as inherited', () => {
    const chain = settingsChain(userScopeFor('user:7'))
    expect(chain.map((n) => n.id)).toEqual(['instance:local', 'user:7'])
    expect(chain[1].parentId).toBe(INSTANCE_SCOPE.id)
  })

  it('ignores a scope id the server did not name', () => {
    expect(userScopeFor('project:1')).toBeNull()
    expect(userScopeFor('')).toBeNull()
  })
})

describe('layout settings at user scope', () => {
  it('a layout preference is settable by a user, a policy value is not', () => {
    expect(railExpanded.settableAt).toContain('user')
    expect(hitlThreshold.settableAt).not.toContain('user')
  })

  it('writes land on the instance while signed out', () => {
    const { result } = renderHook(() => useSetting(railExpanded))
    act(() => result.current[1](true))
    const row = listSettingValues().find((r) => r.key === railExpanded.key)
    expect(row?.scopeId).toBe(INSTANCE_SCOPE.id)
  })

  it('writes land on the user once signed in', async () => {
    await signIn()
    const { result } = renderHook(() => useSetting(railExpanded))
    act(() => result.current[1](true))
    const row = listSettingValues().find((r) => r.key === railExpanded.key)
    expect(row?.scopeId).toBe('user:7')
  })

  it('a policy setting still writes to the instance for a signed-in caller', async () => {
    await signIn()
    const { result } = renderHook(() => useSetting(hitlThreshold))
    act(() => result.current[1](0.9))
    const row = listSettingValues().find((r) => r.key === hitlThreshold.key)
    expect(row?.scopeId).toBe(INSTANCE_SCOPE.id)
  })

  it('the user value wins over the instance default, which stays inherited', async () => {
    await signIn()
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: railExpanded.key,
      value: false,
      locked: false,
    })
    upsertSettingValue({
      scopeId: 'user:7',
      key: railExpanded.key,
      value: true,
      locked: false,
    })
    const { result } = renderHook(() => useSetting(railExpanded))
    expect(result.current[0]).toBe(true)
    expect(result.current[2].source).toMatchObject({ scopeId: 'user:7' })
    expect(result.current[2].isInherited).toBe(false)
  })

  it('an instance value the user has not overridden reads as inherited', () => {
    const chain = settingsChain(userScopeFor('user:7'))
    const effective = resolveEffective(
      railExpanded,
      chain,
      [
        {
          scopeId: INSTANCE_SCOPE.id,
          key: railExpanded.key,
          value: true,
          locked: false,
        },
      ],
      true,
    )
    expect(effective.value).toBe(true)
    expect(effective.isInherited).toBe(true)
    expect(effective.source).toMatchObject({ type: 'instance' })
    expect(effective.canOverride).toBe(true)
  })

  it('an instance-only setting is written at the instance, not the chain leaf', () => {
    // The chain leaf is the user once someone signs in, but a policy value is
    // not theirs to hold. Reading "can I edit this?" off the leaf made the two
    // instance-only settings permanently read-only in /settings for every
    // signed-in caller (BL-20260905-10).
    const chain = settingsChain(userScopeFor('user:7'))
    expect(writeTargetIn(hitlThreshold, chain)?.id).toBe(INSTANCE_SCOPE.id)
    expect(writeTargetIn(railExpanded, chain)?.id).toBe('user:7')

    const unset = resolveEffective(hitlThreshold, chain, [], true)
    expect(unset.canOverride).toBe(true)

    const set = resolveEffective(
      hitlThreshold,
      chain,
      [
        {
          scopeId: INSTANCE_SCOPE.id,
          key: hitlThreshold.key,
          value: 0.9,
          locked: false,
        },
      ],
      true,
    )
    // The value is at the scope it is edited at, so it is not "inherited"
    // and the control is live rather than disabled behind an Override.
    expect(set.isInherited).toBe(false)
    expect(set.canOverride).toBe(true)
  })

  it('a locked instance value still wins over a user row', () => {
    const chain = settingsChain(userScopeFor('user:7'))
    const effective = resolveEffective(
      railExpanded,
      chain,
      [
        {
          scopeId: INSTANCE_SCOPE.id,
          key: railExpanded.key,
          value: false,
          locked: true,
        },
        {
          scopeId: 'user:7',
          key: railExpanded.key,
          value: true,
          locked: false,
        },
      ],
      true,
    )
    expect(effective.value).toBe(false)
    expect(effective.locked).toBe(true)
    expect(effective.canOverride).toBe(false)
  })
})

describe('resetLayout', () => {
  it('drops the user rows and leaves the instance default standing', async () => {
    await signIn()
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: railExpanded.key,
      value: true,
      locked: false,
    })
    upsertSettingValue({
      scopeId: 'user:7',
      key: railExpanded.key,
      value: false,
      locked: false,
    })
    resetLayout()
    const rows = listSettingValues().filter((r) => r.key === railExpanded.key)
    expect(rows.map((r) => r.scopeId)).toEqual([INSTANCE_SCOPE.id])
  })

  it('signed out, it still clears the instance rows', () => {
    upsertSettingValue({
      scopeId: INSTANCE_SCOPE.id,
      key: railExpanded.key,
      value: true,
      locked: false,
    })
    resetLayout()
    expect(
      listSettingValues().filter((r) => r.key === railExpanded.key),
    ).toEqual([])
  })
})
