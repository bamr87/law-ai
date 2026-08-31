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

export interface SettingOption<T> {
  value: T
  label: string
}

export interface SettingDefinition<T> {
  key: string
  label: string
  help: string
  default: T
  settableAt: ScopeType[]
  lockable: boolean
  parse: (raw: unknown) => T | undefined
  /**
   * Present for enum settings. `SettingField` renders a select from these
   * instead of inferring a control from the default's type, which only ever
   * covered boolean and number.
   */
  options?: SettingOption<T>[]
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
