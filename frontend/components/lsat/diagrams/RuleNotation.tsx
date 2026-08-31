import type { LsatNotationRep } from '@/lib/api'

/**
 * Symbolized rules, one per line (spec 041 FR-7).
 *
 * The legend is real text (never colour- or symbol-only) so the notation is
 * learnable and screen-reader friendly (NFR-A11Y-1).
 */

const LEGEND: { symbol: string; meaning: string }[] = [
  { symbol: '→', meaning: 'if… then' },
  { symbol: '¬', meaning: 'not' },
  { symbol: '[X Y]', meaning: 'adjacent block, X immediately before Y' },
  { symbol: 'X — Y', meaning: 'X sometime before Y (any gap)' },
]

export default function RuleNotation({ rep }: { rep: LsatNotationRep }) {
  const used = LEGEND.filter(
    (l) =>
      rep.rules.some((r) => r.symbols.includes(l.symbol[0])) ||
      (l.symbol === '[X Y]' && rep.rules.some((r) => r.symbols.includes('['))) ||
      (l.symbol === 'X — Y' && rep.rules.some((r) => r.symbols.includes('—'))),
  )
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <dl className="space-y-2">
        {rep.rules.map((r, i) => (
          <div key={i} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <dt className="shrink-0 rounded bg-slate-800/80 px-2 py-0.5 font-mono text-sm text-sky-200">
              {r.symbols}
            </dt>
            <dd className="text-xs text-slate-400">
              {r.rule_text}
              {r.note && <span className="ml-2 italic text-slate-500">{r.note}</span>}
            </dd>
          </div>
        ))}
      </dl>
      {used.length > 0 && (
        <p className="mt-3 border-t border-slate-800 pt-2 text-[11px] text-slate-500">
          Legend:{' '}
          {used.map((l, i) => (
            <span key={l.symbol}>
              {i > 0 && ' · '}
              <span className="font-mono text-slate-400">{l.symbol}</span> ={' '}
              {l.meaning}
            </span>
          ))}
        </p>
      )}
    </div>
  )
}
