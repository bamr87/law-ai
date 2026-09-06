'use client'

import { useEffect, useState, useSyncExternalStore } from 'react'
import { useSearchParams } from 'next/navigation'

import {
  fetchIdentity,
  fetchMatter,
  fetchMatters,
  type MatterRow,
} from '@/lib/api'
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
 *
 * It asks *whether* it is signed in before asking for anything account-scoped
 * (BL-20260906-68). `/api/matters` is correct to refuse an anonymous caller,
 * but the shell renders on every page, so trying anyway spent a 401 on every
 * page view of every anonymous session — noise in the log, and a denial any
 * "no failed API call" check then has to carve an exception for.
 * `GET /api/auth/me` is AllowAny, so the question costs a 200 and the
 * account-scoped calls simply do not happen while signed out.
 */
export default function ScopeSwitcher() {
  const active = useSyncExternalStore(
    subscribeActiveScope,
    getActiveScope,
    () => null,
  )
  const [matters, setMatters] = useState<MatterRow[] | null>(null)
  // null while the identity probe is in flight: neither signed in nor out yet.
  const [signedIn, setSignedIn] = useState<boolean | null>(null)
  const params = useSearchParams()
  const slugParam = params?.get('matter') ?? ''

  useEffect(() => {
    let live = true
    fetchIdentity().then((me) => {
      if (live) setSignedIn(me.authenticated)
    })
    return () => {
      live = false
    }
  }, [])

  useEffect(() => {
    // Signed out (or still asking): `matters` stays null, which is already the
    // instance readout — and not one account-scoped request is made.
    if (!signedIn) return
    let live = true
    fetchMatters()
      .then((body) => {
        if (live) setMatters(body.matters)
      })
      // A signed-in caller can still be refused (a revoked session); that is
      // the readout too, not an error worth showing.
      .catch(() => {
        if (live) setMatters([])
      })
    return () => {
      live = false
    }
  }, [signedIn])

  // Deep link: resolve the slug server-side and take the id from the response.
  useEffect(() => {
    if (!signedIn) return
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
  }, [signedIn, slugParam, active?.slug])

  if (!matters || matters.length === 0) {
    return (
      <div
        className="max-w-xs truncate rounded-full border border-slate-700 bg-slate-900/60 px-3 py-1 text-center text-xs text-slate-300"
        title="Instance is the only live scope until you own a matter."
      >
        <span className="text-slate-400">Scope · </span>
        {INSTANCE_SCOPE.name}
      </div>
    )
  }

  return (
    <label className="flex items-center gap-2 text-xs text-slate-300">
      <span className="text-slate-400">Scope</span>
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
