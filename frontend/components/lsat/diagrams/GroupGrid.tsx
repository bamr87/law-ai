import type { LsatGridCell, LsatGridRep } from '@/lib/api'

/**
 * Grouping / assignment / elimination board as a semantic table (spec 041
 * FR-7). Marks pair a symbol with colour so meaning never rides on colour
 * alone (NFR-A11Y-1).
 */

const MARKS: Record<
  LsatGridCell['mark'],
  { glyph: string; label: string; cls: string }
> = {
  yes: { glyph: '✓', label: 'yes', cls: 'text-emerald-300' },
  no: { glyph: '✕', label: 'no', cls: 'text-rose-300' },
  maybe: { glyph: '?', label: 'maybe', cls: 'text-amber-300' },
}

export default function GroupGrid({ rep }: { rep: LsatGridRep }) {
  const cellFor = (row: string, column: string) =>
    rep.cells.find((c) => c.row === row && c.column === column)
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <table className="min-w-full border-collapse text-sm">
        {rep.note && (
          <caption className="mb-2 caption-top text-left text-xs italic text-slate-500">
            {rep.note}
          </caption>
        )}
        <thead>
          <tr>
            <th scope="col" className="p-2" aria-label="row label" />
            {rep.columns.map((col) => (
              <th
                key={col}
                scope="col"
                className="p-2 text-center font-mono text-xs font-medium text-slate-400"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rep.rows.map((row) => (
            <tr key={row} className="border-t border-slate-800/70">
              <th
                scope="row"
                className="p-2 text-left font-mono text-xs font-medium text-slate-300"
              >
                {row}
              </th>
              {rep.columns.map((col) => {
                const cell = cellFor(row, col)
                const mark = cell ? MARKS[cell.mark] : null
                return (
                  <td key={col} className="p-2 text-center">
                    {mark ? (
                      <span
                        className={`font-semibold ${mark.cls}`}
                        title={cell?.note ?? undefined}
                      >
                        {mark.glyph}
                        <span className="sr-only"> {mark.label}</span>
                      </span>
                    ) : (
                      <span className="text-slate-700" aria-hidden="true">
                        ·
                      </span>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-slate-500">
        <span className="text-emerald-300">✓</span> = satisfies ·{' '}
        <span className="text-rose-300">✕</span> = violates ·{' '}
        <span className="text-amber-300">?</span> = undetermined
      </p>
    </div>
  )
}
