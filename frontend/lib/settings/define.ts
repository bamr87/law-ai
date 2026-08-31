import type { SettingDefinition, ScopeType } from '@/lib/scope/types'

export function defineSetting<T>(def: SettingDefinition<T>): SettingDefinition<T> {
  return def
}

export function parseBoolean(raw: unknown): boolean | undefined {
  return typeof raw === 'boolean' ? raw : undefined
}

export function parseNumber(raw: unknown): number | undefined {
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : undefined
}

export const INSTANCE_ONLY: ScopeType[] = ['instance']
