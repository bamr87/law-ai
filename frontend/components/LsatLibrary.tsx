'use client'

/**
 * LSAT Library — the module's one study surface (spec 048 FR-8).
 *
 * Two views of a single shelf. **Articles** is the long-form reader: a
 * contents rail (search, filters, tracks, article list), the article, and an
 * "on this page" outline. **Concepts** is the catalog of recurring reasoning
 * patterns that tags every article and every bank question.
 *
 * The catalog used to be a seventh tab over in the practice lab, which put
 * the vocabulary and the material that teaches it on opposite sides of the
 * app: an article named a concept and could only define it in a footnote,
 * and a concept named nothing at all. Merged, the round trip closes — an
 * article lists its concepts, and a concept lists both the articles that
 * teach it (`taught_in`, an inverse the API has always returned and no
 * surface rendered) and the bank questions that drill it. One rail, one
 * reader, one search box.
 *
 * Both entry types render through one template — header, actions, body,
 * cross-references, provenance, in a fixed order with fixed anchors — see
 * "The entry template" below. An article and a concept are different data
 * but the same kind of thing to a reader, and the page should say so.
 *
 * Below `xl` the outline folds into the reader; below `lg` the rail becomes a
 * disclosure so the reading column keeps a comfortable measure on a phone.
 *
 * The reader renders typed blocks only — see `library/BlockRenderer` — so
 * nothing on this page passes through `dangerouslySetInnerHTML`.
 */

import {
  fetchLsatArticle,
  fetchLsatConcept,
  fetchLsatConcepts,
  fetchLsatLibrary,
  fetchLsatTracks,
  searchLsatLibrary,
  type LsatArticleDetail,
  type LsatArticleKind,
  type LsatArticleSummary,
  type LsatConcept,
  type LsatConceptDetail,
  type LsatLibrarySearchHit,
  type LsatOutlineEntry,
  type LsatSectionCode,
  type LsatTrack,
} from '@/lib/api'
import BlockRenderer from '@/components/lsat/library/BlockRenderer'
import { StickyToolbar } from '@/components/shell/PageLayout'
import { useRovingTabIndex } from '@/components/shell/useRovingTabIndex'
import { useSetting } from '@/components/shell/useSetting'
import { libraryContents, libraryOutline } from '@/lib/settings/catalog'
import {
  KIND_LABEL,
  KIND_ORDER,
  LEVEL_LABEL,
  SECTION_LABEL,
  loadLastArticleId,
  loadReadIds,
  prefersReducedMotion,
  readingLabel,
  saveLastArticleId,
  saveReadIds,
} from '@/lib/lsat/library'
import Link from 'next/link'
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

type View = 'articles' | 'concepts'
type SectionFilter = 'all' | LsatSectionCode

const VIEWS: { id: View; label: string; hint: string }[] = [
  { id: 'articles', label: 'Articles', hint: 'Long-form reading on the exam' },
  {
    id: 'concepts',
    label: 'Concepts',
    hint: 'Catalog of the reasoning patterns the LSAT recycles',
  },
]

const SECTION_FILTERS: { id: SectionFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'LR', label: 'LR' },
  { id: 'RC', label: 'RC' },
  { id: 'LG', label: 'LG' },
  { id: 'WS', label: 'WS' },
]

/** WS is an essay: no concept in the catalog is tagged with it. */
const CONCEPT_SECTION_FILTERS = SECTION_FILTERS.filter((f) => f.id !== 'WS')

export const viewTabId = (v: View) => `library-tab-${v}`
export const viewPanelId = (v: View) => `library-panel-${v}`

/**
 * Read the deep-link target out of the URL fragment.
 *
 * `catalog-<id>`, not `concept-<id>`, for the catalog: `concept-<id>` already
 * names the glossary entry *inside* an article, and `BlockRenderer`'s concept
 * spans link to it. Reusing it would mean that following an inline definition
 * navigated away from the article you were reading, which is the opposite of
 * what a footnote is for.
 */
