'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  articlesTeaching,
  conceptById,
  content,
  questionsForConcept,
  tracks,
} from '@/lib/data'
import type { SectionCode } from '@/lib/types'

/**
 * The concept catalog — the Concepts view of the knowledge library.
 *
 * It used to be its own destination in the header nav, one along from the
 * library, which put the vocabulary and the material that teaches it on
 * opposite sides of the site. It is now the library's second view (see
 * `Library.tsx`), and each card follows the same entry template the article
 * reader does — header, body, then the cross-references in a fixed order:
 * articles on this concept, related, reading tracks, references — so a
 * learner reads one shape whichever kind of entry is in front of them.
 * Parity with the platform's merged library.
 */

const SECTION_FILTERS: { id: 'all' | SectionCode; label: string; full: string }[] = [
  { id: 'all', label: 'All', full: 'All sections' },
  { id: 'LR', label: 'LR', full: 'Logical Reasoning' },
  { id: 'RC', label: 'RC', full: 'Reading Comprehension' },
  { id: 'LG', label: 'LG', full: 'Logic Games' },
]

export default function Concepts({
  focusId,
  onOpenArticle,
  onOpenTrack,
}: {
  /**
   * The concept a `#catalog-<id>` link asked for (BL-20260905-04). The card
   * is brought into view and focused, so a link to one concept lands on that
   * concept rather than at the top of the catalog.
   */
  focusId?: string | null
  /** Hands the reader back to the Articles view on the chosen article. */
  onOpenArticle?: (id: string) => void
  /** Hands the reader back to the Articles view with a track as the rail. */
  onOpenTrack?: (id: string) => void
}) {
  const [q, setQ] = useState('')
  const [section, setSection] = useState<'all' | SectionCode>('all')

  // After the list has committed, so the card exists whether the catalog just
  // opened on a deep link or was already up when the fragment changed.
  useEffect(() => {
    if (!focusId) return
    const card = document.getElementById(`catalog-${focusId}`)
    if (!card) return
    const reduced =
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    card.focus?.({ preventScroll: true })
    card.scrollIntoView?.({ block: 'start', behavior: reduced ? 'auto' : 'smooth' })
  }, [focusId])

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return content.concepts.filter((c) => {
      if (section !== 'all' && !(c.sections ?? []).includes(section)) {
        return false
      }
      if (!needle) return true
      return [c.name, c.summary, c.detail, ...(c.examples ?? [])]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(needle)
    })
  }, [q, section])

  return (
    <section aria-label="Concepts">
      <label className="search">
        <span className="sr-only">Search concepts</span>
        <input
          type="search"
          placeholder="Search concepts…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </label>

      <div className="lib-filters" role="group" aria-label="Filter by section">
        {SECTION_FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            className={'pill' + (section === f.id ? ' pill-active' : ' pill-muted')}
            aria-pressed={section === f.id}
            aria-label={f.full}
            title={f.full}
            onClick={() => setSection(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      <p className="lib-eyebrow">
        {filtered.length === content.concepts.length
          ? `${content.concepts.length} recurring reasoning patterns`
          : `${filtered.length} of ${content.concepts.length} concepts`}
      </p>

      {filtered.length === 0 ? (
        <p className="empty">No concept matches that filter.</p>
      ) : (
        <ul className="concept-list">
          {filtered.map((c) => {
            const taughtIn = articlesTeaching(c.id)
            const drills = questionsForConcept(c.id)
            const taughtIds = new Set(taughtIn.map((a) => a.id))
            const inTracks = tracks.filter((t) =>
              t.article_ids.some((id) => taughtIds.has(id)),
            )
            const seeAlso = (c.see_also ?? []).map((id) => ({
              id,
              target: conceptById(id),
            }))
            const examples = c.examples ?? []
            return (
              <li
                key={c.id}
                className="concept"
                id={`catalog-${c.id}`}
                // Programmatic focus target only: a `#catalog-<id>` link has
                // to land the reader *on* the concept, not merely scroll it
                // past. Not in the tab order — the card's own controls are.
                tabIndex={-1}
              >
                {/* header: the same facts an article's header carries */}
                <div className="lib-meta">
                  <span className="pill pill-muted">Concept</span>
                  <span>
                    {examples.length === 1 ? '1 example' : `${examples.length} examples`}
                  </span>
                  <span aria-hidden="true">·</span>
                  <span>
                    {taughtIn.length === 1
                      ? 'taught in 1 article'
                      : `taught in ${taughtIn.length} articles`}
                  </span>
                  {(c.sections ?? []).map((s) => (
                    <span key={s} className="lib-meta-section">
                      {s}
                    </span>
                  ))}
                  {/* The capability the platform had and this site did not: a
                      URL for one concept (BL-20260905-04). A plain anchor, so
                      it copies, opens in a new tab, and works with no script
                      at all — and it sits beside the heading rather than
                      inside it, so it does not end up in the heading's
                      accessible name. */}
                  <a
                    href={`#catalog-${c.id}`}
                    className="concept-permalink"
                    aria-label={`Link to ${c.name}`}
                  >
                    #
                  </a>
                </div>
                <h3>{c.name}</h3>
                {c.summary && <p className="concept-summary">{c.summary}</p>}

                {/* actions: the drill count is an action, as on an article */}
                {drills.length > 0 && (
                  <p className="concept-drills">
                    {drills.length} bank question{drills.length === 1 ? '' : 's'}{' '}
                    drill this concept
                  </p>
                )}

                {/* body */}
                {c.detail && <p className="concept-detail">{c.detail}</p>}
                {examples.length > 0 && (
                  <div className="concept-block">
                    <span className="lib-eyebrow">Schema &amp; examples</span>
                    <ul className="concept-examples">
                      {examples.map((ex, i) => (
                        <li key={i}>{ex}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* The whole point of living inside the library: a concept
                    that names the material teaching it — and says so in words
                    when the corpus has not caught up. */}
                <div className="concept-block concept-teaches">
                  <span className="lib-eyebrow">Articles on this concept</span>
                  {taughtIn.length > 0 ? (
                    <ul className="concept-teaches-list">
                      {taughtIn.map((a) => (
                        <li key={a.id}>
                          <button
                            type="button"
                            className="linklike"
                            onClick={() => onOpenArticle?.(a.id)}
                          >
                            {a.title}
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="concept-teaches-none">
                      No article covers this concept yet.
                    </span>
                  )}
                </div>

                {seeAlso.length > 0 && (
                  <div className="concept-block">
                    <span className="lib-eyebrow">Related</span>
                    <ul className="concept-teaches-list">
                      {seeAlso.map(({ id, target }) =>
                        target ? (
                          <li key={id}>
                            {/* A sibling card on this same list: an anchor,
                                so it works with no script at all. */}
                            <a href={`#catalog-${id}`}>{target.name}</a>
                          </li>
                        ) : (
                          <li key={id} className="concept-dangling">
                            {id}
                          </li>
                        ),
                      )}
                    </ul>
                  </div>
                )}

                {inTracks.length > 0 && (
                  <div className="concept-block">
                    <span className="lib-eyebrow">Reading tracks</span>
                    <ul className="lib-tracks">
                      {inTracks.map((t) => (
                        <li key={t.id}>
                          <button
                            type="button"
                            className="lib-track"
                            onClick={() => onOpenTrack?.(t.id)}
                          >
                            {t.name}
                            <span className="lib-track-meta">
                              {' '}
                              · {t.article_count} articles · {t.estimated_minutes} min
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {(c.references ?? []).length > 0 && (
                  <div className="concept-block">
                    <span className="lib-eyebrow">References</span>
                    <ul className="lib-refs">
                      {(c.references ?? []).map((r) => (
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
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
