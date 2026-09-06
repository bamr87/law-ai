// Offline full-text search over the knowledge library (spec 048 FR-9).
//
// Mirrors `search_library()` in the backend's `library.py` — same tokenizer,
// same stemmer, same synonym table, same field weights, same snippet radius,
// same ordering — so a query returns the same ranking on both products. It
// runs entirely in the browser against the bundled `content.json`, which is
// what lets the published site search with zero network calls
// (NFR-OFFLINE-1).
//
// It is a token + field-weight ranker, not an index. Each query token is
// stemmed and expanded through SYNONYMS, so "assumptions" meets "assumption"
// and "LG" meets "logic games"; a field word also matches by prefix so
// search-as-you-type keeps working. Every token must match somewhere for an
// article to be a hit. True fuzzy (edit-distance) matching is deliberately
// absent (BL-20260903-06). The parity fixture in
// backend/tests/lsat/fixtures/search_parity.json pins this copy to the
// backend's rule for rule.

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

// --- Tokenizer, stemmer, synonyms — keep byte-for-byte in step with library.py

// Query-side synonyms. A token listed here also matches any alternate; a
// multi-word alternate counts when every one of its words is in the field.
const SYNONYMS: Record<string, string[]> = {
  lr: ['logical reasoning'],
  rc: ['reading comprehension'],
  lg: ['logic games', 'analytical reasoning'],
  ws: ['writing sample', 'writing'],
  games: ['logic games'],
  game: ['logic games'],
  flaw: ['fallacy'],
  flaws: ['fallacy'],
  fallacy: ['flaw'],
  fallacies: ['flaw'],
  premise: ['evidence'],
  conclusion: ['main point'],
  diagram: ['notation'],
  diagramming: ['notation'],
  timing: ['pacing'],
  pacing: ['timing'],
  inference: ['must be true'],
  necessary: ['required'],
  sufficient: ['guarantee'],
  contrapositive: ['conditional'],
}

// Dropped from the query only; field text keeps them.
const STOPWORDS = new Set(
  'a an and are as at be by does do for from how in is it of on or that the this to vs what when why with'.split(
    ' ',
  ),
)

const TOKEN_RE = /[a-z0-9]+/g
const MIN_STEM = 4

function stripDoubleConsonant(s: string): string {
  if (
    s.length >= 3 &&
    s[s.length - 1] === s[s.length - 2] &&
    !'aeiou'.includes(s[s.length - 1]) &&
    !'lsz'.includes(s[s.length - 1])
  ) {
    return s.slice(0, -1)
  }
  return s
}

/** Mirrors `stem()` in library.py: plurals, -ing, -ed, -ly, -ness, final e. */
export function stem(word: string): string {
  let w = word.toLowerCase()
  if (w.length < MIN_STEM) return w
  if (w.endsWith('ies') && w.length > 4) w = w.slice(0, -3) + 'y'
  else if (w.endsWith('sses')) w = w.slice(0, -2)
  else if (
    w.endsWith('s') &&
    !w.endsWith('ss') &&
    !w.endsWith('us') &&
    !w.endsWith('is')
  )
    w = w.slice(0, -1)
  if (w.endsWith('ness') && w.length > 6) w = w.slice(0, -4)
  if (w.endsWith('ing') && w.length > 5) w = stripDoubleConsonant(w.slice(0, -3))
  else if (w.endsWith('ed') && w.length > 4) w = stripDoubleConsonant(w.slice(0, -2))
  else if (w.endsWith('ly') && w.length > 4) w = w.slice(0, -2)
  if (w.endsWith('e') && w.length > 3) w = w.slice(0, -1)
  return w
}

export function tokenize(text: string): string[] {
  return text.toLowerCase().match(TOKEN_RE) ?? []
}

/** The tokens a query is matched on: ≥2 characters, stopwords dropped. */
export function queryTokens(query: string): string[] {
  return tokenize(query).filter((t) => t.length >= 2 && !STOPWORDS.has(t))
}

