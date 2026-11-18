/**
 * The page's destinations, and how the URL names them (#223).
 *
 * The destination used to live only in React state, so the address bar never
 * said where you were. A shared `#article-<id>` permalink opened Overview,
 * a reload reset to Overview, and Back left the site, because switching
 * destination added no history entry. The fragment is now the address: this
 * site has no client router and no server to route a path.
 *
 * `app/page.tsx` reads the fragment after mount and on `hashchange`, and
 * pushes a history entry when the reader picks a destination.
 */
import type { SectionCode } from '@/lib/types'

/** A top-level destination: one item each in the nav (`app/page.tsx` `NAV`). */
export type View = 'overview' | SectionCode | 'writing' | 'library' | 'stats'

/**
 * Fragment → destination. The table is written out rather than derived from
 * the view ids, because the section views are `LR` / `RC` / `LG` while their
 * fragments are lower-case. It is a Map so that a fragment such as
 * `#constructor` cannot find something on an object's prototype.
 */
const DESTINATIONS = new Map<string, View>([
  ['overview', 'overview'],
  ['lr', 'LR'],
  ['rc', 'RC'],
  ['lg', 'LG'],
  ['writing', 'writing'],
  ['library', 'library'],
  ['stats', 'stats'],
])

/**
 * The Library's own permalinks (BL-20260905-04). They open the Library, which
 * reads the rest of the fragment itself (`components/Library.tsx`
 * `hashTarget`) and keeps owning it while the reader is there.
 */
const LIBRARY_PREFIXES = ['article-', 'catalog-']

/**
 * The destination a URL fragment names, or `null` when it names none.
 *
 * Case-insensitive. No fragment at all is Overview: it is what the bare
 * address shows, and where Back lands when it returns to the first entry.
 * Any other fragment is not a destination (the skip link's `#view`, an
 * in-article `#concept-<id>` or heading anchor), so the caller must leave the
 * view alone rather than fall back to Overview.
 *
 * @example viewForHash('#lr') // 'LR'
 * @example viewForHash('#article-lsat-exam-architecture') // 'library'
 * @example viewForHash('') // 'overview'
 * @example viewForHash('#view') // null
 */
export function viewForHash(hash: string): View | null {
  const fragment = hash.replace(/^#/, '').toLowerCase()
  if (fragment === '') return 'overview'
  if (LIBRARY_PREFIXES.some((prefix) => fragment.startsWith(prefix))) return 'library'
  return DESTINATIONS.get(fragment) ?? null
}

/**
 * The fragment a destination is written as, `#lr` for `LR`. For every
 * destination in the nav, `viewForHash(hashForView(view))` is `view`.
 *
 * @example hashForView('LR') // '#lr'
 */
export function hashForView(view: View): string {
  return `#${view.toLowerCase()}`
}
