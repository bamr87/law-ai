'use client'

import { useEffect, useState } from 'react'

import { fetchLsatConcepts, type LsatConcept } from '@/lib/api'

/**
 * Post-grade reference block for the answer component.
 *
 * Deliberately links to nothing external: the only references shown are the
 * concepts a question is tagged with — name, summary, and the schema-level
 * examples the concept derives from — resolved against the in-app concept
 * catalog (`/api/lsat/concepts`). External source URLs are excluded by
 * design; deeper reading lives on the Concepts tab.
 */

let catalogPromise: Promise<Map<string, LsatConcept>> | null = null

function loadCatalog(): Promise<Map<string, LsatConcept>> {
  catalogPromise ??= fetchLsatConcepts().then(
    (r) => new Map(r.concepts.map((c) => [c.id, c])),
  )
  return catalogPromise
}

/** Test hook: drop the memoized concept catalog. */
export function resetConceptCatalog(): void {
  catalogPromise = null
}

export default function ConceptRefs({ conceptIds }: { conceptIds: string[] }) {
  const [catalog, setCatalog] = useState<Map<string, LsatConcept> | null>(null)

  useEffect(() => {
    let mounted = true
    loadCatalog()
      .then((m) => {
        if (mounted) setCatalog(m)
      })
      .catch(() => {
        // Catalog unavailable — fall back to bare id chips; retry next mount.
        catalogPromise = null
        if (mounted) setCatalog(new Map())
      })
    return () => {
      mounted = false
    }
  }, [])

  if (conceptIds.length === 0) return null

  return (
    <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/60 p-4">
      <div className="text-[11px] uppercase tracking-wider text-slate-500">
        Derived from
      </div>
      <ul className="mt-2 space-y-2">
        {conceptIds.map((id) => {
          const concept = catalog?.get(id)
          if (!concept) {
            return (
              <li key={id}>
                <span className="rounded-full bg-slate-800 px-2 py-0.5 font-mono text-[11px] text-slate-300">
                  {id}
                </span>
              </li>
            )
          }
          return (
            <li key={id}>
              <details className="group">
                <summary className="cursor-pointer text-sm font-medium text-sky-300 hover:text-sky-200">
                  {concept.name}
                </summary>
                <p className="mt-1 text-xs leading-relaxed text-slate-400">
                  {concept.summary}
                </p>
                {concept.examples.length > 0 && (
                  <div className="mt-2">
                    <div className="text-[10px] uppercase tracking-wider text-slate-600">
                      Schema / examples
                    </div>
                    <ul className="mt-1 space-y-1">
                      {concept.examples.map((ex) => (
                        <li
                          key={ex}
                          className="rounded bg-slate-900/70 px-2 py-1 font-mono text-[11px] text-slate-300"
                        >
                          {ex}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </details>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
