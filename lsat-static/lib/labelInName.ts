/**
 * The accessible name for a control that shows a short label and has a longer
 * name: the site nav's `LR` pill, the Library's `Concepts` tab and its
 * `LR`/`RC`/`LG`/`WS` section filters (#222).
 *
 * WCAG 2.5.3 (Label in Name, Level A): a speech-input user says what they see,
 * so the name has to contain, and should start with, the visible label. The
 * bare long name fails it — "click LR" matched nothing when the name was
 * "Logical Reasoning". `LR — Logical Reasoning` leads with what is on screen
 * and still spells the destination out for a screen reader.
 *
 * Not `Logical Reasoning (LR)`: label-in-name checkers, axe among them, drop
 * parenthesised text before comparing, so that form still fails.
 *
 * A long name that already contains the label (`Library & concepts`,
 * `Long-form articles`) is kept as it is. The comparison ignores case, the
 * way axe's `label-content-name-mismatch` does.
 *
 * @example
 *   labelInName({ label: 'LR', full: 'Logical Reasoning' })
 *   // → 'LR — Logical Reasoning'
 *   labelInName({ label: 'Articles', full: 'Long-form articles' })
 *   // → 'Long-form articles'
 */
export function labelInName(n: { label: string; full: string }): string {
  return n.full.toLowerCase().includes(n.label.toLowerCase())
    ? n.full
    : `${n.label} — ${n.full}`
}