function hashTarget(): { view: View; id: string } | null {
  if (typeof window === 'undefined') return null
  const raw = window.location.hash.replace(/^#/, '')
  if (raw.startsWith('article-')) {
    return { view: 'articles', id: raw.slice('article-'.length) }
  }
  if (raw.startsWith('catalog-')) {
    return { view: 'concepts', id: raw.slice('catalog-'.length) }
  }
  return null
}

/** Concept text the rail's search box matches against. */
function conceptHaystack(c: LsatConcept): string {
  return [c.name, c.summary, c.detail ?? '', ...c.examples, ...c.see_also]
    .join(' ')
    .toLowerCase()
}

export default function LsatLibrary() {
  const [view, setView] = useState<View>('articles')

  const [index, setIndex] = useState<LsatArticleSummary[] | null>(null)
  const [tracks, setTracks] = useState<LsatTrack[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<LsatArticleDetail | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [concepts, setConcepts] = useState<LsatConcept[] | null>(null)
  const [conceptError, setConceptError] = useState<string | null>(null)
  const [conceptId, setConceptId] = useState<string | null>(null)
  // Tagged with the id it belongs to rather than cleared on every change:
  // "stale" is then a comparison at render time instead of a synchronous
  // setState in the fetch effect, and the previous concept's cross-links can
  // never flash under the new concept's name.
  const [conceptDetail, setConceptDetail] = useState<{
    id: string
    data: LsatConceptDetail
  } | null>(null)

  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<LsatLibrarySearchHit[] | null>(null)
  const [sectionFilter, setSectionFilter] = useState<SectionFilter>('all')
  const [trackFilter, setTrackFilter] = useState<string>('')
  const [railOpen, setRailOpen] = useState(false)
  const [contentsShown] = useSetting(libraryContents)
  const [outlineShown] = useSetting(libraryOutline)

  const [readIds, setReadIds] = useState<Set<string>>(new Set())
  const readerRef = useRef<HTMLDivElement | null>(null)

  // --- initial load -------------------------------------------------------

  useEffect(() => {
    let live = true
    // Read here, applied in the callback below. The fragment cannot be read
    // during render — the server has no `window`, and a first paint that
    // disagreed with it would be a hydration mismatch — and applying it
    // synchronously in the effect body is the cascading-render pattern the
    // rest of this file already avoids.
    const target = hashTarget()
    Promise.all([fetchLsatLibrary(), fetchLsatTracks()])
      .then(([lib, tr]) => {
        if (!live) return
        setIndex(lib.articles)
        setTracks(tr.tracks)
        if (target?.view === 'concepts') {
          setView('concepts')
          setConceptId(target.id)
        }
        // Deep link wins over the remembered article, which wins over the
        // head of the first curated track. Not `articles[0]`: the index is
        // sorted by id, so the alphabetical default would open a technique
        // note to a reader who has not yet been told what the exam is.
        const landing =
          tr.tracks[0]?.article_ids[0] ?? lib.articles[0]?.id ?? null
        const wanted =
          (target?.view === 'articles' ? target.id : null) ??
          loadLastArticleId() ??
          landing
        setSelectedId(
          wanted && lib.articles.some((a) => a.id === wanted) ? wanted : landing,
        )
      })
      .catch(() => {
        if (live) setLoadError('Could not reach the library API.')
      })
    setReadIds(loadReadIds())
    return () => {
      live = false
    }
  }, [])

  // --- article fetch ------------------------------------------------------

  useEffect(() => {
    if (!selectedId) return
    let live = true
    setDetail(null)
    fetchLsatArticle(selectedId)
      .then((d) => {
        if (!live) return
        setDetail(d)
        saveLastArticleId(selectedId)
      })
      .catch(() => {
        if (live) setLoadError(`Could not load article "${selectedId}".`)
      })
    return () => {
      live = false
    }
  }, [selectedId])

  // --- concept catalog ----------------------------------------------------

  // Lazily: articles are the landing view, and a reader who never opens the
  // catalog should not pay for it. Once loaded it stays loaded — the whole
  // catalog is one small response and every view of it filters client-side.
  useEffect(() => {
    if (view !== 'concepts' || concepts) return
    let live = true
    fetchLsatConcepts()
      .then((body) => {
        if (!live) return
        setConcepts(body.concepts)
        setConceptId((current) =>
          current && body.concepts.some((c) => c.id === current)
            ? current
            : (body.concepts[0]?.id ?? null),
        )
      })
      .catch(() => {
        if (live) setConceptError('Could not reach the concept catalog.')
      })
    return () => {
      live = false
    }
  }, [view, concepts])

  // The catalog list already carries every field the reader renders; this
  // second call only adds the two inverses (`taught_in`, `used_in_questions`),
  // so the reader paints immediately and the cross-links fill in behind it.
  useEffect(() => {
    if (!conceptId) return
    let live = true
    fetchLsatConcept(conceptId)
      .then((d) => {
        if (live) setConceptDetail({ id: conceptId, data: d })
      })
      .catch(() => {
        /* Cross-links are an enrichment; the concept itself still reads. */
      })
    return () => {
      live = false
    }
  }, [conceptId])

  // --- deep link ----------------------------------------------------------

  useEffect(() => {
    const id = view === 'articles' ? selectedId : conceptId
    if (!id) return
    const prefix = view === 'articles' ? 'article-' : 'catalog-'
    window.history.replaceState(null, '', `#${prefix}${id}`)
  }, [view, selectedId, conceptId])

  // --- search (debounced) -------------------------------------------------

  // Articles only. Concepts are already in memory, so filtering them through a
  // network round trip would be slower and would drop the match-as-you-type.
  useEffect(() => {
    const q = query.trim()
    if (view !== 'articles' || q.length < 2) {
      setHits(null)
      return
    }
    let live = true
    const handle = window.setTimeout(() => {
      searchLsatLibrary(q)
        .then((r) => {
          if (live) setHits(r.results)
        })
        .catch(() => {
          if (live) setHits([])
        })
    }, 180)
    return () => {
      live = false
      window.clearTimeout(handle)
    }
  }, [query, view])

  // --- navigation ---------------------------------------------------------

  const scrollToReader = useCallback(() => {
    // Optional call, not just optional chaining: `scrollIntoView` is absent
    // in jsdom and in any non-browser render, and moving the viewport is a
    // convenience that must never be the thing that throws.
    readerRef.current?.scrollIntoView?.({
      block: 'start',
      behavior: prefersReducedMotion() ? 'auto' : 'smooth',
    })
  }, [])

  const openArticle = useCallback(
    (id: string) => {
      setView('articles')
      setSelectedId(id)
      setRailOpen(false)
      scrollToReader()
    },
    [scrollToReader],
  )

  const openConcept = useCallback(
    (id: string) => {
      setView('concepts')
      setConceptId(id)
      setRailOpen(false)
      scrollToReader()
    },
    [scrollToReader],
  )

  const changeView = useCallback((next: View) => {
    setView(next)
    setQuery('')
    // WS is an article-only filter; carrying it into the catalog would open
    // the concepts view on an empty list with no obvious cause.
    if (next === 'concepts') setSectionFilter((s) => (s === 'WS' ? 'all' : s))
  }, [])

  const toggleRead = useCallback((key: string) => {
    setReadIds((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      saveReadIds(next)
      return next
    })
  }, [])

  // A track chip on either entry type: switch to the reader with that track
  // as the rail's curriculum, and land on its first article unless the one
  // already open is part of it.
  const openTrack = useCallback(
    (id: string) => {
      const track = tracks.find((t) => t.id === id)
      if (!track) return
      setTrackFilter(id)
      setView('articles')
      setQuery('')
      setSelectedId((current) =>
        current && track.article_ids.includes(current)
          ? current
          : (track.article_ids[0] ?? current),
      )
      setRailOpen(false)
      scrollToReader()
    },
    [tracks, scrollToReader],
  )

  // --- derived ------------------------------------------------------------

  const activeTrack = tracks.find((t) => t.id === trackFilter) ?? null

  const visible = useMemo(() => {
    if (!index) return []
    let rows = index
    if (sectionFilter !== 'all') {
      rows = rows.filter((a) => a.sections.includes(sectionFilter))
    }
    if (activeTrack) {
      const order = new Map(activeTrack.article_ids.map((id, i) => [id, i]))
      rows = rows.filter((a) => order.has(a.id))
      // A track's order *is* the curriculum, so it overrides kind grouping.
      return [...rows].sort((a, b) => order.get(a.id)! - order.get(b.id)!)
    }
    return rows
  }, [index, sectionFilter, activeTrack])

  const grouped = useMemo(() => {
    if (activeTrack) return null
    const buckets = new Map<LsatArticleKind, LsatArticleSummary[]>()
    for (const article of visible) {
      const bucket = buckets.get(article.kind) ?? []
      bucket.push(article)
      buckets.set(article.kind, bucket)
    }
    return KIND_ORDER.filter((k) => buckets.has(k)).map((kind) => ({
      kind,
      articles: buckets.get(kind)!,
    }))
  }, [visible, activeTrack])

  const visibleConcepts = useMemo(() => {
    if (!concepts) return []
    const needle = query.trim().toLowerCase()
    return concepts.filter(
      (c) =>
        (sectionFilter === 'all' ||
          (c.sections as string[]).includes(sectionFilter)) &&
        (!needle || conceptHaystack(c).includes(needle)),
    )
  }, [concepts, query, sectionFilter])

  const conceptGroups = useMemo(() => {
    const buckets = new Map<LsatSectionCode | 'misc', LsatConcept[]>()
    for (const c of visibleConcepts) {
      const key = c.sections[0] ?? 'misc'
      buckets.set(key, [...(buckets.get(key) ?? []), c])
    }
    return [...buckets.entries()]
  }, [visibleConcepts])

  const catalog = useMemo(
    () => new Map((concepts ?? []).map((c) => [c.id, c])),
    [concepts],
  )

  const activeConceptDetail =
    conceptDetail && conceptDetail.id === conceptId ? conceptDetail.data : null

  const selectedConcept =
    (conceptId ? catalog.get(conceptId) : undefined) ??
    activeConceptDetail?.concept ??
    null

  // Read progress is per view. The one set holds both kinds of key, so the
  // count has to be taken against each list rather than off the set's size.
  const articleReadCount = useMemo(
    () => (index ?? []).filter((a) => readIds.has(readKey('articles', a.id))).length,
    [index, readIds],
  )
  const conceptReadCount = useMemo(
    () =>
      (concepts ?? []).filter((c) => readIds.has(readKey('concepts', c.id)))
        .length,
    [concepts, readIds],
  )

  // Concept id → indexed articles tagged with it. The rail's second line,
  // and the tag half of what `taught_in` reports (the API also counts inline
  // references, which the index cannot see).
  const taughtBy = useMemo(() => {
    const counts = new Map<string, number>()
    for (const a of index ?? []) {
      for (const c of a.concepts) counts.set(c, (counts.get(c) ?? 0) + 1)
    }
    return counts
  }, [index])

  // The outline lists the body's own headings plus whichever template
  // sections rendered, so the third column reads the same on both views.
  const outline = useMemo<LsatOutlineEntry[]>(() => {
    if (view === 'articles') {
      return detail
        ? entryOutline(detail.article.outline, articleSections(detail, tracks))
        : []
    }
    return selectedConcept
      ? entryOutline(
          [],
          conceptSections(
            selectedConcept,
            activeConceptDetail,
            index,
            catalog,
            tracks,
          ),
        )
      : []
  }, [
    view,
    detail,
    tracks,
    selectedConcept,
    activeConceptDetail,
    index,
    catalog,
  ])

  if (loadError && !index) {
    return (
      <div className="rounded-lg border border-rose-900/60 bg-rose-950/30 p-6 text-sm text-rose-200">
        {loadError} The library is served from{' '}
        <code className="rounded bg-slate-900 px-1.5 py-0.5 text-xs">
          /api/lsat/library
        </code>
        ; check that the backend is running.
      </div>
    )
  }

  // The same three columns on both views — rail, entry, outline — so
  // switching between an article and a concept moves nothing but the words.
  //
  // Container queries, not viewport breakpoints: with the sidebar and the
  // inspector docked the shell leaves this region ~850px wide on a 1440px
  // screen, and a viewport `xl:` rule would still deal out three columns and
  // leave the prose ~230px. The root below is the container, so the columns
  // follow the width that is actually there — one column under 48rem, the
  // rail from 48rem, the outline from 72rem, and wider gutters from 96rem.
  //
  // Both side columns are preferences (spec 051, `lsat.library.contents` and
  // `lsat.library.outline`). The grid is picked from the four combinations
  // rather than composed, because Tailwind only ships classes it can read.
  const grid = libraryGrid(contentsShown, outlineShown)

  const railCount =
    view === 'articles' ? (index?.length ?? 0) : (concepts?.length ?? 0)
  const railNoun = view === 'articles' ? 'articles' : 'concepts'

  return (
    <div className="@container space-y-4">
      <ViewTabs view={view} onChange={changeView} />

      <div
        role="tabpanel"
        id={viewPanelId(view)}
        aria-labelledby={viewTabId(view)}
        tabIndex={0}
        className={
          grid +
          ' focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400'
        }
      >
        {/* ---------------------------------------------------------- rail */}
        {/* With the rail hidden by preference, the narrow-width disclosure
            serves every width and both it and the rail span the whole row,
            so an opened rail sits above the reader rather than in a column
            the grid no longer has. */}
        <button
          type="button"
          onClick={() => setRailOpen((v) => !v)}
          aria-expanded={railOpen}
          className={
            'mb-4 w-full rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-2 text-left text-sm text-slate-300 ' +
            (contentsShown ? '@min-[48rem]:hidden' : 'col-span-full')
          }
        >
          {railOpen ? 'Hide' : 'Browse'} contents · {railCount} {railNoun}
        </button>

        <nav
          aria-label="Library contents"
          className={
            `${railOpen ? 'block' : 'hidden'} shell-sticky-aside shell-panel-scroll max-h-[calc(100dvh-var(--shell-masthead-h)-var(--shell-pageheader-h)-var(--shell-toolbar-h)-3rem)] mb-6 ` +
            (contentsShown
              ? '@min-[48rem]:mb-0 @min-[48rem]:block @min-[48rem]:pr-2'
              : 'col-span-full')
          }
        >
          <label className="block">
            <span className="sr-only">
              {view === 'articles' ? 'Search the library' : 'Search concepts'}
            </span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={
                view === 'articles' ? 'Search articles…' : 'Search concepts…'
              }
              className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-amber-500 focus-ring-practice"
            />
          </label>

          <div className="mt-3 flex flex-wrap gap-1">
            {(view === 'articles'
              ? SECTION_FILTERS
              : CONCEPT_SECTION_FILTERS
            ).map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setSectionFilter(f.id)}
                aria-pressed={sectionFilter === f.id}
                className={
                  'rounded-full px-2.5 py-1 text-[11px] font-medium transition ' +
                  (sectionFilter === f.id
                    ? 'bg-amber-500/20 text-amber-200 ring-1 ring-inset ring-amber-500/40'
                    : 'bg-slate-800/60 text-slate-400 hover:text-slate-200')
                }
              >
                {f.label}
              </button>
            ))}
          </div>

          {view === 'articles' ? (
            <ArticleRail
              activeTrack={activeTrack}
              grouped={grouped}
              hits={hits}
              index={index}
              onOpen={openArticle}
              onTrackChange={setTrackFilter}
              query={query}
              readCount={articleReadCount}
              readIds={readIds}
              selectedId={selectedId}
              trackFilter={trackFilter}
              tracks={tracks}
              visible={visible}
            />
          ) : (
            <ConceptRail
              error={conceptError}
              groups={conceptGroups}
              loaded={concepts !== null}
              onOpen={openConcept}
              query={query}
              readCount={conceptReadCount}
              readIds={readIds}
              selectedId={conceptId}
              taughtBy={taughtBy}
              total={concepts?.length ?? 0}
            />
          )}
        </nav>

        {/* -------------------------------------------------------- reader */}
        <div ref={readerRef} className="min-w-0 scroll-mt-24">
          {view === 'articles' ? (
            <ArticleReader
              detail={detail}
              onOpenArticle={openArticle}
              onOpenConcept={openConcept}
              onOpenTrack={openTrack}
              onToggleRead={() =>
                selectedId && toggleRead(readKey('articles', selectedId))
              }
              read={
                selectedId ? readIds.has(readKey('articles', selectedId)) : false
              }
              tracks={tracks}
            />
          ) : (
            <ConceptReader
              catalog={catalog}
              concept={selectedConcept}
              detail={activeConceptDetail}
              error={conceptError}
              index={index}
              onOpenArticle={openArticle}
              onOpenConcept={openConcept}
              onOpenTrack={openTrack}
              onToggleRead={() =>
                conceptId && toggleRead(readKey('concepts', conceptId))
              }
              read={
                conceptId ? readIds.has(readKey('concepts', conceptId)) : false
              }
              tracks={tracks}
            />
          )}
        </div>

        {/* ------------------------------------------------------- outline */}
        {outlineShown && <OutlineNav outline={outline} />}
      </div>
    </div>
  )
}

