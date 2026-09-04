/**
 * Shared vocabulary and per-reader state for the LSAT knowledge library.
 *
 * Label maps live here rather than in a component so the contents rail, the
 * reader header and the search results all name a `kind` the same way. Read
 * state is per-browser `localStorage` — deliberately not synced anywhere
 * (BL-20260903-05 tracks folding it into `/api/lsat/stats`).
 */

import type { LsatArticleKind, LsatArticleLevel, LsatSectionCode } from '@/lib/api'

export const KIND_LABEL: Record<LsatArticleKind, string> = {
  orientation: 'Orientation',
  'section-guide': 'Section guide',
  'question-type': 'Question type',
  technique: 'Technique',
  strategy: 'Strategy',
  foundation: 'Foundations',
  'review-method': 'Review method',
}

/** Reading order for the contents rail: foundations before families. */
export const KIND_ORDER: LsatArticleKind[] = [
  'orientation',
  'foundation',
  'section-guide',
  'question-type',
  'technique',
  'strategy',
  'review-method',
]

export const LEVEL_LABEL: Record<LsatArticleLevel, string> = {
  foundation: 'Foundation',
  core: 'Core',
  advanced: 'Advanced',
}

export const SECTION_LABEL: Record<LsatSectionCode, string> = {
  LR: 'Logical Reasoning',
  RC: 'Reading Comprehension',
  LG: 'Logic Games',
  WS: 'Argumentative Writing',
}

const READ_KEY = 'lsat:library:read'
const LAST_KEY = 'lsat:library:last'

function safeGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    // Private mode, blocked site data, SSR — reading progress is a
    // convenience, never a correctness requirement.
    return null
  }
}

function safeSet(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* non-fatal */
  }
}

export function loadReadIds(): Set<string> {
  const raw = safeGet(READ_KEY)
  if (!raw) return new Set()
  try {
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? new Set(parsed.map(String)) : new Set()
  } catch {
    return new Set()
  }
}

export function saveReadIds(ids: Set<string>): void {
  safeSet(READ_KEY, JSON.stringify([...ids].sort()))
}

export function loadLastArticleId(): string | null {
  return safeGet(LAST_KEY)
}

export function saveLastArticleId(id: string): void {
  safeSet(LAST_KEY, id)
}

/** "4 min read" / "1 min read" — used in the rail and the reader header. */
export function readingLabel(minutes: number): string {
  return `${minutes} min read`
}

/**
 * True when the viewer asked for reduced motion.
 *
 * Guarded rather than called directly: `matchMedia` is absent in jsdom and in
 * any non-browser render, and a smooth-scroll convenience must never be the
 * thing that throws.
 */
export function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  } catch {
    return false
  }
}
