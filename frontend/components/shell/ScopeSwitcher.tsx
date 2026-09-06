'use client'

import { useEffect, useState, useSyncExternalStore } from 'react'
import { useSearchParams } from 'next/navigation'

import { fetchMatter, fetchMatters, type MatterRow } from '@/lib/api'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import {
  getActiveScope,
  projectScopeFor,
  setActiveScope,
  subscribeActiveScope,
} from '@/lib/scope/active'

/**
 * Pick the matter the shell is scoped to (BL-20260830-08).
 *
 * A scope switcher is an IDOR vector, which is why this component never turns
 * a string into an id. Two rules, both load-bearing:
 *
 * 1. **Every option comes from the server.** The list is `GET /api/matters`,
 *    which returns only the caller's own matters, and the scope id is built
 *    from the row's server-assigned `id` (`lib/scope/active.ts`).
 * 2. **A URL slug is a request, not an answer.** `?matter=<slug>` is resolved
 *    by calling the owner-scoped endpoint; the id used is the one that comes
 *    back. A slug that is unknown *or* belongs to someone else resolves to
 *    nothing and the shell silently stays on the instance scope — the two
 *    cases must be indistinguishable or the control leaks existence.
 *
 * Signed out (or with no matters), it degrades to the spec-040 readout.
 */
export default function ScopeSwitcher() {
  const active = useSyncExternalStore(
    subscribeActiveScope,
    getActiveScope,
    () => null,
  )
  const [matters, setMatters] = useState<MatterRow[] | null>(null)
  const params = useSearchParams()
  const slugParam = params?.get('matter') ?? ''

  useEffect(() => {
    let live = true
    fetchMatters()
      .then((body) => {
        if (live) setMatters(body.matters)
      })
      // Signed out is the common case, not an error worth showing.
      .catch(() => {
        if (live) setMatters([])
      })
    return () => {
      live = false
    }
  }, [])

  // Deep link: resolve the slug server-side and take the id from the response.
  useEffect(() => {
    if (!slugParam || active?.slug === slugParam) return
    let live = true
    fetchMatter(slugParam)
      .then((matter) => {
        if (live && matter) setActiveScope(projectScopeFor(matter))
      })
      .catch(() => {
        /* unknown or unowned — stay on the instance scope, say nothing */
      })
    return () => {
      live = false
    }
  }, [slugParam, active?.slug])

  if (!matters || matters.length === 0) {
    return (
      <div
        className="max-w-xs truncate rounded-full border border-slate-700 bg-slate-900/60 px-3 py-1 text-center text-xs text-slate-300"
        title="Instance is the only live scope until you own a matter."
      >
        <span className="text-slate-500">Scope · </span>
        {INSTANCE_SCOPE.name}
      </div>
    )
  }

  return (
    <label className="flex items-center gap-2 text-xs text-slate-300">
      <span className="text-slate-500">Scope</span>
      <select
        aria-label="Active scope"
        className="max-w-56 truncate rounded-full border border-slate-700 bg-slate-900/60 px-3 py-1 text-xs text-slate-200"
        value={active?.slug ?? ''}
        onChange={(event) => {
          const slug = event.target.value
          const chosen = matters.find((m) => m.slug === slug)
          setActiveScope(chosen ? projectScopeFor(chosen) : null)
        }}
      >
        <option value="">{INSTANCE_SCOPE.name}</option>
        {matters.map((matter) => (
          <option key={matter.id} value={matter.slug}>
            {matter.name}
          </option>
        ))}
      </select>
    </label>
  )
}
