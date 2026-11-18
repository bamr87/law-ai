import type { Passage } from '@/lib/types'

/**
 * Renders the shared context for an RC passage or an LG game setup.
 *
 * A comparative RC set (spec 047 FR-9) carries two texts under their own
 * headings: every question in such a set names one of them, so collapsing
 * them into one block would make the questions unanswerable.
 */
export default function PassagePanel({ passage }: { passage: Passage }) {
  const comparative = Boolean(passage.passage_b)
  const label = comparative ? 'Comparative passages' : `${passage.section} context`
  return (
    // A tab stop (#222, WCAG 2.1.1): beside the questions on a wide screen
    // this column is its own scroll region (`.drill-grid > .passage` in
    // globals.css), and it holds nothing focusable, so a keyboard user had no
    // way to reach the rest of a long passage. Focused, the arrow keys and
    // Page Down scroll it; the global `:focus-visible` ring shows where focus
    // is. The aside already carries its name.
    <aside className="passage" aria-label={label} tabIndex={0}>
      <h3 className="passage-title">{passage.title}</h3>
      {passage.summary && <p className="passage-summary">{passage.summary}</p>}
      {passage.passage && comparative && (
        <h4 className="passage-subhead">{passage.title_a ?? 'Passage A'}</h4>
      )}
      {passage.passage && <div className="passage-body">{passage.passage}</div>}
      {passage.passage_b && (
        <>
          <h4 className="passage-subhead passage-subhead-b">
            {passage.title_b ?? 'Passage B'}
          </h4>
          <div className="passage-body">{passage.passage_b}</div>
        </>
      )}
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
