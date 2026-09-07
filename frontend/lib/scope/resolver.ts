import type {
  Effective,
  ScopeNode,
  SettingDefinition,
  SettingValue,
} from './types'

/**
 * Resolve the effective value of a setting along an ancestor chain.
 *
 * `chain` is root-first and MUST include the target as the last node.
 *
 * Rule (see specs/040-app-shell):
 * 1. Walk root → leaf.
 * 2. The deepest scope holding a *parsable* value wins…
 * 3. …unless any ancestor (including target) holds a parsable value with
 *    `locked = true`, in which case the *deepest locked* row wins.
 * 4. Unparsable stored JSON is skipped (type drift) and does not crash.
 * 5. If nothing remains, use the definition default.
 *
 * @example
 * const hitl = resolveEffective(hitlThreshold, [instance], [], true)
 * // hitl.value === 0.7, hitl.source === 'default'
 */
export function resolveEffective<T>(
  def: SettingDefinition<T>,
  chain: ScopeNode[],
  values: SettingValue[],
  canWrite: boolean,
): Effective<T> {
  if (chain.length === 0) {
    return {
      value: def.default,
      source: 'default',
      isInherited: true,
      locked: false,
      canOverride: false,
    }
  }

  const target = writeTargetIn(def, chain) ?? chain[chain.length - 1]
  const rows = values.filter((row) => row.key === def.key)
  const byScope = new Map(rows.map((row) => [row.scopeId, row]))

  let deepWinner: { node: ScopeNode; row: SettingValue; parsed: T } | null =
    null
  let lockedWinner: { node: ScopeNode; row: SettingValue; parsed: T } | null =
    null

  for (const node of chain) {
    const row = byScope.get(node.id)
    if (!row) continue
    const parsed = def.parse(row.value)
    if (parsed === undefined) continue
    const hit = { node, row, parsed }
    deepWinner = hit
    if (row.locked) lockedWinner = hit
  }

  const winner = lockedWinner ?? deepWinner
  const settableHere = def.settableAt.includes(target.type)

  if (!winner) {
    return {
      value: def.default,
      source: 'default',
      isInherited: true,
      locked: false,
      canOverride: canWrite && settableHere,
    }
  }

  const locked = lockedWinner !== null
  const isInherited = winner.node.id !== target.id
  const source = {
    scopeId: winner.node.id,
    scopeName: winner.node.name,
    type: winner.node.type,
  }

  return {
    value: winner.parsed,
    source,
    isInherited,
    locked,
    lockedBy: lockedWinner
      ? { scopeId: lockedWinner.node.id, scopeName: lockedWinner.node.name }
      : undefined,
    canOverride: canWrite && !locked && settableHere,
  }
}

/**
 * The deepest node in `chain` that may hold `def`, or `null` when none may.
 *
 * Not the chain's leaf (BL-20260905-10). Once a signed-in caller's chain is
 * `[instance, user]`, reading "can I edit this?" off the leaf made the two
 * deliberately instance-only settings — the HITL threshold and the graph's
 * citation counts — permanently read-only for anyone signed in, because a user
 * scope may not hold them. They are still editable; the edit just lands on the
 * instance, which is exactly where `settableAt` says it belongs.
 */
export function writeTargetIn(
  def: SettingDefinition<unknown>,
  chain: ScopeNode[],
): ScopeNode | null {
  for (let i = chain.length - 1; i >= 0; i -= 1) {
    if (def.settableAt.includes(chain[i].type)) return chain[i]
  }
  return null
}

/**
 * Ancestor chain from root to `target`, inclusive. `nodes` is a flat list.
 *
 * @example
 * chainTo(project, [instance, org, project])
 */
export function chainTo(target: ScopeNode, nodes: ScopeNode[]): ScopeNode[] {
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const walked: ScopeNode[] = []
  let cur: ScopeNode | undefined = target
  const seen = new Set<string>()
  while (cur && !seen.has(cur.id)) {
    seen.add(cur.id)
    walked.push(cur)
    cur = cur.parentId ? byId.get(cur.parentId) : undefined
  }
  return walked.reverse()
}
