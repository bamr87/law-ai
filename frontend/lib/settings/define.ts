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

/**
 * Parser for a closed set of string values. Anything not in the set — a stale
 * key from an older build, or a hand-edited localStorage row — falls back to
 * the setting's default rather than putting the UI in an unrenderable state.
 */
export function parseEnum<T extends string>(allowed: readonly T[]) {
  return (raw: unknown): T | undefined =>
    typeof raw === 'string' && (allowed as readonly string[]).includes(raw)
      ? (raw as T)
      : undefined
}

export const INSTANCE_ONLY: ScopeType[] = ['instance']
