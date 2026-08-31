import type { PassageMapRep } from '@/lib/types'

/** Paragraph-by-paragraph structural outline of an RC passage, in reading order. */
export default function PassageMap({ rep }: { rep: PassageMapRep }) {
  return (
    <ol className="rep passage-map">
      {rep.paragraphs.map((p) => (
        <li key={p.paragraph} className="passage-map-item">
          <span className="passage-map-num" aria-label={`Paragraph ${p.paragraph}`}>
            {p.paragraph}
          </span>
          <div>
            <p className="passage-map-role">{p.role}</p>
            <p className="passage-map-gist">{p.gist}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}
