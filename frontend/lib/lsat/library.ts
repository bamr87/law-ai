/**
 * Shared vocabulary and per-reader state for the LSAT knowledge library.
 *
 * Label maps live here rather than in a component so the contents rail, the
 * reader header and the search results all name a `kind` the same way.
 *
 * Read state is `localStorage` *plus* the server (BL-20260903-05). It used to
 * be localStorage alone, so a learner who read half the library on a laptop
 * started again on a phone, and "articles read" was invisible next to drill
 * accuracy. The browser's copy is still the one that answers instantly and the
 * one that works offline; the server's copy is what makes a second device
 * agree with the first, and it is what `/api/lsat/stats` folds in.
 *
 * `lsat-static` keeps localStorage as its only store, and always will — a
 * serverless bundle has nothing to sync with.
 */

import {
  fetchLsatReadArticles,
  recordLsatArticleRead,
  type LsatArticleKind,
  type LsatArticleLevel,
  type LsatSectionCode,
} from '@/lib/api'

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

/**
 * Concept entries are read-tracked with a `concept:` prefix so a concept and
 * an article sharing an id never collide. Only articles have a server
 * counterpart — the endpoint is keyed on the library index — so the prefix is
 * also what tells the two apart when syncing.
 */
const CONCEPT_PREFIX = 'concept:'

export const isArticleReadKey = (key: string): boolean =>
  !key.startsWith(CONCEPT_PREFIX)

/**
 * This browser's read set, merged with the server's.
 *
 * A union, not a replacement: reading done offline (or before the endpoint
 * existed) is real progress and must not be erased by a device that has read
 * less. Unmarking is therefore explicit — a POST with `read: false` — rather
 * than an absence. The merged set is written back to `localStorage` so the
 * next load starts from it even with no network.
 *
 * Never rejects: an unreachable API leaves the local set exactly as it was.
 */
export async function hydrateReadIds(): Promise<Set<string>> {
  const local = loadReadIds()
  try {
    const body = await fetchLsatReadArticles()
    const merged = new Set(local)
    for (const id of body.read) merged.add(id)
    saveReadIds(merged)
    return merged
  } catch {
    return local
  }
}

/**
 * Tell the server about one article's read state, fire-and-forget.
 *
 * The local set has already been updated by the time this is called, so a
 * failure costs cross-device sync for that one article and nothing else — it
 * must never reach the reader as an error.
 */
export function publishReadState(key: string, read: boolean): void {
  if (!isArticleReadKey(key)) return
  void recordLsatArticleRead(key, read).catch(() => {
    /* the browser's own copy is authoritative offline */
  })
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
