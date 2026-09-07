import type { ScopeNode } from './types'

/** The only live scope in v1 (spec 040 / spec 036 NG3). */
export const INSTANCE_SCOPE: ScopeNode = {
  id: 'instance:local',
  type: 'instance',
  parentId: null,
  slug: 'local',
  name: 'Law AI (local)',
  depth: 0,
}

export const LIVE_SCOPES: ScopeNode[] = [INSTANCE_SCOPE]

/**
 * The signed-in user's own scope (BL-20260905-10).
 *
 * Built from the scope id the *server* names in `/api/settings/values`
 * (`user:<pk>`), never from anything typed: a scope id decides which rows a
 * write lands on, so it is not the client's to invent. `null` — nobody signed
 * in — leaves the chain exactly as spec 040 shipped it.
 */
export function userScopeFor(scopeId: string | null): ScopeNode | null {
  if (!scopeId || !scopeId.startsWith('user:')) return null
  return {
    id: scopeId,
    type: 'user',
    parentId: INSTANCE_SCOPE.id,
    slug: scopeId.slice('user:'.length),
    name: 'You',
    depth: 1,
  }
}

/**
 * The chain the settings resolver walks, root-first: instance, then the user
 * when there is one. An instance value therefore reads as *inherited* on a
 * user's screen — which is what it is — and their own override wins.
 */
export function settingsChain(userScope: ScopeNode | null): ScopeNode[] {
  return userScope ? [INSTANCE_SCOPE, userScope] : [INSTANCE_SCOPE]
}
