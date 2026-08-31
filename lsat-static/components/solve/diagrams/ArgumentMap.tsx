import type { ArgumentMapRep, ArgumentNode } from '@/lib/types'

/**
 * Argument structure for LR stimuli: premise/assumption boxes flow down into
 * the conclusion. Roles carry a text label, never colour alone.
 */

const ROLE_LABEL: Record<ArgumentNode['role'], string> = {
  premise: 'Premise',
  assumption: 'Assumption',
  conclusion: 'Conclusion',
  objection: 'Objection',
}

function mapLabel(rep: ArgumentMapRep): string {
  const byId = new Map(rep.nodes.map((n) => [n.id, n]))
  const edges = rep.edges.map((e) => {
    const from = byId.get(e.from)
    const to = byId.get(e.to)
    return `${from?.role ?? e.from} "${from?.text ?? ''}" ${e.relation} ${to?.role ?? e.to}`
  })
  return `Argument map with ${rep.nodes.length} parts. ${edges.join('. ')}.`
}

function NodeBox({ node }: { node: ArgumentNode }) {
  return (
    <div className={`arg-node arg-node-${node.role}`}>
      <p className="arg-role">{ROLE_LABEL[node.role]}</p>
      <p className="arg-text">{node.text}</p>
    </div>
  )
}

export default function ArgumentMap({ rep }: { rep: ArgumentMapRep }) {
  const supports = rep.nodes.filter((n) => n.role !== 'conclusion')
  const conclusions = rep.nodes.filter((n) => n.role === 'conclusion')
  const hasOppose = rep.edges.some((e) => e.relation === 'opposes')
  return (
    <div role="img" aria-label={mapLabel(rep)} className="rep rep-scroll">
      <div className="arg-supports">
        {supports.map((n) => (
          <NodeBox key={n.id} node={n} />
        ))}
      </div>
      <div className="arg-arrow" aria-hidden="true">
        <svg width="24" height="28" viewBox="0 0 24 28">
          <line x1="12" y1="2" x2="12" y2="20" strokeWidth="1.5" />
          <path d="M6 18 L12 26 L18 18" />
        </svg>
      </div>
      <div className="arg-conclusions">
        {conclusions.map((n) => (
          <NodeBox key={n.id} node={n} />
        ))}
      </div>
      {hasOppose && (
        <p className="arg-oppose-note">
          Dashed / “opposes” parts push against the conclusion rather than
          supporting it.
        </p>
      )}
    </div>
  )
}
