/**
 * The fragment scheme itself (#223, `lib/destinations.ts`).
 *
 * `hashRouting.test.tsx` drives the page. These pin the table: the section
 * views are upper-case while their fragments are not, so the mapping is
 * written out, and the writer and the reader have to agree on every entry.
 */
import { describe, expect, it } from 'vitest'

import { hashForView, viewForHash, type View } from '@/lib/destinations'

const DESTINATIONS: View[] = ['overview', 'LR', 'RC', 'LG', 'writing', 'library', 'stats']

describe('viewForHash', () => {
  it.each([
    ['#overview', 'overview'],
    ['#lr', 'LR'],
    ['#rc', 'RC'],
    ['#lg', 'LG'],
    ['#writing', 'writing'],
    ['#library', 'library'],
    ['#stats', 'stats'],
  ] as const)('reads %s as %s', (hash, view) => {
    expect(viewForHash(hash)).toBe(view)
  })

  it('ignores case', () => {
    expect(viewForHash('#LR')).toBe('LR')
    expect(viewForHash('#Writing')).toBe('writing')
    expect(viewForHash('#STATS')).toBe('stats')
  })

  it("sends the Library's permalinks to the Library", () => {
    expect(viewForHash('#article-lsat-exam-architecture')).toBe('library')
    expect(viewForHash('#catalog-necessary-assumption')).toBe('library')
  })

  it('reads no fragment as Overview, with or without the #', () => {
    expect(viewForHash('')).toBe('overview')
    expect(viewForHash('#')).toBe('overview')
  })

  it('names no destination for any other fragment', () => {
    for (const hash of ['#nope', '#view', '#concept-necessary-assumption', '#ws', '#articles']) {
      expect(viewForHash(hash)).toBeNull()
    }
  })

  it('finds nothing on the prototype of the table', () => {
    for (const hash of ['#constructor', '#__proto__', '#tostring', '#hasownproperty']) {
      expect(viewForHash(hash)).toBeNull()
    }
  })
})

describe('hashForView', () => {
  it('writes lower-case fragments', () => {
    expect(hashForView('LR')).toBe('#lr')
    expect(hashForView('stats')).toBe('#stats')
  })

  it.each(DESTINATIONS)('round-trips %s', (view) => {
    expect(viewForHash(hashForView(view))).toBe(view)
  })
})
