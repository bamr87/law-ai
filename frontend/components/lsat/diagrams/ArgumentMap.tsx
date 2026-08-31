import type { LsatArgumentMapRep, LsatArgumentNode } from '@/lib/api'

/**
 * Argument structure for LR stimuli (spec 041 FR-7): premise/assumption
 * boxes flow down into the conclusion. Support edges are solid arrows,
 * oppose edges dashed with an explicit label (never colour alone).
 */

const ROLE_STYLE: Record<LsatArgumentNode['role'], { label: string; cls: string }> = {
  premise: { label: 'Premise', cls: 'border-sky-500/40 bg-sky-500/10' },
  assumption: {
    label: 'Assumption',
    cls: 'border-amber-500/40 bg-amber-500/10 border-dashed',
  },
  conclusion: { label: 'Conclusion', cls: 'border-emerald-500/50 bg-emerald-500/10' },
  objection: { label: 'Objection', cls: 'border-rose-500/40 bg-rose-500/10' },
}

function mapLabel(rep: LsatArgumentMapRep): string {
  const byId = new Map(rep.nodes.map((n) => [n.id, n]))
  const edges = rep.edges.map((e) => {
    const from = byId.get(e.from)
    const to = byId.get(e.to)
    return `${from?.role ?? e.from} "${from?.text ?? ''}" ${e.relation} ${
      to?.role ?? e.to
    }`
  })
  return `Argument map with ${rep.nodes.length} parts. ${edges.join('. ')}.`
}

function NodeBox({ node }: { node: LsatArgumentNode }) {
  const style = ROLE_STYLE[node.role]
  return (
    <div className={`rounded-lg border px-3 py-2 ${style.cls}`}>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
        {style.label}
      </p>
      <p className="mt-0.5 text-xs leading-relaxed text-slate-200">{node.text}</p>
    </div>
  )
}

export default function ArgumentMap({ rep }: { rep: LsatArgumentMapRep }) {
  const supports = rep.nodes.filter((n) => n.role !== 'conclusion')
  const conclusions = rep.nodes.filter((n) => n.role === 'conclusion')
  const hasOppose = rep.edges.some((e) => e.relation === 'opposes')
  return (
    <div
      role="img"
      aria-label={mapLabel(rep)}
      className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950/60 p-3"
    >
      <div className="grid gap-2 sm:grid-cols-2">
        {supports.map((n) => (
          <NodeBox key={n.id} node={n} />
        ))}
      </div>
      <div className="my-1 flex justify-center" aria-hidden="true">
        <svg width="24" height="28" viewBox="0 0 24 28">
          <line
            x1="12"
            y1="2"
            x2="12"
            y2="20"
            className="stroke-slate-500"
            strokeWidth="1.5"
          />
          <path d="M6 18 L12 26 L18 18" className="fill-slate-500" />
        </svg>
      </div>
      <div className="space-y-2">
        {conclusions.map((n) => (
          <NodeBox key={n.id} node={n} />
        ))}
      </div>
      {hasOppose && (
        <p className="mt-2 text-[11px] text-rose-300">
          Dashed / “opposes” parts push against the conclusion rather than
          supporting it.
        </p>
      )}
    </div>
  )
}
