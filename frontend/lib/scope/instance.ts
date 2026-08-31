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