function fieldStems(text: string): string[] {
  return tokenize(text).map(stem)
}

function countMatches(field: string[], token: string): number {
  const target = stem(token)
  let count = 0
  for (const s of field) if (s === target || s.startsWith(token)) count += 1
  const fieldSet = new Set(field)
  for (const phrase of SYNONYMS[token] ?? []) {
    if (fieldStems(phrase).every((part) => fieldSet.has(part))) count += 1
  }
  return count
}

function firstMatchOffset(
  text: string,
  tokens: string[],
): [number, number] | null {
  const targets = new Set(tokens.map(stem))
  const re = new RegExp(TOKEN_RE.source, 'g')
  const lower = text.toLowerCase()
  let m: RegExpExecArray | null
  while ((m = re.exec(lower)) !== null) {
    const word = m[0]
    if (targets.has(stem(word)) || tokens.some((t) => word.startsWith(t))) {
      return [m.index, m.index + word.length]
    }
  }
  return null
}

function snippet(text: string, tokens: string[]): string | null {
  const span = firstMatchOffset(text, tokens)
  if (span === null) return null
  const [at, stop] = span
  const start = Math.max(0, at - SNIPPET_RADIUS)
  const end = Math.min(text.length, stop + SNIPPET_RADIUS)
  return (
    (start > 0 ? '…' : '') +
    text.slice(start, end).trim() +
    (end < text.length ? '…' : '')
  )
}

type Fields = { title: string[]; summary: string[]; tag: string[]; body: string[] }

// Per-article tokenised fields are built once and reused across every
// keystroke — re-stemming 35 bodies per character is the difference between
// instant and laggy.
const fieldCache = new Map<string, Fields>()

function fieldsFor(article: Article): Fields {
  let f = fieldCache.get(article.id)
  if (!f) {
    f = {
      title: fieldStems(article.title),
      summary: fieldStems(article.summary),
      tag: fieldStems(article.tags.join(' ')),
      body: fieldStems(bodies.get(article.id) ?? ''),
    }
    fieldCache.set(article.id, f)
  }
  return f
}

function scoreArticle(
  article: Article,
  tokens: string[],
): { score: number; where: string[]; anchor: string | null } {
  const fields = fieldsFor(article)
  const headings = article.outline.map(
    (e) => [e.anchor, fieldStems(e.text)] as const,
  )
  let score = 0
  const where: string[] = []
  let anchor: string | null = null
  for (const token of tokens) {
    let matched = false
    for (const name of ['title', 'summary', 'tag'] as const) {
      if (countMatches(fields[name], token) > 0) {
        score += WEIGHTS[name]
        matched = true
        if (!where.includes(name)) where.push(name)
      }
    }
    const hit = headings.filter(([, stems]) => countMatches(stems, token) > 0)
    if (hit.length > 0) {
      score += WEIGHTS.heading * hit.length
      matched = true
      if (!where.includes('heading')) where.push('heading')
      anchor = anchor ?? hit[0][0]
    }
    const occurrences = countMatches(fields.body, token)
    if (occurrences > 0) {
      score += WEIGHTS.body * Math.min(occurrences, 5)
      matched = true
      if (!where.includes('body')) where.push('body')
    }
    if (!matched) return { score: 0, where: [], anchor: null }
  }
  return { score, where, anchor }
}

export function searchLibrary(query: string, limit = 20): SearchHit[] {
  const tokens = queryTokens(query)
  if (tokens.length === 0) return []

  const hits: SearchHit[] = []
  for (const article of articles) {
    const { score, where, anchor } = scoreArticle(article, tokens)
    if (score === 0) continue
    const body = bodies.get(article.id) ?? ''
    hits.push({
      id: article.id,
      title: article.title,
      kind: article.kind,
      sections: article.sections,
      reading_minutes: article.reading_minutes,
      score,
      matched_in: where,
      snippet: snippet(body, tokens) ?? article.summary,
      anchor,
    })
  }

  hits.sort((a, b) => b.score - a.score || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
  return hits.slice(0, limit)
}
