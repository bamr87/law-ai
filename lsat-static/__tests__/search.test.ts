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

import { queryTokens, searchLibrary, stem } from '@/lib/search'

interface Parity {
  stems: Record<string, string>
  query_tokens: Record<string, string[]>
  corpus: { query: string; top?: string | null; ids?: string[] }[]
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
