'use client'

/**
 * The offline reading/research surface (spec 048 FR-10).
 *
 * Parity with the platform reader: contents rail with search, filters and
 * tracks; the article itself rendered from typed blocks; an in-page outline;
 * cross-reference navigation; and per-browser reading progress. Everything
 * comes from the bundled `content.json`, so nothing here touches the network
 * (NFR-OFFLINE-1).
 *
 * Two views, matching the platform: **Articles** is the reader below, and
 * **Concepts** is the catalog that used to be its own header destination one
 * along from this one. Splitting them meant an article could name a concept
 * and a concept could name nothing; merged, `Concepts` links each pattern to
 * the articles that teach it and the questions that drill it, and clicking
 * one of those articles lands back here.
 *
 * Keyboard: `/` focuses search, `[`/`]` move through the visible list, and
 * `Escape` leaves the search field — consistent with the drill's scheme, and
 * none of them fire while the reader is typing.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import BlockRenderer from '@/components/library/BlockRenderer'
import Concepts from '@/components/Concepts'
import {
  articleById,
  articles,
  conceptById,
  content,
  drillsForArticle,
  inboundArticles,
  tracks,
} from '@/lib/data'
import { useShortcuts } from '@/lib/keyboard'
import { searchLibrary, type SearchHit } from '@/lib/search'
import type { Article, ArticleKind, SectionCode } from '@/lib/types'

const KIND_LABEL: Record<ArticleKind, string> = {
  orientation: 'Orientation',
  foundation: 'Foundations',
  'section-guide': 'Section guide',
  'question-type': 'Question type',
  technique: 'Technique',
  strategy: 'Strategy',
  'review-method': 'Review method',
}

/** Reading order for the contents rail: foundations before families. */
const KIND_ORDER: ArticleKind[] = [
  'orientation',
  'foundation',
  'section-guide',
  'question-type',
  'technique',
  'strategy',
  'review-method',
]

const SECTION_FILTERS: { id: 'all' | SectionCode; label: string; full: string }[] = [
  { id: 'all', label: 'All', full: 'All sections' },
  { id: 'LR', label: 'LR', full: 'Logical Reasoning' },
  { id: 'RC', label: 'RC', full: 'Reading Comprehension' },
  { id: 'LG', label: 'LG', full: 'Logic Games' },
  { id: 'WS', label: 'WS', full: 'Argumentative Writing' },
]

const READ_KEY = 'lsat-library-read'

