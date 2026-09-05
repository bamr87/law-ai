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
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

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

  const toggleRead = useCallback((id: string) => {
    setReadIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      saveReadIds(next)
      return next
    })
  }, [])

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

  const progress = index?.length
    ? Math.round((readIds.size / index.length) * 100)
    : 0

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

  // Three columns while reading (the outline is article-only), two in the
  // catalog — a concept has no in-page outline, and giving its cross-links
  // the whole width beats parking them in a 15rem gutter. Both grow past
  // 1800px, where the page frame itself stops capping at `max-w-7xl`.
  const grid =
    view === 'articles'
      ? 'lg:grid lg:grid-cols-[17rem_minmax(0,1fr)] lg:gap-8 xl:grid-cols-[17rem_minmax(0,1fr)_15rem] min-[1800px]:grid-cols-[20rem_minmax(0,1fr)_18rem] min-[1800px]:gap-12'
      : 'lg:grid lg:grid-cols-[17rem_minmax(0,1fr)] lg:gap-8 min-[1800px]:grid-cols-[20rem_minmax(0,1fr)] min-[1800px]:gap-12'

  const railCount =
    view === 'articles' ? (index?.length ?? 0) : (concepts?.length ?? 0)
  const railNoun = view === 'articles' ? 'articles' : 'concepts'

  return (
    <div className="space-y-4">
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
        <button
          type="button"
          onClick={() => setRailOpen((v) => !v)}
          aria-expanded={railOpen}
          className="mb-4 w-full rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-2 text-left text-sm text-slate-300 lg:hidden"
        >
          {railOpen ? 'Hide' : 'Browse'} contents · {railCount} {railNoun}
        </button>

        <nav
          aria-label="Library contents"
          className={`${railOpen ? 'block' : 'hidden'} shell-sticky-aside shell-panel-scroll max-h-[calc(100dvh-var(--shell-masthead-h)-var(--shell-pageheader-h)-var(--shell-toolbar-h)-3rem)] mb-6 lg:mb-0 lg:block lg:pr-2`}
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
              progress={progress}
              query={query}
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
              selectedId={conceptId}
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
              onToggleRead={toggleRead}
              readIds={readIds}
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
            />
          )}
        </div>

        {/* ------------------------------------------------------- outline */}
        {view === 'articles' && (
          <OutlineNav outline={detail?.article.outline ?? []} />
        )}
      </div>
    </div>
  )
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

