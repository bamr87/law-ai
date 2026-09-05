'use client'

import { useMemo, useState } from 'react'
import {
  articlesTeaching,
  content,
  questionsForConcept,
} from '@/lib/data'
import type { SectionCode } from '@/lib/types'

/**
 * The concept catalog — the Concepts view of the knowledge library.
 *
 * It used to be its own destination in the header nav, one along from the
 * library, which put the vocabulary and the material that teaches it on
 * opposite sides of the site. It is now the library's second view (see
 * `Library.tsx`), and every concept carries the inverse link the split made
 * impossible: the articles that teach it, and how many bank questions drill
 * it. Parity with the platform's merged library.
 */

const SECTION_FILTERS: { id: 'all' | SectionCode; label: string; full: string }[] = [
  { id: 'all', label: 'All', full: 'All sections' },
  { id: 'LR', label: 'LR', full: 'Logical Reasoning' },
  { id: 'RC', label: 'RC', full: 'Reading Comprehension' },
  { id: 'LG', label: 'LG', full: 'Logic Games' },
]

export default function Concepts({
  onOpenArticle,
}: {
  /** Hands the reader back to the Articles view on the chosen article. */
  onOpenArticle?: (id: string) => void
}) {
  const [q, setQ] = useState('')
  const [section, setSection] = useState<'all' | SectionCode>('all')

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
            return (
              <li key={c.id} className="concept" id={`catalog-${c.id}`}>
                <h3>{c.name}</h3>
                {c.summary && <p className="concept-summary">{c.summary}</p>}
                {c.detail && <p className="concept-detail">{c.detail}</p>}
                {c.examples && c.examples.length > 0 && (
                  <ul className="concept-examples">
                    {c.examples.map((ex, i) => (
                      <li key={i}>{ex}</li>
                    ))}
                  </ul>
                )}

                {/* The whole point of living inside the library: a concept
                    that names the material teaching it. */}
                <div className="concept-teaches">
                  {taughtIn.length > 0 ? (
                    <>
                      <span className="lib-eyebrow">Where to learn it</span>
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
                    </>
                  ) : (
                    <span className="concept-teaches-none">
                      No article covers this concept yet.
                    </span>
                  )}
                  {drills.length > 0 && (
                    <span className="concept-drills">
                      {drills.length} bank question
                      {drills.length === 1 ? '' : 's'}
                    </span>
                  )}
                </div>

                {c.sections && c.sections.length > 0 && (
                  <div className="concept-tags">
                    {c.sections.map((s) => (
                      <span key={s} className="pill pill-muted">
                        {s}
                      </span>
                    ))}
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
