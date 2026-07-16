'use client'

import { useMemo, useState } from 'react'
import { content } from '@/lib/data'

/** Searchable glossary of the recurring reasoning patterns in the bank. */
export default function Concepts() {
  const [q, setQ] = useState('')
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return content.concepts
    return content.concepts.filter((c) =>
      [c.name, c.summary, c.detail, ...(c.examples ?? [])]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(needle),
    )
  }, [q])

  return (
    <section aria-label="Concepts">
      <div className="drill-head">
        <h2>Concept reference</h2>
        <p className="drill-timing">{content.concepts.length} recurring reasoning patterns</p>
      </div>

      <label className="search">
        <span className="sr-only">Search concepts</span>
        <input
          type="search"
          placeholder="Search concepts…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </label>

      {filtered.length === 0 ? (
        <p className="empty">No concepts match “{q}”.</p>
      ) : (
        <ul className="concept-list">
          {filtered.map((c) => (
            <li key={c.id} className="concept">
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
          ))}
        </ul>
      )}
    </section>
  )
}
