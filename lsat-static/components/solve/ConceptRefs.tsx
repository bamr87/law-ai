import { conceptById } from '@/lib/data'

/**
 * Post-grade reference block: the concepts a question is tagged with.
 *
 * Static counterpart of the platform's `frontend/components/lsat/ConceptRefs.tsx`
 * (spec 045), ported by spec 046. The only difference is the lookup — the
 * concept catalog is already in the bundle, so there is no fetch, no loading
 * state, and no bare-id fallback for an unreachable API.
 *
 * Deliberately links to nothing external, matching the platform: the concepts
 * are named and summarised here, and deeper reading lives on the Concepts tab.
 */
export default function ConceptRefs({ conceptIds }: { conceptIds: string[] }) {
  if (conceptIds.length === 0) return null

  return (
    <div className="concept-refs">
      <div className="concept-refs-head">Derived from</div>
      <ul className="concept-refs-list">
        {conceptIds.map((id) => {
          const concept = conceptById(id)
          if (!concept) {
            return (
              <li key={id}>
                <span className="concept-chip">{id}</span>
              </li>
            )
          }
          return (
            <li key={id}>
              <details>
                <summary className="concept-name">{concept.name}</summary>
                {concept.summary && (
                  <p className="concept-summary-text">{concept.summary}</p>
                )}
                {concept.examples && concept.examples.length > 0 && (
                  <div className="concept-examples">
                    <div className="concept-examples-head">Schema / examples</div>
                    <ul>
                      {concept.examples.map((ex) => (
                        <li key={ex} className="concept-example">
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
