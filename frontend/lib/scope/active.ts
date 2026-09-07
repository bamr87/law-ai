/**
 * The active scope (BL-20260830-08).
 *
 * Spec 040 shipped a single instance scope because there was nothing else to
 * point at. Spec 036 matters give the `project` scope a real referent, and
 * with it the trap the scope switcher has always carried: a scope id is an
 * authorisation-adjacent identifier, so it must never be minted from
 * something the user can type.
 *
 * The rule this module enforces is one line long: **a project scope may only
 * be built from a matter row the server returned.** `projectScopeFor` takes
 * the row, not a slug; a URL slug is a *request* to resolve, and the resolving
 * is done by the API against the caller's own matters. An unknown or unowned
 * slug resolves to nothing and the shell stays on the instance scope — no
 * error, because "that matter is not yours" and "that matter does not exist"
 * must look the same.
 *
 * The selection lives in `sessionStorage`, not the URL and not a cookie: it is
 * a per-tab convenience, and a stale one costs nothing because every read of
 * matter data is re-authorised server-side anyway.
 */

import { INSTANCE_SCOPE, LIVE_SCOPES } from './instance'
import { chainTo } from './resolver'
import type { ScopeNode } from './types'

export const ACTIVE_SCOPE_STORAGE_KEY = 'law-ai.active-scope'

/** Shape of the server's matter row, narrowed to what a scope needs. */
export interface ScopeSource {
  id: number
  slug: string
  name: string
}

/**
 * Build a `project` scope from a server-returned matter row.
 *
 * The id is `project:<server id>` — never `project:<slug>` — so a scope id
 * cannot be forged by typing a URL.
 */
export function projectScopeFor(matter: ScopeSource): ScopeNode {
  return {
    id: `project:${matter.id}`,
    type: 'project',
    parentId: INSTANCE_SCOPE.id,
    slug: matter.slug,
    name: matter.name,
    depth: 1,
  }
}

function canUseStorage(): boolean {
  return typeof window !== 'undefined' && typeof window.sessionStorage !== 'undefined'
}

let snapshot: ScopeNode | null = null
let snapshotRead = false
const listeners = new Set<() => void>()

function read(): ScopeNode | null {
  if (!canUseStorage()) return null
  try {
    const raw = window.sessionStorage.getItem(ACTIVE_SCOPE_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<ScopeNode>
    if (
      typeof parsed?.id !== 'string' ||
      typeof parsed?.slug !== 'string' ||
      typeof parsed?.name !== 'string' ||
      parsed.type !== 'project'
    ) {
      return null
    }
    return {
      id: parsed.id,
      type: 'project',
      parentId: INSTANCE_SCOPE.id,
      slug: parsed.slug,
      name: parsed.name,
      depth: 1,
    }
  } catch {
    return null
  }
}

/**
 * Current project scope, or `null` for the instance scope.
 *
 * Cached by identity because `useSyncExternalStore` compares snapshots that
 * way — re-parsing on every render would loop.
 */
export function getActiveScope(): ScopeNode | null {
  if (!snapshotRead) {
    snapshot = read()
    snapshotRead = true
  }
  return snapshot
}

export function subscribeActiveScope(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Select a project scope, or clear back to the instance scope with `null`. */
export function setActiveScope(node: ScopeNode | null): void {
  snapshot = node
  snapshotRead = true
  if (canUseStorage()) {
    try {
      if (node) {
        window.sessionStorage.setItem(
          ACTIVE_SCOPE_STORAGE_KEY,
          JSON.stringify(node),
        )
      } else {
        window.sessionStorage.removeItem(ACTIVE_SCOPE_STORAGE_KEY)
      }
    } catch {
      /* a private window without storage still switches scope in memory */
    }
  }
  for (const listener of listeners) listener()
}

/** Reset between tests. */
export function resetActiveScope(): void {
  snapshot = null
  snapshotRead = false
  if (canUseStorage()) {
    try {
      window.sessionStorage.removeItem(ACTIVE_SCOPE_STORAGE_KEY)
    } catch {
      /* ignore */
    }
  }
}

/**
 * The scope chain the settings resolver should read, root-first.
 *
 * With no project selected this is exactly what shipped in spec 040, so the
 * switcher cannot change how settings resolve until a matter is chosen.
 */
export function activeScopeChain(node: ScopeNode | null): ScopeNode[] {
  if (!node) return [INSTANCE_SCOPE]
  return chainTo(node, [...LIVE_SCOPES, node])
}
