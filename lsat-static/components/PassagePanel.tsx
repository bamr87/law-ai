import type { Passage } from '@/lib/types'

/** Renders the shared context for an RC passage or an LG game setup. */
export default function PassagePanel({ passage }: { passage: Passage }) {
  return (
    <aside className="passage" aria-label={`${passage.section} context`}>
      <h3 className="passage-title">{passage.title}</h3>
      {passage.summary && <p className="passage-summary">{passage.summary}</p>}
      {passage.passage && <div className="passage-body">{passage.passage}</div>}
      {passage.setup && <div className="passage-body">{passage.setup}</div>}
      {passage.rules && passage.rules.length > 0 && (
        <>
          <h4 className="passage-subhead">Rules</h4>
          <ol className="passage-rules">
            {passage.rules.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ol>
        </>
      )}
    </aside>
  )
}
