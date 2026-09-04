'use client'

/**
 * LSAT Library — the reading/research surface (spec 048 FR-8).
 *
 * Three regions at wide viewports: a contents rail (search, filters, tracks,
 * article list), the reader, and an "on this page" outline. Below `xl` the
 * outline folds into the reader; below `lg` the rail becomes a disclosure so
 * the reading column keeps a comfortable measure on a phone.
 *
 * The reader renders typed blocks only — see `library/BlockRenderer` — so
 * nothing on this page passes through `dangerouslySetInnerHTML`.
 */

import {
  fetchLsatArticle,
  fetchLsatLibrary,
  fetchLsatTracks,
  searchLsatLibrary,
  type LsatArticleDetail,
  type LsatArticleKind,
  type LsatArticleSummary,
  type LsatLibrarySearchHit,
  type LsatTrack,
} from '@/lib/api'
import BlockRenderer from '@/components/lsat/library/BlockRenderer'
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

type SectionFilter = 'all' | 'LR' | 'RC' | 'LG' | 'WS'

const SECTION_FILTERS: { id: SectionFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'LR', label: 'LR' },
  { id: 'RC', label: 'RC' },
  { id: 'LG', label: 'LG' },
  { id: 'WS', label: 'WS' },
]

/** Read the article id from the URL fragment so a reader can share a link. */
function hashArticleId(): string | null {
  if (typeof window === 'undefined') return null
  const raw = window.location.hash.replace(/^#/, '')
  return raw.startsWith('article-') ? raw.slice('article-'.length) : null
}

export default function LsatLibrary() {
  const [index, setIndex] = useState<LsatArticleSummary[] | null>(null)
  const [tracks, setTracks] = useState<LsatTrack[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<LsatArticleDetail | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

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
    Promise.all([fetchLsatLibrary(), fetchLsatTracks()])
      .then(([lib, tr]) => {
        if (!live) return
        setIndex(lib.articles)
        setTracks(tr.tracks)
        // Deep link wins over the remembered article, which wins over the
        // head of the first curated track. Not `articles[0]`: the index is
        // sorted by id, so the alphabetical default would open a technique
        // note to a reader who has not yet been told what the exam is.
        const landing =
          tr.tracks[0]?.article_ids[0] ?? lib.articles[0]?.id ?? null
        const wanted = hashArticleId() ?? loadLastArticleId() ?? landing
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
        window.history.replaceState(null, '', `#article-${selectedId}`)
      })
      .catch(() => {
        if (live) setLoadError(`Could not load article "${selectedId}".`)
      })
    return () => {
      live = false
    }
  }, [selectedId])

  // --- search (debounced) -------------------------------------------------

  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
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
  }, [query])

  const openArticle = useCallback((id: string) => {
    setSelectedId(id)
    setRailOpen(false)
    // Optional call, not just optional chaining: `scrollIntoView` is absent
    // in jsdom and in any non-browser render, and moving the viewport is a
    // convenience that must never be the thing that throws.
    readerRef.current?.scrollIntoView?.({
      block: 'start',
      behavior: prefersReducedMotion() ? 'auto' : 'smooth',
    })
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

  return (
    <div className="lg:grid lg:grid-cols-[17rem_minmax(0,1fr)] lg:gap-8 xl:grid-cols-[17rem_minmax(0,1fr)_15rem]">
      {/* ---------------------------------------------------------- rail */}
      <button
        type="button"
        onClick={() => setRailOpen((v) => !v)}
        aria-expanded={railOpen}
        className="mb-4 w-full rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-2 text-left text-sm text-slate-300 lg:hidden"
      >
        {railOpen ? 'Hide' : 'Browse'} contents · {index?.length ?? 0} articles
      </button>

      <nav
        aria-label="Library contents"
        className={`${railOpen ? 'block' : 'hidden'} shell-sticky-aside shell-panel-scroll max-h-[calc(100dvh-var(--shell-masthead-h)-var(--shell-pageheader-h)-var(--shell-toolbar-h)-3rem)] mb-6 lg:mb-0 lg:block lg:pr-2`}
      >
        <label className="block">
          <span className="sr-only">Search the library</span>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search articles…"
            className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-amber-500 focus-ring-practice"
          />
        </label>

        <div className="mt-3 flex flex-wrap gap-1">
          {SECTION_FILTERS.map((f) => (
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

        <label className="mt-3 block">
          <span className="text-[11px] uppercase tracking-wider text-slate-500">
            Reading track
          </span>
          <select
            value={trackFilter}
            onChange={(e) => setTrackFilter(e.target.value)}
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
                    onClick={() => openArticle(hit.id)}
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
                        onClick={() => openArticle(article.id)}
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
      </nav>

      {/* -------------------------------------------------------- reader */}
      <div ref={readerRef} className="min-w-0 scroll-mt-24">
        {!detail ? (
          <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-8 text-sm text-slate-500">
            Loading article…
          </div>
        ) : (
          <article className="max-w-[68ch]">
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
                onClick={() => toggleRead(detail.article.id)}
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
                        onClick={() => openArticle(p.id)}
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
                handlers={{ onArticle: openArticle }}
              />
            </div>

            {detail.concepts.length > 0 && (
              <section className="mt-10 border-t border-slate-800 pt-6">
                <h2 className="text-lg font-semibold text-slate-100">
                  Concepts in this article
                </h2>
                <dl className="mt-3 space-y-3">
                  {detail.concepts.map((c) => (
                    <div key={c.id} id={`concept-${c.id}`} className="scroll-mt-24">
                      <dt className="text-sm font-medium text-emerald-300">
                        {c.name}
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
                        onClick={() => openArticle(r.id)}
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
        )}
      </div>

      {/* ------------------------------------------------------- outline */}
      <nav
        aria-label="On this page"
        className="shell-sticky-aside shell-panel-scroll max-h-[calc(100dvh-var(--shell-masthead-h)-var(--shell-pageheader-h)-var(--shell-toolbar-h)-3rem)] hidden xl:block"
      >
        {detail && detail.article.outline.length > 0 && (
          <>
            <div className="text-[11px] uppercase tracking-wider text-slate-500">
              On this page
            </div>
            <ul className="mt-2 space-y-1 border-l border-slate-800">
              {detail.article.outline.map((entry) => (
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
    </div>
  )
}
