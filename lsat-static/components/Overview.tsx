'use client'

import type { SectionCode } from '@/lib/types'
import { content } from '@/lib/data'

/**
 * Landing view: intro + one card per section with the key exam facts.
 *
 * 'WS' is a section but not a drill — Argumentative Writing has prompts, not
 * keyed questions — so its card counts prompts and opens the Writing view
 * instead of a Drill that would have nothing to show (spec 047 FR-3).
 */
export default function Overview({
  onStart,
}: {
  onStart: (view: SectionCode | 'writing') => void
}) {
  return (
    <section aria-label="Overview">
      <div className="intro">
        <h2>Practice every LSAT section</h2>
        <p>
          {content.counts.total} original, openly-licensed practice items across Logical Reasoning,
          Reading Comprehension, and Logic Games — each with a full explanation — plus{' '}
          {content.counts.writing_prompts ?? 0} Argumentative Writing prompts with a scoring rubric
          and an annotated model response. Everything runs in your browser; your progress is stored
          only on this device.
        </p>
        {/* Say what is missing rather than letting it be discovered. The full
            lab has three things this site cannot: they all need a server, and
            a learner who goes looking for them deserves to be told once, up
            front, instead of finding a gap and wondering whether it is a bug
            (BL-20260831-25). */}
        <details className="intro-limits">
          <summary>What this site does not have</summary>
          <p>
            Three things in the full Law AI lab need a server, so they are not here: an{' '}
            <strong>AI tutor</strong> to talk a question through when the written guide is not
            enough, a <strong>blind answer cross-check</strong> that re-solves an item
            independently, and <strong>server-side stats</strong> and the human review queue used
            to author new questions. Everything else — the bank, the explanations, the
            step-by-step solve guides, the writing rubric and model responses, the knowledge
            library and the concept catalog — is here in full and works offline. The lab itself is{' '}
            <a href="https://github.com/bamr87/law-ai" target="_blank" rel="noreferrer">
              open source
            </a>
            .
          </p>
        </details>
      </div>

      <div className="cards">
        {content.sections.map((s) => {
          const isWriting = s.code === 'WS'
          const count = isWriting
            ? (content.counts.writing_prompts ?? 0)
            : content.counts[s.code]
          return (
          <article key={s.code} className="card">
            <div className="card-head">
              <h3>{s.name}</h3>
              <span className="pill">
                {count} {isWriting ? 'prompts' : 'items'}
              </span>
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
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onStart(isWriting ? 'writing' : s.code)}
            >
              {isWriting ? 'Start writing practice' : `Start ${s.code} drill`} →
            </button>
          </article>
          )
        })}
      </div>
    </section>
  )
}
