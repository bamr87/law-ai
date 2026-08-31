import type { LsatPassageMapRep } from '@/lib/api'

/**
 * Paragraph-by-paragraph structural outline of an RC passage (spec 041
 * FR-7): the role each paragraph plays, in reading order.
 */
export default function PassageMap({ rep }: { rep: LsatPassageMapRep }) {
  return (
    <ol className="space-y-2 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      {rep.paragraphs.map((p) => (
        <li key={p.paragraph} className="flex items-start gap-3">
          <span
            className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-slate-700 bg-slate-900 text-xs font-semibold text-slate-300"
            aria-label={`Paragraph ${p.paragraph}`}
          >
            {p.paragraph}
          </span>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-sky-300">
              {p.role}
            </p>
            <p className="text-xs leading-relaxed text-slate-400">{p.gist}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}