/**
 * The library's column grid, by which side columns are shown. Container
 * queries, not viewport ones (see the note at the call site); every class is
 * spelled out so Tailwind can see it.
 */
function libraryGrid(contents: boolean, outline: boolean): string {
  if (contents && outline) {
    return '@min-[48rem]:grid @min-[48rem]:grid-cols-[17rem_minmax(0,1fr)] @min-[48rem]:gap-8 @min-[72rem]:grid-cols-[17rem_minmax(0,1fr)_15rem] @min-[96rem]:grid-cols-[20rem_minmax(0,1fr)_18rem] @min-[96rem]:gap-12'
  }
  if (contents) {
    return '@min-[48rem]:grid @min-[48rem]:grid-cols-[17rem_minmax(0,1fr)] @min-[48rem]:gap-8 @min-[96rem]:grid-cols-[20rem_minmax(0,1fr)] @min-[96rem]:gap-12'
  }
  if (outline) {
    return '@min-[72rem]:grid @min-[72rem]:grid-cols-[minmax(0,1fr)_15rem] @min-[72rem]:gap-8 @min-[96rem]:grid-cols-[minmax(0,1fr)_18rem] @min-[96rem]:gap-12'
  }
  return ''
}

// ---------------------------------------------------------------------------
// View switcher
// ---------------------------------------------------------------------------

