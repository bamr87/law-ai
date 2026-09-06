/**
 * Shared vocabulary for the LSAT Lab and the panels it routes between.
 *
 * `LsatLab.tsx` is the tab router; each panel lives in its own file under
 * `components/lsat/`. What they need in common — the tab ids, the ARIA id
 * helpers that tie a tab to its panel, and the per-session score shape —
 * lives here so no panel has to import the router that mounts it.
 */

import type { LsatDifficulty } from '@/lib/api'

export type Tab = 'overview' | 'LR' | 'RC' | 'LG' | 'stats' | 'authoring'

export const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: 'overview', label: 'Overview', hint: 'How the LSAT is built' },
  { id: 'LR', label: 'Logical Reasoning', hint: 'Drill short-argument questions' },
  { id: 'RC', label: 'Reading Comprehension', hint: 'Practice passage sets' },
  { id: 'LG', label: 'Logic Games', hint: 'Sequencing & grouping setups' },
  { id: 'stats', label: 'Stats', hint: 'Your practice history' },
  { id: 'authoring', label: 'Authoring (HITL)', hint: 'Review AI-drafted questions' },
]

/**
 * Sections the lab can actually drill. The API also describes WS
 * (Argumentative Writing), which has no panel here — it is an essay, not a
 * keyed item, and it lives on the published static site. Jumping to it opened
 * an empty tabpanel with no tab selected: a dead end a keyboard user could
 * land on and had no marked way out of.
 */
export const PRACTICE_TABS = new Set<Tab>(['LR', 'RC', 'LG'])

export const DIFFICULTIES: { label: string; value: LsatDifficulty | 'any' }[] = [
  { label: 'Any', value: 'any' },
  { label: 'Easy', value: 'easy' },
  { label: 'Medium', value: 'med' },
  { label: 'Hard', value: 'hard' },
]

export const tabId = (t: Tab) => `lsat-tab-${t}`
export const tabPanelId = (t: Tab) => `lsat-panel-${t}`

export interface SessionScore {
  attempts: number
  correct: number
  /** Attempts answered after revealing at least one solve-guide hint. */
  assisted: number
}

/** What a drill panel reports back to the lab after each graded question. */
export type AttemptHandler = (
  correct: boolean,
  elapsedSeconds: number,
  hintsUsed?: number,
) => void
