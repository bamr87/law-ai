'use client'

import type { SectionCode } from '@/lib/types'
import { content } from '@/lib/data'

/** Landing view: intro + one card per section with the key exam facts. */
export default function Overview({ onStart }: { onStart: (s: SectionCode) => void }) {
  return (
    <section aria-label="Overview">
      <div className="intro">
        <h2>Practice every LSAT section</h2>
        <p>
          {content.counts.total} original, openly-licensed practice items across Logical Reasoning,
          Reading Comprehension, and Logic Games — each with a full explanation. Everything runs in
          your browser; your progress is stored only on this device.
        </p>
      </div>

      <div className="cards">
        {content.sections.map((s) => (
          <article key={s.code} className="card">
            <div className="card-head">
              <h3>{s.name}</h3>
              <span className="pill">{content.counts[s.code]} items</span>
            </div>
            <p className="card-desc">{s.description}</p>
            <dl className="card-facts">
              <div>
                <dt>Format</dt>
                <dd>{s.format}</dd>
              </div>
              <div>
                <dt>Timing</dt>
                <dd>{s.timing}</dd>
              </div>
            </dl>
            {s.tips && s.tips.length > 0 && (
              <details className="card-tips">
                <summary>Strategy tips</summary>
                <ul>
                  {s.tips.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              </details>
            )}
            <button type="button" className="btn btn-primary" onClick={() => onStart(s.code)}>
              Start {s.code} drill →
            </button>
          </article>
        ))}
      </div>
    </section>
  )
}
