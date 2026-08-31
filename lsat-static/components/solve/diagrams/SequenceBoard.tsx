import type { SequenceRep } from '@/lib/types'

/**
 * Ordering-game board: horizontal slots, left = first. Placed entities sit
 * inside their slot; exclusions render beneath as `~X` — symbol *and* colour,
 * never colour alone.
 *
 * Ported from the platform's `frontend/components/lsat/diagrams/` (spec 045)
 * onto semantic CSS, because the static export is Tailwind-free.
 */

const SLOT_W = 64
const SLOT_H = 56
const GAP = 12
const PAD = 8
const EXCL_H = 22

function boardLabel(rep: SequenceRep): string {
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

export default function SequenceBoard({ rep }: { rep: SequenceRep }) {
  const hasExclusions = Object.values(rep.exclusions).some((xs) => xs.length > 0)
  const width = PAD * 2 + rep.slots.length * SLOT_W + (rep.slots.length - 1) * GAP
  const height = PAD + 18 + SLOT_H + (hasExclusions ? EXCL_H : 0) + PAD
  const unplaced = rep.entities.filter(
    (e) => !Object.values(rep.placements).includes(e),
  )
  return (
    <div className="rep">
      <p className="rep-caption">
        Elements: <span className="rep-mono">{rep.entities.join('  ')}</span>
        {unplaced.length > 0 && unplaced.length < rep.entities.length && (
          <span className="rep-muted"> (still floating: {unplaced.join(', ')})</span>
        )}
      </p>
      <div className="rep-scroll">
        <svg
          role="img"
          aria-label={boardLabel(rep)}
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
        >
          {rep.slots.map((slot, i) => {
            const x = PAD + i * (SLOT_W + GAP)
            const y = PAD + 14
            const placed = rep.placements[slot]
            const excluded = rep.exclusions[slot] ?? []
            return (
              <g key={slot}>
                <text x={x + SLOT_W / 2} y={y - 4} textAnchor="middle" className="seq-slot-label" fontSize={10}>
                  {slot}
                </text>
                <rect
                  x={x}
                  y={y}
                  width={SLOT_W}
                  height={SLOT_H}
                  rx={8}
                  className={placed ? 'seq-slot seq-slot-filled' : 'seq-slot'}
                  strokeWidth={1.5}
                />
                {placed ? (
                  <text x={x + SLOT_W / 2} y={y + SLOT_H / 2 + 6} textAnchor="middle" className="seq-entity" fontSize={20} fontWeight={600}>
                    {placed}
                  </text>
                ) : (
                  <text x={x + SLOT_W / 2} y={y + SLOT_H / 2 + 5} textAnchor="middle" className="seq-empty" fontSize={14}>
                    ?
                  </text>
                )}
                {excluded.length > 0 && (
                  <text x={x + SLOT_W / 2} y={y + SLOT_H + 15} textAnchor="middle" className="seq-excluded" fontSize={11}>
                    {excluded.map((e) => `~${e}`).join(' ')}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      </div>
      {rep.note && <p className="rep-note">{rep.note}</p>}
    </div>
  )
}
