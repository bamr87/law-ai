// Offline full-text search over the knowledge library (spec 048 FR-9).
//
// Mirrors `search_library()` in the backend's `library.py` — same field
// weights, same snippet radius, same ordering — so a query returns the same
// ranking on both products. It runs entirely in the browser against the
// bundled `content.json`, which is what lets the published site search with
// zero network calls (NFR-OFFLINE-1).
//
// It is a substring + field-weight ranker, not an index. At 35 articles that
// is instant and needs no build step; it has no stemming, so "assumptions"
// does not match "assumption" in body text (BL-20260903-06).

import { articles } from './data'
import type { Article, Block, Cell, Span } from './types'

const WEIGHTS = { title: 8, summary: 4, tag: 3, heading: 3, body: 1 }
const SNIPPET_RADIUS = 90

function spansText(spans: Span[]): string {
  return spans.map((s) => s.text).join(' ')
}

function cellsText(cells: Cell[]): string {
  return cells.map(spansText).join(' ')
}

/** Flatten one block to plain text. Mirrors `block_text()` in library.py. */
export function blockText(block: Block): string {
  switch (block.block_type) {
    case 'heading':
      return block.text
    case 'paragraph':
      return spansText(block.spans)
    case 'list':
      return cellsText(block.items)
    case 'notation':
      return block.lines.join(' ')
    case 'table':
      return [cellsText(block.headers), ...block.rows.map(cellsText)].join(' ')
    case 'callout':
      return [block.title, ...block.blocks.map(blockText)].join(' ')
    default:
      return ''
  }
}

export function articleText(article: Article): string {
  return article.blocks.map(blockText).join(' ')
}

// Bodies are flattened once and reused across every keystroke — re-walking 35
// block trees per character is the difference between instant and laggy.
const bodies = new Map<string, string>(
  articles.map((a) => [a.id, articleText(a)]),
)

export interface SearchHit {
  id: string
  title: string
  kind: Article['kind']
  sections: Article['sections']
  reading_minutes: number
  score: number
  matched_in: string[]
  snippet: string
  anchor: string | null
}

function snippet(text: string, needle: string): string | null {
  const at = text.toLowerCase().indexOf(needle)
  if (at === -1) return null
  const start = Math.max(0, at - SNIPPET_RADIUS)
  const end = Math.min(text.length, at + needle.length + SNIPPET_RADIUS)
  return (
    (start > 0 ? '…' : '') +
    text.slice(start, end).trim() +
    (end < text.length ? '…' : '')
  )
}

function countOccurrences(haystack: string, needle: string): number {
  let count = 0
  let from = 0
  for (;;) {
    const at = haystack.indexOf(needle, from)
    if (at === -1) return count
    count += 1
    from = at + needle.length
  }
}

export function searchLibrary(query: string, limit = 20): SearchHit[] {
  const needle = query.trim().toLowerCase()
  if (needle.length < 2) return []

  const hits: SearchHit[] = []
  for (const article of articles) {
    let score = 0
    const matchedIn: string[] = []

    if (article.title.toLowerCase().includes(needle)) {
      score += WEIGHTS.title
      matchedIn.push('title')
    }
    if (article.summary.toLowerCase().includes(needle)) {
      score += WEIGHTS.summary
      matchedIn.push('summary')
    }
    if (article.tags.some((t) => t.toLowerCase().includes(needle))) {
      score += WEIGHTS.tag
      matchedIn.push('tag')
    }
    const headings = article.outline.filter((e) =>
      e.text.toLowerCase().includes(needle),
    )
    if (headings.length > 0) {
      score += WEIGHTS.heading * headings.length
      matchedIn.push('heading')
    }
    const body = bodies.get(article.id) ?? ''
    const occurrences = countOccurrences(body.toLowerCase(), needle)
    if (occurrences > 0) {
      score += WEIGHTS.body * Math.min(occurrences, 5)
      matchedIn.push('body')
    }
    if (score === 0) continue

    hits.push({
      id: article.id,
      title: article.title,
      kind: article.kind,
      sections: article.sections,
      reading_minutes: article.reading_minutes,
      score,
      matched_in: matchedIn,
      snippet: snippet(body, needle) ?? article.summary,
      anchor: headings[0]?.anchor ?? null,
    })
  }

  hits.sort((a, b) => b.score - a.score || a.id.localeCompare(b.id))
  return hits.slice(0, limit)
}