function ViewTabs({
  view,
  onChange,
}: {
  view: View
  onChange: (v: View) => void
}) {
  // One tab stop, arrows move within it (WAI-ARIA tabs pattern) — the same
  // switcher contract the practice lab's section bar uses.
  const roving = useRovingTabIndex({
    count: VIEWS.length,
    activeIndex: VIEWS.findIndex((v) => v.id === view),
    onActivate: (i) => onChange(VIEWS[i].id),
  })

  return (
    <StickyToolbar>
      <div role="tablist" aria-label="Library views" className="flex gap-1">
        {VIEWS.map((v, i) => {
          const active = v.id === view
          return (
            <button
              key={v.id}
              {...roving.itemProps(i)}
              id={viewTabId(v.id)}
              role="tab"
              aria-selected={active}
              aria-controls={viewPanelId(v.id)}
              title={v.hint}
              onClick={() => onChange(v.id)}
              className={
                'min-w-[8rem] rounded-lg px-4 py-2 text-sm font-medium transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 ' +
                (active
                  ? 'bg-amber-500/20 text-amber-100 ring-1 ring-inset ring-amber-500/40'
                  : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200')
              }
            >
              {v.label}
            </button>
          )
        })}
      </div>
    </StickyToolbar>
  )
}

// ---------------------------------------------------------------------------
// Rails
// ---------------------------------------------------------------------------

/**
 * One row shape for both rails: a read-state dot, the title, and one line of
 * metadata underneath. Articles put their reading time there; concepts, the
 * number of articles that teach them. Whatever the second line says, the eye
 * learns one row and reads both lists.
 */
function RailRow({
  meta,
  onClick,
  read,
  selected,
  title,
}: {
  meta: string
  onClick: () => void
  read: boolean
  selected: boolean
  title: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={selected ? 'true' : undefined}
      className={
        'flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm transition ' +
        (selected
          ? 'bg-amber-500/15 text-amber-100'
          : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200')
      }
    >
      <span
        aria-hidden="true"
        className={
          'mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ' +
          (read ? 'bg-emerald-400' : 'bg-slate-700')
        }
      />
      <span className="min-w-0">
        <span className="block truncate">{title}</span>
        <span className="text-[10px] text-slate-600">{meta}</span>
      </span>
    </button>
  )
}

/** "3 of 35 read · 9%" — the same progress line under both rails. */
function RailProgress({ read, total }: { read: number; total: number }) {
  const pct = total ? Math.round((read / total) * 100) : 0
  return (
    <div className="mt-3 text-[11px] text-slate-500">
      {read} of {total} read · {pct}%
    </div>
  )
}

function ArticleRail({
  activeTrack,
  grouped,
  hits,
  index,
  onOpen,
  onTrackChange,
  query,
  readCount,
  readIds,
  selectedId,
  trackFilter,
  tracks,
  visible,
}: {
  activeTrack: LsatTrack | null
  grouped: { kind: LsatArticleKind; articles: LsatArticleSummary[] }[] | null
  hits: LsatLibrarySearchHit[] | null
  index: LsatArticleSummary[] | null
  onOpen: (id: string) => void
  onTrackChange: (id: string) => void
  query: string
  readCount: number
  readIds: Set<string>
  selectedId: string | null
  trackFilter: string
  tracks: LsatTrack[]
  visible: LsatArticleSummary[]
}) {
  return (
    <>
      <label className="mt-3 block">
        <span className="text-[11px] uppercase tracking-wider text-slate-500">
          Reading track
        </span>
        <select
          value={trackFilter}
          onChange={(e) => onTrackChange(e.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950 px-2 py-1.5 text-sm text-slate-200 focus:border-amber-500 focus-ring-practice"
        >
          <option value="">All articles</option>
          {tracks.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} · {t.estimated_minutes} min
            </option>
          ))}
        </select>
      </label>

      {activeTrack && (
        <p className="mt-2 rounded-lg border border-slate-800 bg-slate-900/50 p-2 text-xs leading-relaxed text-slate-400">
          {activeTrack.goal}
        </p>
      )}

      <RailProgress read={readCount} total={index?.length ?? 0} />

      {hits ? (
        <div className="mt-4">
          <div className="text-[11px] uppercase tracking-wider text-slate-500">
            {hits.length} result{hits.length === 1 ? '' : 's'}
          </div>
          <ul className="mt-2 space-y-2">
            {hits.map((hit) => (
              <li key={hit.id}>
                <button
                  type="button"
                  onClick={() => onOpen(hit.id)}
                  className="w-full rounded-lg border border-slate-800 bg-slate-900/40 p-2 text-left hover:border-amber-500/40"
                >
                  <div className="text-sm font-medium text-slate-200">
                    {hit.title}
                  </div>
                  <div className="mt-1 line-clamp-3 text-xs leading-relaxed text-slate-500">
                    {hit.snippet}
                  </div>
                  <div className="mt-1 text-[10px] uppercase tracking-wider text-slate-600">
                    matched in {hit.matched_in.join(', ')}
                  </div>
                </button>
              </li>
            ))}
            {hits.length === 0 && (
              <li className="text-xs text-slate-500">
                Nothing matched “{query.trim()}”.
              </li>
            )}
          </ul>
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          {(grouped ?? [{ kind: null, articles: visible }]).map((group) => (
            <div key={group.kind ?? 'track'}>
              {group.kind && (
                <div className="text-[11px] uppercase tracking-wider text-slate-500">
                  {KIND_LABEL[group.kind]}
                </div>
              )}
              <ul className="mt-1.5 space-y-0.5">
                {group.articles.map((article) => (
                  <li key={article.id}>
                    <RailRow
                      title={article.title}
                      meta={readingLabel(article.reading_minutes)}
                      read={readIds.has(article.id)}
                      selected={article.id === selectedId}
                      onClick={() => onOpen(article.id)}
                    />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

function ConceptRail({
  error,
  groups,
  loaded,
  onOpen,
  query,
  readCount,
  readIds,
  selectedId,
  taughtBy,
  total,
}: {
  error: string | null
  groups: [LsatSectionCode | 'misc', LsatConcept[]][]
  loaded: boolean
  onOpen: (id: string) => void
  query: string
  readCount: number
  readIds: Set<string>
  selectedId: string | null
  /** Concept id → how many indexed articles tag it. */
  taughtBy: Map<string, number>
  total: number
}) {
  const shown = groups.reduce((n, [, items]) => n + items.length, 0)

  return (
    <>
      <div className="mt-3 text-[11px] uppercase tracking-wider text-slate-500">
        {shown === total
          ? `${total} concept${total === 1 ? '' : 's'}`
          : `${shown} of ${total} concepts`}
      </div>

      <RailProgress read={readCount} total={total} />

      {error && (
        <p className="mt-4 rounded-lg border border-rose-900/60 bg-rose-950/30 p-3 text-xs text-rose-200">
          {error}
        </p>
      )}
      {!loaded && !error && (
        <p className="mt-4 text-xs text-slate-500">Loading concepts…</p>
      )}
      {loaded && shown === 0 && (
        <p className="mt-4 text-xs text-slate-500">
          {query.trim()
            ? `Nothing matched “${query.trim()}”.`
            : 'No concepts match this filter.'}
        </p>
      )}

      <div className="mt-4 space-y-4">
        {groups.map(([section, items]) => (
          <div key={section}>
            <div className="text-[11px] uppercase tracking-wider text-slate-500">
              {section === 'misc' ? 'Cross-section' : SECTION_LABEL[section]}
            </div>
            <ul className="mt-1.5 space-y-0.5">
              {items.map((concept) => (
                <li key={concept.id}>
                  <RailRow
                    title={concept.name}
                    meta={articlesLabel(taughtBy.get(concept.id) ?? 0)}
                    read={readIds.has(readKey('concepts', concept.id))}
                    selected={concept.id === selectedId}
                    onClick={() => onOpen(concept.id)}
                  />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// The entry template
// ---------------------------------------------------------------------------
//
// An article and a concept are different data but the same *kind of thing* to
// a reader: an entry on a shelf, with a header, something to do with it, a
// body, and the things it connects to. So both readers are assembled from the
// same parts in the same order, and every section carries a fixed anchor so
// the outline column can list it whichever view is open:
//
//   header       type pill · badges · stats · sections; title; summary; chips
//   actions      Mark as read · Drill this (N questions)
//   read first   articles: prerequisites
//   body         articles: the typed blocks · concepts: the detail
//   examples     concepts: schema & examples             #entry-examples
//   concepts     Concepts in this article                #entry-concepts
//   articles     Articles on this concept                #entry-articles
//   related      Related                                 #entry-related
//   tracks       Reading tracks                          #entry-tracks
//   references   References                              #entry-references
//   provenance   source · revision · reviewed · status | catalog · sections
//
// A section that has nothing to show is omitted, not rendered empty — except
// the one cross-reference a learner arrives needing ("Articles on this
// concept"), which says so in words when the corpus has not caught up.

/**
 * The prose measure, widened a little where the page frame widens too. The
 * entry is also a query container, so its card grids can go two-up on the
 * width the column really has rather than on a viewport guess.
 */
const MEASURE = '@container max-w-[68ch] min-[1800px]:max-w-[76ch]'

/** Fixed anchors for the template's sections, shared with the outline. */
const ENTRY_ANCHOR = {
  examples: 'entry-examples',
  concepts: 'entry-concepts',
  articles: 'entry-articles',
  related: 'entry-related',
  tracks: 'entry-tracks',
  references: 'entry-references',
} as const

type EntryAnchor = (typeof ENTRY_ANCHOR)[keyof typeof ENTRY_ANCHOR]

/** Something an entry points at: an article or a concept, as a card. */
interface RefItem {
  id: string
  title: string
  summary: string
  meta?: string
}

/**
 * Read-state key. Articles keep their bare id — that is what every existing
 * `localStorage` entry holds — and concepts get a prefix, so the one set
 * covers both without a migration and without an article and a concept that
 * happen to share an id colliding.
 */
export function readKey(view: View, id: string): string {
  return view === 'concepts' ? `concept:${id}` : id
}

function articlesLabel(n: number): string {
  return n === 1 ? 'taught in 1 article' : `taught in ${n} articles`
}

function EntryHeader({
  badges,
  chips,
  pill,
  sections,
  summary,
  title,
}: {
  /** Secondary facts after the pill: level, reading time, example count. */
  badges: string[]
  /** Tags, archetypes — the entry's vocabulary, rendered as chips. */
  chips?: { label: string; mono?: boolean }[]
  pill: string
  sections: LsatSectionCode[]
  summary: string
  title: string
}) {
  return (
    <header>
      <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wider text-slate-500">
        <span className="rounded-full bg-slate-800 px-2 py-0.5 text-slate-300">
          {pill}
        </span>
        {badges.map((b, i) => (
          <span key={b} className="contents">
            {i > 0 && <span aria-hidden="true">·</span>}
            <span>{b}</span>
          </span>
        ))}
        {sections.map((s) => (
          <span key={s} className="text-amber-400/80">
            {SECTION_LABEL[s]}
          </span>
        ))}
      </div>

      <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-100">
        {title}
      </h2>
      <p className="mt-2 leading-7 text-slate-400">{summary}</p>

      {chips && chips.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Tags">
          {chips.map((c) => (
            <li
              key={c.label}
              className={
                'rounded-full bg-slate-900/70 px-2.5 py-0.5 text-[11px] text-slate-400 ring-1 ring-inset ring-slate-800 ' +
                (c.mono ? 'font-mono' : '')
              }
            >
              {c.label}
            </li>
          ))}
        </ul>
      )}
    </header>
  )
}

function EntryActions({
  drillCount,
  drillCapped = false,
  onToggleRead,
  read,
}: {
  /** Bank questions this entry leads to; undefined while still loading. */
  drillCount?: number
  /** The API caps `used_in_questions` at 10, so 10 means "at least 10". */
  drillCapped?: boolean
  onToggleRead: () => void
  read: boolean
}) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3">
      <button
        type="button"
        onClick={onToggleRead}
        className={
          'rounded-lg px-3 py-1.5 text-xs font-medium transition ' +
          (read
            ? 'bg-emerald-500/15 text-emerald-200 ring-1 ring-inset ring-emerald-500/30'
            : 'bg-slate-800 text-slate-300 hover:bg-slate-700')
        }
      >
        {read ? '✓ Read' : 'Mark as read'}
      </button>
      {drillCount !== undefined && drillCount > 0 && (
        <Link
          href="/lsat"
          className="rounded-lg bg-amber-500/15 px-3 py-1.5 text-xs font-medium text-amber-200 ring-1 ring-inset ring-amber-500/30 hover:bg-amber-500/25"
        >
          Drill this ({drillCapped ? `${drillCount}+` : drillCount}{' '}
          question{drillCount === 1 && !drillCapped ? '' : 's'})
        </Link>
      )}
    </div>
  )
}

/** A titled, anchored block of the template. Same rule for every section. */
function EntrySection({
  children,
  id,
  subtitle,
  title,
}: {
  children: ReactNode
  id: EntryAnchor
  subtitle?: string
  title: string
}) {
  return (
    <section id={id} className="mt-10 scroll-mt-24 border-t border-slate-800 pt-6">
      <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
      {subtitle && (
        <p className="mt-0.5 text-[11px] uppercase tracking-wider text-slate-500">
          {subtitle}
        </p>
      )}
      {children}
    </section>
  )
}

/**
 * Cross-reference cards. One component in both directions — an article's
 * concepts and a concept's articles look the same and open the same way.
 * `anchorPrefix` gives each card an id, which is how an article's concept
 * cards stay the landing spot for the inline `#concept-<id>` references.
 */
function RefCards({
  anchorPrefix,
  items,
  onOpen,
}: {
  anchorPrefix?: string
  items: RefItem[]
  onOpen: (id: string) => void
}) {
  return (
    <ul className="mt-3 grid gap-2 @2xl:grid-cols-2">
      {items.map((item) => (
        <li
          key={item.id}
          id={anchorPrefix ? `${anchorPrefix}${item.id}` : undefined}
          className="scroll-mt-24"
        >
          <button
            type="button"
            onClick={() => onOpen(item.id)}
            className="h-full w-full rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-left hover:border-amber-500/40"
          >
            <span className="block text-sm font-medium text-slate-200">
              {item.title}
            </span>
            <span className="mt-1 block text-xs leading-relaxed text-slate-500">
              {item.summary}
            </span>
            {item.meta && (
              <span className="mt-2 block text-[10px] uppercase tracking-wider text-slate-600">
                {item.meta}
              </span>
            )}
          </button>
        </li>
      ))}
    </ul>
  )
}

/** External references, identically on both entry types. */
function RefLinks({
  refs,
}: {
  refs: { title: string; url?: string | null }[]
}) {
  return (
    <ul className="mt-2 space-y-1 text-sm">
      {refs.map((r) => (
        <li key={r.title}>
          {r.url ? (
            <a
              href={r.url}
              target="_blank"
              rel="noreferrer"
              className="text-sky-300 underline underline-offset-2 hover:text-sky-200"
            >
              {r.title}
            </a>
          ) : (
            <span className="text-slate-400">{r.title}</span>
          )}
        </li>
      ))}
    </ul>
  )
}

/** The curated reading tracks an entry belongs to, each one click to open. */
function TrackChips({
  onOpen,
  tracks,
}: {
  onOpen: (id: string) => void
  tracks: LsatTrack[]
}) {
  return (
    <ul className="mt-3 flex flex-wrap gap-2">
      {tracks.map((t) => (
        <li key={t.id}>
          <button
            type="button"
            onClick={() => onOpen(t.id)}
            className="rounded-full bg-slate-800/60 px-3 py-1 text-xs text-slate-300 transition hover:bg-slate-700 hover:text-slate-100"
          >
            {t.name}
            <span className="text-slate-500">
              {' '}
              · {t.article_count} articles · {t.estimated_minutes} min
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function Provenance({ parts }: { parts: string[] }) {
  return (
    <p className="mt-10 border-t border-slate-800 pt-4 text-xs text-slate-600">
      {[...parts, 'study aid for LSAT preparation, not legal advice'].join(
        ' · ',
      )}
      .
    </p>
  )
}

/**
 * The outline column's entries for an entry: the body's own headings (an
 * article's, from the API) followed by whichever template sections rendered,
 * in template order — so the outline reads the same way on both views.
 */
function entryOutline(
  body: LsatOutlineEntry[],
  present: { anchor: EntryAnchor; text: string }[],
): LsatOutlineEntry[] {
  return [
    ...body,
    ...present.map((p) => ({ level: 2, text: p.text, anchor: p.anchor })),
  ]
}

// ---------------------------------------------------------------------------
// Readers
// ---------------------------------------------------------------------------

function ArticleReader({
  detail,
  onOpenArticle,
  onOpenConcept,
  onOpenTrack,
  onToggleRead,
  read,
  tracks,
}: {
  detail: LsatArticleDetail | null
  onOpenArticle: (id: string) => void
  onOpenConcept: (id: string) => void
  onOpenTrack: (id: string) => void
  onToggleRead: () => void
  read: boolean
  tracks: LsatTrack[]
}) {
  if (!detail) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-8 text-sm text-slate-500">
        Loading article…
      </div>
    )
  }

  const { article } = detail
  const byId = new Map(tracks.map((t) => [t.id, t]))
  const inTracks = detail.tracks
    .map((t) => byId.get(t.id))
    .filter((t): t is LsatTrack => Boolean(t))

  return (
    <article className={MEASURE}>
      <EntryHeader
        pill={KIND_LABEL[article.kind]}
        badges={[
          LEVEL_LABEL[article.level],
          readingLabel(article.reading_minutes),
          `${article.word_count.toLocaleString()} words`,
        ]}
        sections={article.sections}
        title={article.title}
        summary={article.summary}
        chips={[
          ...article.tags.map((t) => ({ label: t })),
          ...article.archetypes.map((a) => ({ label: a, mono: true })),
        ]}
      />

      <EntryActions
        read={read}
        onToggleRead={onToggleRead}
        drillCount={detail.drill_question_count}
      />

      {detail.prerequisites.length > 0 && (
        <div className="mt-5 rounded-lg border border-slate-800 bg-slate-900/40 p-3">
          <div className="text-[11px] uppercase tracking-wider text-slate-500">
            Read first
          </div>
          <ul className="mt-1 space-y-1">
            {detail.prerequisites.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => onOpenArticle(p.id)}
                  className="text-sm text-indigo-300 hover:text-indigo-200"
                >
                  {p.title}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-2">
        <BlockRenderer
          blocks={article.blocks}
          handlers={{ onArticle: onOpenArticle }}
        />
      </div>

      {detail.concepts.length > 0 && (
        <EntrySection
          id={ENTRY_ANCHOR.concepts}
          title="Concepts in this article"
          subtitle="the reasoning patterns it teaches"
        >
          {/* `concept-` anchors: an inline concept span still lands on its
            * card here rather than leaving the article. The card is the way
            * *out* to the catalog. */}
          <RefCards
            anchorPrefix="concept-"
            items={detail.concepts.map((c) => ({
              id: c.id,
              title: c.name,
              summary: c.summary,
              meta: c.sections.map((s) => SECTION_LABEL[s]).join(' · '),
            }))}
            onOpen={onOpenConcept}
          />
        </EntrySection>
      )}

      {detail.related.length > 0 && (
        <EntrySection
          id={ENTRY_ANCHOR.related}
          title="Related"
          subtitle="articles this one points to"
        >
          <RefCards
            items={detail.related.map((r) => ({
              id: r.id,
              title: r.title,
              summary: r.summary,
              meta: `${KIND_LABEL[r.kind]} · ${readingLabel(r.reading_minutes)}`,
            }))}
            onOpen={onOpenArticle}
          />
        </EntrySection>
      )}

      {inTracks.length > 0 && (
        <EntrySection
          id={ENTRY_ANCHOR.tracks}
          title="Reading tracks"
          subtitle="curated orders this article appears in"
        >
          <TrackChips tracks={inTracks} onOpen={onOpenTrack} />
        </EntrySection>
      )}

      {article.references.length > 0 && (
        <EntrySection id={ENTRY_ANCHOR.references} title="References">
          <RefLinks refs={article.references} />
        </EntrySection>
      )}

      <Provenance
        parts={[
          article.source,
          `revision ${article.revision}`,
          `last reviewed ${article.last_reviewed}`,
          article.status,
        ]}
      />
    </article>
  )
}

/** Which template sections an article renders, for the outline. */
function articleSections(
  detail: LsatArticleDetail,
  tracks: LsatTrack[],
): { anchor: EntryAnchor; text: string }[] {
  const known = new Set(tracks.map((t) => t.id))
  const out: { anchor: EntryAnchor; text: string }[] = []
  if (detail.concepts.length > 0) {
    out.push({ anchor: ENTRY_ANCHOR.concepts, text: 'Concepts in this article' })
  }
  if (detail.related.length > 0) {
    out.push({ anchor: ENTRY_ANCHOR.related, text: 'Related' })
  }
  if (detail.tracks.some((t) => known.has(t.id))) {
    out.push({ anchor: ENTRY_ANCHOR.tracks, text: 'Reading tracks' })
  }
  if (detail.article.references.length > 0) {
    out.push({ anchor: ENTRY_ANCHOR.references, text: 'References' })
  }
  return out
}

function ConceptReader({
  catalog,
  concept,
  detail,
  error,
  index,
  onOpenArticle,
  onOpenConcept,
  onOpenTrack,
  onToggleRead,
  read,
  tracks,
}: {
  catalog: Map<string, LsatConcept>
  concept: LsatConcept | null
  detail: LsatConceptDetail | null
  error: string | null
  index: LsatArticleSummary[] | null
  onOpenArticle: (id: string) => void
  onOpenConcept: (id: string) => void
  onOpenTrack: (id: string) => void
  onToggleRead: () => void
  read: boolean
  tracks: LsatTrack[]
}) {
  if (error) {
    return (
      <div className="rounded-lg border border-rose-900/60 bg-rose-950/30 p-6 text-sm text-rose-200">
        {error} The catalog is served from{' '}
        <code className="rounded bg-slate-900 px-1.5 py-0.5 text-xs">
          /api/lsat/concepts
        </code>
        ; check that the backend is running.
      </div>
    )
  }

  if (!concept) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-8 text-sm text-slate-500">
        Loading concept…
      </div>
    )
  }

  const links = conceptLinks(concept, detail, index, catalog, tracks)

  return (
    <article className={MEASURE}>
      <EntryHeader
        pill="Concept"
        badges={[
          concept.examples.length === 1
            ? '1 example'
            : `${concept.examples.length} examples`,
          ...(detail ? [articlesLabel(links.taughtIn.length)] : []),
        ]}
        sections={concept.sections}
        title={concept.name}
        summary={concept.summary}
      />

      <EntryActions
        read={read}
        onToggleRead={onToggleRead}
        drillCount={detail?.used_in_questions.length}
        drillCapped={(detail?.used_in_questions.length ?? 0) >= 10}
      />

      {concept.detail && (
        <div className="mt-6">
          <p className="leading-7 text-slate-300">{concept.detail}</p>
        </div>
      )}

      {concept.examples.length > 0 && (
        <EntrySection id={ENTRY_ANCHOR.examples} title="Schema & examples">
          <ul className="mt-3 space-y-2">
            {concept.examples.map((ex) => (
              <li
                key={ex}
                className="rounded-lg bg-slate-900/70 px-3 py-2 font-mono text-xs leading-relaxed text-slate-300"
              >
                {ex}
              </li>
            ))}
          </ul>
        </EntrySection>
      )}

      {/* The merge's payoff, and the one section that speaks even when empty:
        * a learner who missed a concept-tagged question lands here needing
        * the material, so "none yet" is an answer where silence is not. */}
      <EntrySection
        id={ENTRY_ANCHOR.articles}
        title="Articles on this concept"
        subtitle="the material that teaches it"
      >
        {!detail ? (
          <p className="mt-2 text-sm text-slate-500">Looking up articles…</p>
        ) : links.taughtIn.length > 0 ? (
          <RefCards items={links.taughtIn} onOpen={onOpenArticle} />
        ) : (
          <p className="mt-2 text-sm text-slate-500">
            No article covers this concept yet — it is still only a tag on the
            question bank.
          </p>
        )}
      </EntrySection>

      {(links.related.length > 0 || links.dangling.length > 0) && (
        <EntrySection
          id={ENTRY_ANCHOR.related}
          title="Related"
          subtitle="concepts this one points to"
        >
          {links.related.length > 0 && (
            <RefCards items={links.related} onOpen={onOpenConcept} />
          )}
          {/* A `see_also` the catalog no longer holds reads as a dangling
            * reference, not as a button into a reader that will never load. */}
          {links.dangling.length > 0 && (
            <p className="mt-3 text-xs text-slate-600">
              Also referenced:{' '}
              {links.dangling.map((id) => (
                <span key={id} className="mr-2 font-mono">
                  {id}
                </span>
              ))}
            </p>
          )}
        </EntrySection>
      )}

      {links.tracks.length > 0 && (
        <EntrySection
          id={ENTRY_ANCHOR.tracks}
          title="Reading tracks"
          subtitle="curated orders that reach this concept"
        >
          <TrackChips tracks={links.tracks} onOpen={onOpenTrack} />
        </EntrySection>
      )}

      {concept.references.length > 0 && (
        <EntrySection id={ENTRY_ANCHOR.references} title="References">
          <RefLinks refs={concept.references} />
        </EntrySection>
      )}

      <Provenance
        parts={[
          'concept catalog',
          `${concept.sections.length === 1 ? 'section' : 'sections'} ${concept.sections.join(', ')}`,
        ]}
      />
    </article>
  )
}

/**
 * Everything a concept connects to, resolved once: the articles that teach
 * it (`taught_in` against the index), its `see_also` against the catalog —
 * split into the ones that resolve and the ones that no longer do — and the
 * reading tracks that reach any of those articles.
 */
function conceptLinks(
  concept: LsatConcept,
  detail: LsatConceptDetail | null,
  index: LsatArticleSummary[] | null,
  catalog: Map<string, LsatConcept>,
  tracks: LsatTrack[],
) {
  const byId = new Map((index ?? []).map((a) => [a.id, a]))
  const taughtIds = detail?.taught_in ?? []
  const taughtIn: RefItem[] = taughtIds
    .map((id) => byId.get(id))
    .filter((a): a is LsatArticleSummary => Boolean(a))
    .map((a) => ({
      id: a.id,
      title: a.title,
      summary: a.summary,
      meta: `${KIND_LABEL[a.kind]} · ${readingLabel(a.reading_minutes)}`,
    }))

  const related: RefItem[] = []
  const dangling: string[] = []
  for (const id of concept.see_also) {
    const target = catalog.get(id)
    if (target) {
      related.push({
        id,
        title: target.name,
        summary: target.summary,
        meta: target.sections.map((s) => SECTION_LABEL[s]).join(' · '),
      })
    } else {
      dangling.push(id)
    }
  }

  const taughtSet = new Set(taughtIds)
  const inTracks = tracks.filter((t) =>
    t.article_ids.some((id) => taughtSet.has(id)),
  )

  return { taughtIn, related, dangling, tracks: inTracks }
}

/** Which template sections a concept renders, for the outline. */
function conceptSections(
  concept: LsatConcept,
  detail: LsatConceptDetail | null,
  index: LsatArticleSummary[] | null,
  catalog: Map<string, LsatConcept>,
  tracks: LsatTrack[],
): { anchor: EntryAnchor; text: string }[] {
  const links = conceptLinks(concept, detail, index, catalog, tracks)
  const out: { anchor: EntryAnchor; text: string }[] = []
  if (concept.examples.length > 0) {
    out.push({ anchor: ENTRY_ANCHOR.examples, text: 'Schema & examples' })
  }
  out.push({ anchor: ENTRY_ANCHOR.articles, text: 'Articles on this concept' })
  if (links.related.length > 0 || links.dangling.length > 0) {
    out.push({ anchor: ENTRY_ANCHOR.related, text: 'Related' })
  }
  if (links.tracks.length > 0) {
    out.push({ anchor: ENTRY_ANCHOR.tracks, text: 'Reading tracks' })
  }
  if (concept.references.length > 0) {
    out.push({ anchor: ENTRY_ANCHOR.references, text: 'References' })
  }
  return out
}

function OutlineNav({ outline }: { outline: LsatOutlineEntry[] }) {
  return (
    <nav
      aria-label="On this page"
      className="shell-sticky-aside shell-panel-scroll max-h-[calc(100dvh-var(--shell-masthead-h)-var(--shell-pageheader-h)-var(--shell-toolbar-h)-3rem)] hidden @min-[72rem]:block"
    >
      {outline.length > 0 && (
        <>
          <div className="text-[11px] uppercase tracking-wider text-slate-500">
            On this page
          </div>
          <ul className="mt-2 space-y-1 border-l border-slate-800">
            {outline.map((entry) => (
              <li key={entry.anchor}>
                <a
                  href={`#${entry.anchor}`}
                  className={
                    'block border-l-2 border-transparent py-0.5 text-xs leading-relaxed text-slate-500 hover:border-amber-500 hover:text-slate-300 ' +
                    (entry.level === 3 ? 'pl-6' : 'pl-3')
                  }
                >
                  {entry.text}
                </a>
              </li>
            ))}
          </ul>
        </>
      )}
    </nav>
  )
}
