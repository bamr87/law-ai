/**
 * Library search parity with the backend ranker (BL-20260903-06).
 *
 * `lib/search.ts` mirrors `search_library()` in library.py by hand; the
 * fixture under backend/tests/lsat/fixtures/ is the contract both suites
 * assert, so a stemmer or synonym rule changed on one side fails the other.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { isTypo, queryTokens, searchLibrary, stem } from '@/lib/search'

interface Parity {
  stems: Record<string, string>
  query_tokens: Record<string, string[]>
  corpus: { query: string; top?: string | null; ids?: string[] }[]
  typo_pairs: { a: string; b: string; typo: boolean }[]
  corpus_typos: { query: string; top: string | null }[]
  scores: {
    query: string
    hits: { id: string; score: number; matched_in: string[] }[]
  }[]
}

// Vitest runs with the project root at lsat-static/, so the fixture resolves
// from cwd. `import.meta.url` is not usable here: package.json has no
// "type": "module", so the config and tests load as CommonJS.
const parity: Parity = JSON.parse(
  readFileSync(
    resolve(process.cwd(), '../backend/tests/lsat/fixtures/search_parity.json'),
    'utf-8',
  ),
)

describe('search parity with library.py', () => {
  it('stems every fixture word the way the backend does', () => {
    const got = Object.fromEntries(
      Object.keys(parity.stems).map((w) => [w, stem(w)]),
    )
    expect(got).toEqual(parity.stems)
  })

  it('stemming is idempotent', () => {
    for (const w of Object.keys(parity.stems)) expect(stem(stem(w))).toBe(stem(w))
  })

  it('tokenises queries the way the backend does', () => {
    const got = Object.fromEntries(
      Object.keys(parity.query_tokens).map((q) => [q, queryTokens(q)]),
    )
    expect(got).toEqual(parity.query_tokens)
  })

  it('judges typos the way the backend does', () => {
    for (const { a, b, typo } of parity.typo_pairs) {
      expect(isTypo(a, b), `${a}/${b}`).toBe(typo)
      expect(isTypo(b, a), `${b}/${a}`).toBe(typo)
    }
  })

  it('lands mistyped queries on the same article as the backend', () => {
    for (const c of parity.corpus_typos) {
      const ids = searchLibrary(c.query, 5).map((h) => h.id)
      if (c.top === null) expect(ids, c.query).toEqual([])
      else expect(ids[0], c.query).toBe(c.top)
    }
  })

  it('scores the shipped corpus the way the backend does', () => {
    // Order parity hides arithmetic divergence: a weight, an occurrence cap
    // or the half-weight typo fallback can change on one side alone and leave
    // the ranking intact. The number and the fields it came from cannot
    // (BL-20260905-52).
    for (const c of parity.scores) {
      const got = searchLibrary(c.query, c.hits.length).map((h) => ({
        id: h.id,
        score: h.score,
        matched_in: h.matched_in,
      }))
      expect(got, c.query).toEqual(c.hits)
    }
  })

  it('ranks the shipped corpus the way the backend does', () => {
    for (const c of parity.corpus) {
      const ids = searchLibrary(c.query, 5).map((h) => h.id)
      if (c.ids) expect(ids.slice(0, c.ids.length), c.query).toEqual(c.ids)
      else if (c.top === null) expect(ids, c.query).toEqual([])
      else expect(ids[0], c.query).toBe(c.top)
    }
  })
})

describe('searchLibrary', () => {
  it('matches a plural query against singular text', () => {
    const hits = searchLibrary('assumptions')
    expect(hits[0]?.id).toBe('lr-assumption-family')
    expect(hits[0]?.matched_in).toContain('body')
  })

  it('requires every token to match somewhere', () => {
    expect(searchLibrary('assumptions xyzzy')).toEqual([])
  })

  it('drops stopwords and ignores one-letter queries', () => {
    expect(searchLibrary('the')).toEqual([])
    expect(searchLibrary('a')).toEqual([])
  })
})

/**
 * Section narrowing (issue #120).
 *
 * The Library's section chips used to go cosmetic the moment a query was
 * typed, because the search branch called this ranker with no knowledge of the
 * filter. The narrowing lives here rather than over the returned hits so the
 * `limit` cap cannot hide a section whose matches all rank low overall.
 */
describe('searchLibrary — section narrowing', () => {
  const SECTIONS = ['LR', 'RC', 'LG', 'WS'] as const

  it('returns only articles tagged with the requested section', () => {
    const all = searchLibrary('argument', 100)
    expect(all.length).toBeGreaterThan(1)

    for (const code of SECTIONS) {
      const narrowed = searchLibrary('argument', 100, code)
      expect(
        narrowed.every((h) => h.sections.includes(code)),
        `${code} hits: ${narrowed.map((h) => h.id).join(', ')}`,
      ).toBe(true)
      // …and nothing tagged with it is dropped: narrowing is a filter over the
      // same ranking, not a different search.
      expect(narrowed.map((h) => h.id), code).toEqual(
        all.filter((h) => h.sections.includes(code)).map((h) => h.id),
      )
    }
  })

  it('leaves the unnarrowed ranking byte-for-byte unchanged', () => {
    // The backend parity fixture above pins the default path; this asserts the
    // new parameter cannot perturb it.
    expect(searchLibrary('assumptions', 5, 'all')).toEqual(searchLibrary('assumptions', 5))
  })

  it('applies the limit after the section filter, not before', () => {
    const wide = searchLibrary('argument', 100)
    const firstRc = wide.findIndex((h) => h.sections.includes('RC'))
    // Precondition, asserted rather than assumed: RC must not already be the
    // top hit, or this test proves nothing.
    expect(firstRc, 'expected an RC match ranked below the top of "argument"')
      .toBeGreaterThan(0)

    // Capping first and filtering after would slice RC away entirely here.
    const narrowed = searchLibrary('argument', firstRc, 'RC')
    expect(narrowed.length).toBeGreaterThan(0)
    expect(narrowed[0]?.id).toBe(wide[firstRc]?.id)
  })

  it('narrows to nothing rather than falling back to the whole corpus', () => {
    // A query with no match in the section is an empty result, not a silently
    // unfiltered one — the failure mode this issue was filed about.
    const ws = searchLibrary('contrapositive', 100, 'WS')
    expect(ws.every((h) => h.sections.includes('WS'))).toBe(true)
  })
})
