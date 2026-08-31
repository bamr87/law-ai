export type ScopeType = 'instance' | 'org' | 'team' | 'project' | 'user'

export interface ScopeNode {
  id: string
  type: ScopeType
  parentId: string | null
  slug: string
  name: string
  depth: number
}

export interface SettingValue {
  scopeId: string
  key: string
  value: unknown
  locked: boolean
}

export interface SettingDefinition<T> {
  key: string
  label: string
  help: string
  default: T
  settableAt: ScopeType[]
  lockable: boolean
  parse: (raw: unknown) => T | undefined
}

export type EffectiveSource =
  | { scopeId: string; scopeName: string; type: ScopeType }
  | 'default'

export interface Effective<T> {
  value: T
  source: EffectiveSource
  isInherited: boolean
  locked: boolean
  lockedBy?: { scopeId: string; scopeName: string }
  canOverride: boolean
}
