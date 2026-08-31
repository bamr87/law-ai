import type { GridCell, GridRep } from '@/lib/types'

/**
 * Grouping / assignment board as a semantic table. Marks pair a symbol with
 * colour so meaning never rides on colour alone.
 */

const MARKS: Record<GridCell['mark'], { glyph: string; label: string; cls: string }> = {
  yes: { glyph: '✓', label: 'yes', cls: 'mark-yes' },
  no: { glyph: '✕', label: 'no', cls: 'mark-no' },
  maybe: { glyph: '?', label: 'maybe', cls: 'mark-maybe' },
}

export default function GroupGrid({ rep }: { rep: GridRep }) {
  const cellFor = (row: string, column: string) =>
    rep.cells.find((c) => c.row === row && c.column === column)
  return (
    <div className="rep rep-scroll">
      <table className="grid-rep">
        {rep.note && <caption className="rep-note">{rep.note}</caption>}
        <thead>
          <tr>
            <th scope="col" aria-label="row label" />
            {rep.columns.map((col) => (
              <th key={col} scope="col" className="grid-col">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rep.rows.map((row) => (
            <tr key={row}>
              <th scope="row" className="grid-row">
                {row}
              </th>
              {rep.columns.map((col) => {
                const cell = cellFor(row, col)
                const mark = cell ? MARKS[cell.mark] : null
                return (
                  <td key={col} className="grid-cell">
                    {mark ? (
                      <span className={mark.cls} title={cell?.note ?? undefined}>
                        {mark.glyph}
                        <span className="sr-only"> {mark.label}</span>
                      </span>
                    ) : (
                      <span className="grid-blank" aria-hidden="true">
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
      <p className="rep-legend">
        <span className="mark-yes">✓</span> = satisfies ·{' '}
        <span className="mark-no">✕</span> = violates ·{' '}
        <span className="mark-maybe">?</span> = undetermined
      </p>
    </div>
  )
}