function loadRead(): Set<string> {
  try {
    const raw = window.localStorage.getItem(READ_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? new Set(parsed.map(String)) : new Set()
  } catch {
    // Private mode, blocked site data, or no storage at all. Progress is a
    // convenience; the library reads fine without it.
    return new Set()
  }
}

function saveRead(ids: Set<string>): void {
  try {
    window.localStorage.setItem(READ_KEY, JSON.stringify([...ids].sort()))
  } catch {
    /* non-fatal */
  }
}

/**
 * Where a first-time reader lands.
 *
 * The head of the first curated track, not `articles[0]` — the article list is
 * sorted by id, so the alphabetical default opened "Answer-Choice Elimination"
 * on a reader who had not yet been told what the exam is.
 */
const LANDING_ARTICLE_ID = tracks[0]?.article_ids[0] ?? articles[0]?.id ?? ''

type View = 'articles' | 'concepts'

const VIEWS: { id: View; label: string; full: string }[] = [
  { id: 'articles', label: 'Articles', full: 'Long-form articles' },
  { id: 'concepts', label: 'Concepts', full: 'Concept catalog' },
]

export default function Library({
  onAnnounce,
}: {
  onAnnounce?: (message: string) => void
}) {
  const [view, setView] = useState<View>('articles')
  const [selectedId, setSelectedId] = useState<string>(LANDING_ARTICLE_ID)
  const [query, setQuery] = useState('')
  const [sectionFilter, setSectionFilter] = useState<'all' | SectionCode>('all')
  const [trackFilter, setTrackFilter] = useState('')
  const [readIds, setReadIds] = useState<Set<string>>(new Set())
  // Narrow viewports only (the CSS that gives this effect lives under a
  // `max-width: 899px` query): 35 contents rows above the article is a long
  // scroll to reach the thing you came to read.
  const [railOpen, setRailOpen] = useState(false)
  const searchRef = useRef<HTMLInputElement | null>(null)
  const articleRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    setReadIds(loadRead())
  }, [])

  const activeTrack = tracks.find((t) => t.id === trackFilter) ?? null

  const visible: Article[] = useMemo(() => {
    let rows = articles
    if (sectionFilter !== 'all') {
      rows = rows.filter((a) => a.sections.includes(sectionFilter))
    }
    if (activeTrack) {
      const order = new Map(activeTrack.article_ids.map((id, i) => [id, i]))
      // A track's order *is* the curriculum, so it overrides kind grouping.
      return rows
        .filter((a) => order.has(a.id))
        .sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0))
    }
    return rows
  }, [sectionFilter, activeTrack])

  const grouped = useMemo(() => {
    if (activeTrack) return null
    const buckets = new Map<ArticleKind, Article[]>()
    for (const a of visible) {
      buckets.set(a.kind, [...(buckets.get(a.kind) ?? []), a])
    }
    return KIND_ORDER.filter((k) => buckets.has(k)).map((kind) => ({
      kind,
      items: buckets.get(kind) ?? [],
    }))
  }, [visible, activeTrack])

  const hits: SearchHit[] | null = useMemo(
    () => (query.trim().length >= 2 ? searchLibrary(query) : null),
    [query],
  )

  const article = articleById(selectedId) ?? visible[0] ?? articles[0]

  const open = useCallback(
    (id: string) => {
      const next = articleById(id)
      if (!next) return
      setView('articles')
      setSelectedId(id)
      setRailOpen(false)
      onAnnounce?.(`Opened ${next.title}`)
      // Guarded: `matchMedia` is absent outside a browser, and a smooth-scroll
      // convenience must never be the thing that throws.
      const reduced =
        window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
      // Focus moves with the reader: a keyboard user who followed a
      // cross-reference must land in the new article, not stay in the rail.
      articleRef.current?.focus?.({ preventScroll: true })
      articleRef.current?.scrollIntoView?.({
        block: 'start',
        behavior: reduced ? 'auto' : 'smooth',
      })
    },
    [onAnnounce],
  )

  const step = useCallback(
    (delta: number) => {
      const list = hits ? hits.map((h) => h.id) : visible.map((a) => a.id)
      const at = list.indexOf(selectedId)
      const next = list[Math.min(list.length - 1, Math.max(0, at + delta))]
      if (next) open(next)
    },
    [hits, visible, selectedId, open],
  )

  // `j`/`k` rather than `[`/`]`: the page binds those to move between
  // destinations and keeps them bound while this view is mounted, so claiming
  // them here would move the destination *and* the article on one keystroke.
  // The drill's own `j`/`k` (hint carousel) is unmounted whenever this is up.
  // Only while the article list is on screen: the catalog has its own search
  // box and no ordered list to step through, so binding these there would aim
  // `/` at an input that is not mounted.
  useShortcuts(
    {
      '/': (e) => {
        e.preventDefault()
        searchRef.current?.focus()
        searchRef.current?.select()
      },
      k: () => step(-1),
      j: () => step(1),
    },
    { enabled: view === 'articles' },
  )

  const toggleRead = useCallback(
    (id: string) => {
      setReadIds((prev) => {
        const next = new Set(prev)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        saveRead(next)
        onAnnounce?.(next.has(id) ? 'Marked as read' : 'Marked as unread')
        return next
      })
    },
    [onAnnounce],
  )

  // No early return: an export can carry concepts without articles, and the
  // catalog is a view of this component now — bailing here would take it down
  // with the reader.
  const drills = article ? drillsForArticle(article) : []
  const related = article
    ? [
        ...article.related.map(articleById),
        ...inboundArticles(article.id),
      ].filter(
        (a, i, all): a is Article =>
          Boolean(a) &&
          all.findIndex((b) => b?.id === a?.id) === i &&
          a?.id !== article.id,
      )
    : []

  return (
    <section aria-label="Library" className="lib">
      <div className="drill-head">
        <h2>Knowledge library</h2>
        <p className="drill-timing">
          {view === 'articles'
            ? `${articles.length} articles · ${readIds.size} read · ${tracks.length} reading tracks`
            : `${content.concepts.length} recurring reasoning patterns`}
        </p>
      </div>

      <div className="lib-views" role="tablist" aria-label="Library views">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            type="button"
            role="tab"
            id={`lib-view-${v.id}`}
            aria-selected={view === v.id}
            aria-controls={`lib-panel-${v.id}`}
            aria-label={v.full}
            title={v.full}
            className={'lib-view' + (view === v.id ? ' lib-view-active' : '')}
            onClick={() => {
              setView(v.id)
              onAnnounce?.(`${v.full} view`)
            }}
          >
            {v.label}
          </button>
        ))}
      </div>

      {view === 'concepts' ? (
        <div
          role="tabpanel"
          id="lib-panel-concepts"
          aria-labelledby="lib-view-concepts"
        >
          <Concepts onOpenArticle={open} />
        </div>
      ) : !article ? (
        <div
          role="tabpanel"
          id="lib-panel-articles"
          aria-labelledby="lib-view-articles"
        >
          <p className="empty">
            This build of the site shipped without the knowledge library.
          </p>
        </div>
      ) : (
        <div
          role="tabpanel"
          id="lib-panel-articles"
          aria-labelledby="lib-view-articles"
          className="lib-grid"
        >
          {/* ------------------------------------------------------ rail */}
          <button
            type="button"
            className="btn lib-rail-toggle"
            aria-expanded={railOpen}
            aria-controls="lib-rail"
            onClick={() => setRailOpen((v) => !v)}
          >
            {railOpen ? 'Hide' : 'Browse'} contents · {articles.length} articles
          </button>

          <nav
            aria-label="Library contents"
            id="lib-rail"
            className={'lib-rail' + (railOpen ? ' lib-rail-open' : '')}
          >
            <label className="search">
              <span className="sr-only">Search the library</span>
              <input
                ref={searchRef}
                type="search"
                placeholder="Search articles… (press /)"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') {
                    e.currentTarget.blur()
                  }
                }}
              />
            </label>

            <div className="lib-filters" role="group" aria-label="Filter by section">
              {SECTION_FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  className={
                    'pill' + (sectionFilter === f.id ? ' pill-active' : ' pill-muted')
                  }
                  aria-pressed={sectionFilter === f.id}
                  aria-label={f.full}
                  title={f.full}
                  onClick={() => setSectionFilter(f.id)}
                >
                  {f.label}
                </button>
              ))}
            </div>

            <label className="lib-track-select">
              <span className="lib-eyebrow">Reading track</span>
              <select
                value={trackFilter}
                onChange={(e) => setTrackFilter(e.target.value)}
              >
                <option value="">All articles</option>
                {tracks.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} · {t.estimated_minutes} min
                  </option>
                ))}
              </select>
            </label>

            {activeTrack && <p className="lib-track-goal">{activeTrack.goal}</p>}

            {hits ? (
              <div className="lib-results">
                <div className="lib-eyebrow">
                  {hits.length} result{hits.length === 1 ? '' : 's'}
                </div>
                {hits.length === 0 ? (
                  <p className="empty">Nothing matched “{query.trim()}”.</p>
                ) : (
                  <ul className="lib-hitlist">
                    {hits.map((hit) => (
                      <li key={hit.id}>
                        <button
                          type="button"
                          className="lib-hit"
                          aria-current={hit.id === article.id ? 'true' : undefined}
                          onClick={() => open(hit.id)}
                        >
                          <span className="lib-hit-title">{hit.title}</span>
                          <span className="lib-hit-snippet">{hit.snippet}</span>
                          <span className="lib-hit-where">
                            matched in {hit.matched_in.join(', ')}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              (grouped ?? [{ kind: null as ArticleKind | null, items: visible }]).map(
                (group) => (
                  <div key={group.kind ?? 'track'} className="lib-group">
                    {group.kind && (
                      <div className="lib-eyebrow">{KIND_LABEL[group.kind]}</div>
                    )}
                    <ul className="lib-list-nav">
                      {group.items.map((a) => (
                        <li key={a.id}>
                          <button
                            type="button"
                            className={
                              'lib-nav-item' +
                              (a.id === article.id ? ' lib-nav-item-active' : '')
                            }
                            aria-current={a.id === article.id ? 'true' : undefined}
                            onClick={() => open(a.id)}
                          >
                            <span
                              aria-hidden="true"
                              className={
                                'lib-dot' + (readIds.has(a.id) ? ' lib-dot-read' : '')
                              }
                            />
                            <span className="lib-nav-text">
                              <span className="lib-nav-title">{a.title}</span>
                              <span className="lib-nav-meta">
                                {a.reading_minutes} min read
                              </span>
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ),
              )
            )}
          </nav>

          {/* ---------------------------------------------------- reader */}
          <article
            className="lib-article"
            ref={articleRef}
            tabIndex={-1}
            aria-labelledby="lib-article-title"
          >
            <div className="lib-meta">
              <span className="pill pill-muted">{KIND_LABEL[article.kind]}</span>
              <span>{article.reading_minutes} min read</span>
              {article.sections.map((s) => (
                <span key={s} className="lib-meta-section">
                  {s}
                </span>
              ))}
            </div>

            <h3 id="lib-article-title" className="lib-title">
              {article.title}
            </h3>
            <p className="lib-summary">{article.summary}</p>

            <div className="lib-actions">
              <button
                type="button"
                className={'btn' + (readIds.has(article.id) ? ' btn-primary' : '')}
                onClick={() => toggleRead(article.id)}
              >
                {readIds.has(article.id) ? '✓ Read' : 'Mark as read'}
              </button>
              {drills.length > 0 && (
                <span className="lib-drill-note">
                  {drills.length} bank question{drills.length === 1 ? '' : 's'} drill
                  these concepts
                </span>
              )}
            </div>

            {article.prerequisites.length > 0 && (
              <div className="lib-prereq">
                <div className="lib-eyebrow">Read first</div>
                <ul>
                  {article.prerequisites.map((id) => {
                    const prereq = articleById(id)
                    return prereq ? (
                      <li key={id}>
                        <button
                          type="button"
                          className="linklike"
                          onClick={() => open(id)}
                        >
                          {prereq.title}
                        </button>
                      </li>
                    ) : null
                  })}
                </ul>
              </div>
            )}

            {article.outline.length > 0 && (
              <nav aria-label="On this page" className="lib-outline">
                <div className="lib-eyebrow">On this page</div>
                <ul>
                  {article.outline.map((entry) => (
                    <li
                      key={entry.anchor}
                      className={entry.level === 3 ? 'lib-outline-sub' : undefined}
                    >
                      <a href={`#${entry.anchor}`}>{entry.text}</a>
                    </li>
                  ))}
                </ul>
              </nav>
            )}

            <div className="lib-body">
              <BlockRenderer blocks={article.blocks} handlers={{ onArticle: open }} />
            </div>

            {article.concepts.length > 0 && (
              <section className="lib-section">
                <h3>Concepts in this article</h3>
                <dl className="lib-glossary">
                  {article.concepts.map((id) => {
                    const concept = conceptById(id)
                    return (
                      <div key={id} id={`concept-${id}`}>
                        <dt>{concept?.name ?? id}</dt>
                        <dd>{concept?.summary ?? 'See the Concepts view.'}</dd>
                      </div>
                    )
                  })}
                </dl>
              </section>
            )}

            {(article.references ?? []).length > 0 && (
              <section className="lib-section">
                <h3>References</h3>
                <ul className="lib-refs">
                  {(article.references ?? []).map((r) => (
                    <li key={r.title}>
                      {r.url ? (
                        <a href={r.url} target="_blank" rel="noreferrer">
                          {r.title}
                        </a>
                      ) : (
                        r.title
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {related.length > 0 && (
              <section className="lib-section">
                <h3>Related</h3>
                <ul className="lib-related">
                  {related.map((r) => (
                    <li key={r.id}>
                      <button type="button" onClick={() => open(r.id)}>
                        <span className="lib-related-title">{r.title}</span>
                        <span className="lib-related-summary">{r.summary}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <p className="lib-provenance">
              {article.source ?? 'original (CC0)'} · revision {article.revision} · last
              reviewed {article.last_reviewed} · study aid for LSAT preparation, not
              legal advice.
            </p>
          </article>
        </div>
      )}
    </section>
  )
}
