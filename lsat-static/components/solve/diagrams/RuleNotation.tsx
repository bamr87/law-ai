import type { NotationRep } from '@/lib/types'

/**
 * Symbolized rules, one per line. The legend is real text — never colour- or
 * symbol-only — so the notation is learnable and screen-reader friendly.
 */

const LEGEND: { symbol: string; meaning: string }[] = [
  { symbol: '→', meaning: 'if… then' },
  { symbol: '¬', meaning: 'not' },
  { symbol: '[X Y]', meaning: 'adjacent block, X immediately before Y' },
  { symbol: 'X — Y', meaning: 'X sometime before Y (any gap)' },
]

export default function RuleNotation({ rep }: { rep: NotationRep }) {
  const used = LEGEND.filter(
    (l) =>
      rep.rules.some((r) => r.symbols.includes(l.symbol[0])) ||
      (l.symbol === '[X Y]' && rep.rules.some((r) => r.symbols.includes('['))) ||
      (l.symbol === 'X — Y' && rep.rules.some((r) => r.symbols.includes('—'))),
  )
  return (
    <div className="rep rep-scroll">
      <dl className="notation">
        {rep.rules.map((r, i) => (
          <div key={i} className="notation-row">
            <dt className="notation-symbols">{r.symbols}</dt>
            <dd className="notation-text">
              {r.rule_text}
              {r.note && <span className="rep-note-inline">{r.note}</span>}
            </dd>
          </div>
        ))}
      </dl>
      {used.length > 0 && (
        <p className="rep-legend">
          Legend:{' '}
          {used.map((l, i) => (
            <span key={l.symbol}>
              {i > 0 && ' · '}
              <span className="rep-mono">{l.symbol}</span> = {l.meaning}
            </span>
          ))}
        </p>
      )}
    </div>
  )
}
