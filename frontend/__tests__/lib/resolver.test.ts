import { describe, expect, it } from 'vitest'
import { chainTo, resolveEffective } from '@/lib/scope/resolver'
import type { ScopeNode, SettingDefinition, SettingValue } from '@/lib/scope/types'

const instance: ScopeNode = {
  id: 'i',
  type: 'instance',
  parentId: null,
  slug: 'root',
  name: 'Instance',
  depth: 0,
}
const org: ScopeNode = {
  id: 'o',
  type: 'org',
  parentId: 'i',
  slug: 'acme',
  name: 'Acme Corp',
  depth: 1,
}
const project: ScopeNode = {
  id: 'p',
  type: 'project',
  parentId: 'o',
  slug: 'api',
  name: 'API',
  depth: 2,
}

const flag: SettingDefinition<boolean> = {
  key: 'security.mfa.required',
  label: 'MFA',
  help: '',
  default: false,
  settableAt: ['instance', 'org', 'project'],
  lockable: true,
  parse: (raw) => (typeof raw === 'boolean' ? raw : undefined),
}

const ALL = [instance, org, project]

function chain(target: ScopeNode) {
  return chainTo(target, ALL)
}

function row(
  scopeId: string,
  value: unknown,
  locked = false,
): SettingValue {
  return { scopeId, key: flag.key, value, locked }
}

describe('chainTo', () => {
  it('returns root-first inclusive chain', () => {
    expect(chain(project).map((n) => n.id)).toEqual(['i', 'o', 'p'])
  })
})

describe('resolveEffective', () => {
  it('falls back to the definition default', () => {
    const e = resolveEffective(flag, chain(project), [], true)
    expect(e.value).toBe(false)
    expect(e.source).toBe('default')
    expect(e.isInherited).toBe(true)
    expect(e.canOverride).toBe(true)
  })

  it('inherits the nearest ancestor value', () => {
    const e = resolveEffective(flag, chain(project), [row('o', true)], true)
    expect(e.value).toBe(true)
    expect(e.source).toEqual({
      scopeId: 'o',
      scopeName: 'Acme Corp',
      type: 'org',
    })
    expect(e.isInherited).toBe(true)
    expect(e.canOverride).toBe(true)
  })

  it('lets a deeper scope override an ancestor', () => {
    const e = resolveEffective(
      flag,
      chain(project),
      [row('o', true), row('p', false)],
      true,
    )
    expect(e.value).toBe(false)
    expect(e.isInherited).toBe(false)
    expect(e.source).toMatchObject({ scopeId: 'p' })
  })

  it('lets a locked ancestor beat a deeper unlocked override', () => {
    const e = resolveEffective(
      flag,
      chain(project),
      [row('o', true, true), row('p', false)],
      true,
    )
    expect(e.value).toBe(true)
    expect(e.locked).toBe(true)
    expect(e.lockedBy).toEqual({ scopeId: 'o', scopeName: 'Acme Corp' })
    expect(e.canOverride).toBe(false)
  })

  it('lets a deeper lock beat a shallower lock', () => {
    const e = resolveEffective(
      flag,
      chain(project),
      [row('i', false, true), row('o', true, true)],
      true,
    )
    expect(e.value).toBe(true)
    expect(e.lockedBy).toEqual({ scopeId: 'o', scopeName: 'Acme Corp' })
  })

  it('skips type-drifted values and uses the default', () => {
    const e = resolveEffective(
      flag,
      chain(project),
      [row('o', 'yes-please')],
      true,
    )
    expect(e.value).toBe(false)
    expect(e.source).toBe('default')
  })

  it('skips drifted rows and still honors a parsable ancestor', () => {
    const e = resolveEffective(
      flag,
      chain(project),
      [row('i', true), row('o', 'nope')],
      true,
    )
    expect(e.value).toBe(true)
    expect(e.source).toMatchObject({ scopeId: 'i' })
  })

  it('refuses override when the target type is not settable', () => {
    const userOnly: SettingDefinition<boolean> = {
      ...flag,
      settableAt: ['user'],
    }
    const e = resolveEffective(userOnly, chain(project), [], true)
    expect(e.canOverride).toBe(false)
  })

  it('refuses override when the caller cannot write', () => {
    const e = resolveEffective(flag, chain(project), [], false)
    expect(e.canOverride).toBe(false)
  })
})