function ArticleRail({
  activeTrack,
  grouped,
  hits,
  index,
  onOpen,
  onTrackChange,
  progress,
  query,
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
  progress: number
  query: string
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

      <div className="mt-3 text-[11px] text-slate-500">
        {readIds.size} of {index?.length ?? 0} read · {progress}%
      </div>

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
                    <button
                      type="button"
                      onClick={() => onOpen(article.id)}
                      aria-current={
                        article.id === selectedId ? 'true' : undefined
                      }
                      className={
                        'flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm transition ' +
                        (article.id === selectedId
                          ? 'bg-amber-500/15 text-amber-100'
                          : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200')
                      }
                    >
                      <span
                        aria-hidden="true"
                        className={
                          'mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ' +
                          (readIds.has(article.id)
                            ? 'bg-emerald-400'
                            : 'bg-slate-700')
                        }
                      />
                      <span className="min-w-0">
                        <span className="block truncate">{article.title}</span>
                        <span className="text-[10px] text-slate-600">
                          {readingLabel(article.reading_minutes)}
                        </span>
                      </span>
                    </button>
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
  selectedId,
  total,
}: {
  error: string | null
  groups: [LsatSectionCode | 'misc', LsatConcept[]][]
  loaded: boolean
  onOpen: (id: string) => void
  query: string
  selectedId: string | null
  total: number
}) {
  const shown = groups.reduce((n, [, items]) => n + items.length, 0)

  return (
    <>
      <div className="mt-3 text-[11px] text-slate-500">
        {shown === total
          ? `${total} concept${total === 1 ? '' : 's'}`
          : `${shown} of ${total} concepts`}
      </div>

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
                  <button
                    type="button"
                    onClick={() => onOpen(concept.id)}
                    aria-current={
                      concept.id === selectedId ? 'true' : undefined
                    }
                    className={
                      'block w-full rounded-md px-2 py-1.5 text-left text-sm transition ' +
                      (concept.id === selectedId
                        ? 'bg-amber-500/15 text-amber-100'
                        : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200')
                    }
                  >
                    <span className="block truncate">{concept.name}</span>
                  </button>
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
// Readers
// ---------------------------------------------------------------------------

/** The prose measure. Widened a little where the page frame widens too. */
const MEASURE = 'max-w-[68ch] min-[1800px]:max-w-[76ch]'

function ArticleReader({
  detail,
  onOpenArticle,
  onOpenConcept,
  onToggleRead,
  readIds,
}: {
  detail: LsatArticleDetail | null
  onOpenArticle: (id: string) => void
  onOpenConcept: (id: string) => void
  onToggleRead: (id: string) => void
  readIds: Set<string>
}) {
  if (!detail) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-8 text-sm text-slate-500">
        Loading article…
      </div>
    )
  }

  return (
    <article className={MEASURE}>
      <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wider text-slate-500">
        <span className="rounded-full bg-slate-800 px-2 py-0.5 text-slate-300">
          {KIND_LABEL[detail.article.kind]}
        </span>
        <span>{LEVEL_LABEL[detail.article.level]}</span>
        <span aria-hidden="true">·</span>
        <span>{readingLabel(detail.article.reading_minutes)}</span>
        {detail.article.sections.map((s) => (
          <span key={s} className="text-amber-400/80">
            {SECTION_LABEL[s]}
          </span>
        ))}
      </div>

      <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-100">
        {detail.article.title}
      </h2>
      <p className="mt-2 leading-7 text-slate-400">{detail.article.summary}</p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => onToggleRead(detail.article.id)}
          className={
            'rounded-lg px-3 py-1.5 text-xs font-medium transition ' +
            (readIds.has(detail.article.id)
              ? 'bg-emerald-500/15 text-emerald-200 ring-1 ring-inset ring-emerald-500/30'
              : 'bg-slate-800 text-slate-300 hover:bg-slate-700')
          }
        >
          {readIds.has(detail.article.id) ? '✓ Read' : 'Mark as read'}
        </button>
        {detail.drill_question_count > 0 && (
          <Link
            href="/lsat"
            className="rounded-lg bg-amber-500/15 px-3 py-1.5 text-xs font-medium text-amber-200 ring-1 ring-inset ring-amber-500/30 hover:bg-amber-500/25"
          >
            Drill this ({detail.drill_question_count} questions)
          </Link>
        )}
      </div>

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
          blocks={detail.article.blocks}
          handlers={{ onArticle: onOpenArticle }}
        />
      </div>

      {detail.concepts.length > 0 && (
        <section className="mt-10 border-t border-slate-800 pt-6">
          <h2 className="text-lg font-semibold text-slate-100">
            Concepts in this article
          </h2>
          {/* The glossary keeps its `concept-<id>` anchors — an inline concept
            * span still lands here rather than leaving the article. The name
            * is the way *out* to the catalog, for a reader who wants the
            * examples, the cross-references and everything else that teaches
            * it. */}
          <dl className="mt-3 space-y-3">
            {detail.concepts.map((c) => (
              <div key={c.id} id={`concept-${c.id}`} className="scroll-mt-24">
                <dt>
                  <button
                    type="button"
                    onClick={() => onOpenConcept(c.id)}
                    className="text-sm font-medium text-emerald-300 underline-offset-4 hover:underline"
                  >
                    {c.name}
                  </button>
                </dt>
                <dd className="text-sm leading-relaxed text-slate-400">
                  {c.summary}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {detail.article.references.length > 0 && (
        <section className="mt-8 border-t border-slate-800 pt-6">
          <h2 className="text-lg font-semibold text-slate-100">References</h2>
          <ul className="mt-2 space-y-1 text-sm">
            {detail.article.references.map((r) => (
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
        </section>
      )}

      {detail.related.length > 0 && (
        <section className="mt-8 border-t border-slate-800 pt-6">
          <h2 className="text-lg font-semibold text-slate-100">Related</h2>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {detail.related.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => onOpenArticle(r.id)}
                  className="w-full rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-left hover:border-amber-500/40"
                >
                  <span className="block text-sm font-medium text-slate-200">
                    {r.title}
                  </span>
                  <span className="mt-1 block text-xs leading-relaxed text-slate-500">
                    {r.summary}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="mt-10 border-t border-slate-800 pt-4 text-xs text-slate-600">
        {detail.article.source} · revision {detail.article.revision} · last
        reviewed {detail.article.last_reviewed} · study aid for LSAT
        preparation, not legal advice.
      </p>
    </article>
  )
}

function ConceptReader({
  catalog,
  concept,
  detail,
  error,
  index,
  onOpenArticle,
  onOpenConcept,
}: {
  catalog: Map<string, LsatConcept>
  concept: LsatConcept | null
  detail: LsatConceptDetail | null
  error: string | null
  index: LsatArticleSummary[] | null
  onOpenArticle: (id: string) => void
  onOpenConcept: (id: string) => void
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

  const byId = new Map((index ?? []).map((a) => [a.id, a]))
  const taughtIn = (detail?.taught_in ?? [])
    .map((id) => byId.get(id))
    .filter((a): a is LsatArticleSummary => Boolean(a))
  const drills = detail?.used_in_questions ?? []

  return (
    <article className={MEASURE}>
      <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wider text-slate-500">
        <span className="rounded-full bg-slate-800 px-2 py-0.5 text-slate-300">
          Concept
        </span>
        {concept.sections.map((s) => (
          <span key={s} className="text-amber-400/80">
            {SECTION_LABEL[s]}
          </span>
        ))}
      </div>

      <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-100">
        {concept.name}
      </h2>
      <p className="mt-2 leading-7 text-slate-400">{concept.summary}</p>

      {concept.detail && (
        <p className="mt-4 leading-7 text-slate-300">{concept.detail}</p>
      )}

      {concept.examples.length > 0 && (
        <section className="mt-8 border-t border-slate-800 pt-6">
          <h3 className="text-lg font-semibold text-slate-100">
            Schema &amp; examples
          </h3>
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
        </section>
      )}

      {/* The merge's payoff: the concept → material direction the API has
        * always exposed as `taught_in` and no screen ever rendered. A learner
        * who misses a concept-tagged question lands on the tag and leaves
        * with the article that teaches it. */}
      <section className="mt-8 border-t border-slate-800 pt-6">
        <h3 className="text-lg font-semibold text-slate-100">Where to learn it</h3>
        {taughtIn.length > 0 ? (
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {taughtIn.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => onOpenArticle(a.id)}
                  className="h-full w-full rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-left hover:border-amber-500/40"
                >
                  <span className="block text-sm font-medium text-slate-200">
                    {a.title}
                  </span>
                  <span className="mt-1 block text-xs leading-relaxed text-slate-500">
                    {a.summary}
                  </span>
                  <span className="mt-2 block text-[10px] uppercase tracking-wider text-slate-600">
                    {KIND_LABEL[a.kind]} · {readingLabel(a.reading_minutes)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-slate-500">
            No article covers this concept yet — it is still only a tag on the
            question bank.
          </p>
        )}

        {drills.length > 0 && (
          <p className="mt-3 text-sm text-slate-400">
            Tagged on {drills.length} bank question
            {drills.length === 1 ? '' : 's'} —{' '}
            <Link
              href="/lsat"
              className="text-amber-300 underline underline-offset-2 hover:text-amber-200"
            >
              drill them in the lab
            </Link>
            .
          </p>
        )}
      </section>

      {concept.see_also.length > 0 && (
        <section className="mt-8 border-t border-slate-800 pt-6">
          <h3 className="text-lg font-semibold text-slate-100">See also</h3>
          {/* Only a concept the catalog actually holds becomes a link: a
            * `see_also` naming something that was renamed or removed should
            * read as a dangling reference, not as a button into a reader
            * that will never load. */}
          <ul className="mt-2 flex flex-wrap gap-2">
            {concept.see_also.map((id) => {
              const target = catalog.get(id)
              return (
                <li key={id}>
                  {target ? (
                    <button
                      type="button"
                      onClick={() => onOpenConcept(id)}
                      className="rounded-full bg-slate-800/60 px-3 py-1 text-xs text-slate-300 transition hover:bg-slate-700 hover:text-slate-100"
                    >
                      {target.name}
                    </button>
                  ) : (
                    <span className="rounded-full bg-slate-900/60 px-3 py-1 font-mono text-xs text-slate-600">
                      {id}
                    </span>
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      )}

      {concept.references.length > 0 && (
        <section className="mt-8 border-t border-slate-800 pt-6">
          <h3 className="text-lg font-semibold text-slate-100">References</h3>
          <ul className="mt-2 space-y-1 text-sm">
            {concept.references.map((r) => (
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
        </section>
      )}

      <p className="mt-10 border-t border-slate-800 pt-4 text-xs text-slate-600">
        Concept catalog · study aid for LSAT preparation, not legal advice.
      </p>
    </article>
  )
}

function OutlineNav({ outline }: { outline: LsatOutlineEntry[] }) {
  return (
    <nav
      aria-label="On this page"
      className="shell-sticky-aside shell-panel-scroll max-h-[calc(100dvh-var(--shell-masthead-h)-var(--shell-pageheader-h)-var(--shell-toolbar-h)-3rem)] hidden xl:block"
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
