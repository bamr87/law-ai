/**
 * Shared vocabulary for the LSAT Lab and the panels it routes between.
 *
 * `LsatLab.tsx` is the tab router; each panel lives in its own file under
 * `components/lsat/`. What they need in common — the tab ids, the ARIA id
 * helpers that tie a tab to its panel, and the per-session score shape —
 * lives here so no panel has to import the router that mounts it.
 */

import type { LsatDifficulty } from '@/lib/api'

export type Tab =
  | 'overview'
  | 'LR'
  | 'RC'
  | 'LG'
  | 'WS'
  | 'stats'
  | 'authoring'

export const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: 'overview', label: 'Overview', hint: 'How the LSAT is built' },
  { id: 'LR', label: 'Logical Reasoning', hint: 'Drill short-argument questions' },
  { id: 'RC', label: 'Reading Comprehension', hint: 'Practice passage sets' },
  { id: 'LG', label: 'Logic Games', hint: 'Sequencing & grouping setups' },
  {
    id: 'WS',
    label: 'Writing',
    hint: 'Argumentative Writing — draft against the clock',
  },
  { id: 'stats', label: 'Stats', hint: 'Your practice history' },
  { id: 'authoring', label: 'Authoring (HITL)', hint: 'Review AI-drafted questions' },
]

/** Every tab id, for validating a `?tab=` param against the real set. */
export const TAB_IDS: Tab[] = TABS.map((t) => t.id)

/**
 * Sections the lab can actually drill.
 *
 * WS (Argumentative Writing) joined them in BL-20260901-09. It had been the
 * one section the API described and the lab could not open — an essay rather
 * than a keyed item, and until `WritingPanel` landed the Overview card for it
 * said "No drill in the lab yet" and sent the learner to the published static
 * site to practise the task law schools actually read.
 */
export const PRACTICE_TABS = new Set<Tab>(['LR', 'RC', 'LG', 'WS'])

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
