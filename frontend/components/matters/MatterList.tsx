'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

import { fetchMatters, type MatterRow } from '@/lib/api'

/**
 * The caller's matters (spec 036).
 *
 * Signed out is not an error state — most of this app works without an
 * account — so it renders as an invitation rather than a failure, and the
 * component never claims a matter exists that the server did not return.
 */
export default function MatterList() {
  const [matters, setMatters] = useState<MatterRow[] | null>(null)
  const [signedOut, setSignedOut] = useState(false)

  const load = useCallback(async () => {
    try {
      const body = await fetchMatters()
      setMatters(body.matters)
      setSignedOut(false)
    } catch {
      setMatters([])
      setSignedOut(true)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (matters === null) {
    return <p className="text-sm text-slate-400">Loading matters…</p>
  }

  if (signedOut) {
    return (
      <p className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 text-sm text-slate-400">
        Matters are per-account. Sign in to open yours — the rest of the app
        works without one.
      </p>
    )
  }

  if (matters.length === 0) {
    return (
      <p className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 text-sm text-slate-400">
        No matters yet. A matter is the container for one legal question: its
        research, its authorities, and its deadlines.
      </p>
    )
  }

  return (
    <ul className="space-y-2">
      {matters.map((matter) => (
        <li
          key={matter.id}
          className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4"
        >
          <div className="flex items-baseline justify-between gap-3">
            <Link
              href={`/matters/${matter.slug}`}
              className="text-sm font-semibold text-slate-100 hover:text-amber-300"
            >
              {matter.name}
            </Link>
            <span className="text-[11px] uppercase tracking-wider text-slate-400">
              {matter.stage}
            </span>
          </div>
          {matter.issue_tags.length > 0 && (
            <p className="mt-1 text-xs text-slate-400">
              {matter.issue_tags.join(' · ')}
            </p>
          )}
        </li>
      ))}
    </ul>
  )
}
