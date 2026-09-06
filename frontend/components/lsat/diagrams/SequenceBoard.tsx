import type { LsatSequenceRep } from '@/lib/api'

/**
 * Ordering-game board: horizontal slots, left = first (spec 041 FR-7,
 * resolved OQ-3). Placed entities sit inside their slot; exclusions render
 * beneath as `~X` (symbol + colour, never colour alone — NFR-A11Y-1).
 */

const SLOT_W = 64
const SLOT_H = 56
const GAP = 12
const PAD = 8
const EXCL_H = 22

function boardLabel(rep: LsatSequenceRep): string {
  const parts = [`Sequence board with ${rep.slots.length} slots, first to last.`]
  for (const slot of rep.slots) {
    const placed = rep.placements[slot]
    if (placed) parts.push(`Slot ${slot}: ${placed}.`)
    const excluded = rep.exclusions[slot]
    if (excluded?.length) parts.push(`Slot ${slot} excludes ${excluded.join(', ')}.`)
  }
  const unplaced = rep.entities.filter(
    (e) => !Object.values(rep.placements).includes(e),
  )
  if (unplaced.length) parts.push(`Unplaced: ${unplaced.join(', ')}.`)
  return parts.join(' ')
}

export default function SequenceBoard({ rep }: { rep: LsatSequenceRep }) {
  const hasExclusions = Object.values(rep.exclusions).some((xs) => xs.length > 0)
  const width = PAD * 2 + rep.slots.length * SLOT_W + (rep.slots.length - 1) * GAP
  const height = PAD + 18 + SLOT_H + (hasExclusions ? EXCL_H : 0) + PAD
  const unplaced = rep.entities.filter(
    (e) => !Object.values(rep.placements).includes(e),
  )
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <p className="mb-2 text-[11px] uppercase tracking-wider text-slate-400">
        Elements:{' '}
        <span className="font-mono normal-case text-slate-300">
          {rep.entities.join('  ')}
        </span>
        {unplaced.length > 0 && unplaced.length < rep.entities.length && (
          <span className="ml-2 normal-case text-slate-400">
            (still floating: {unplaced.join(', ')})
          </span>
        )}
      </p>
      <div className="overflow-x-auto">
        <svg
          role="img"
          aria-label={boardLabel(rep)}
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          className="max-w-none"
        >
          {rep.slots.map((slot, i) => {
            const x = PAD + i * (SLOT_W + GAP)
            const y = PAD + 14
            const placed = rep.placements[slot]
            const excluded = rep.exclusions[slot] ?? []
            return (
              <g key={slot}>
                <text
                  x={x + SLOT_W / 2}
                  y={y - 4}
                  textAnchor="middle"
                  className="fill-slate-500"
                  fontSize={10}
                >
                  {slot}
                </text>
                <rect
                  x={x}
                  y={y}
                  width={SLOT_W}
                  height={SLOT_H}
                  rx={8}
                  className={
                    placed
                      ? 'fill-sky-500/15 stroke-sky-500/60'
                      : 'fill-slate-900/60 stroke-slate-700'
                  }
                  strokeWidth={1.5}
                />
                {placed ? (
                  <text
                    x={x + SLOT_W / 2}
                    y={y + SLOT_H / 2 + 6}
                    textAnchor="middle"
                    className="fill-sky-200"
                    fontSize={20}
                    fontFamily="monospace"
                    fontWeight={600}
                  >
                    {placed}
                  </text>
                ) : (
                  <text
                    x={x + SLOT_W / 2}
                    y={y + SLOT_H / 2 + 5}
                    textAnchor="middle"
                    className="fill-slate-700"
                    fontSize={14}
                  >
                    ?
                  </text>
                )}
                {excluded.length > 0 && (
                  <text
                    x={x + SLOT_W / 2}
                    y={y + SLOT_H + 15}
                    textAnchor="middle"
                    className="fill-rose-300"
                    fontSize={11}
                    fontFamily="monospace"
                  >
                    {excluded.map((e) => `~${e}`).join(' ')}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      </div>
      {rep.note && <p className="mt-2 text-xs italic text-slate-400">{rep.note}</p>}
    </div>
  )
}
