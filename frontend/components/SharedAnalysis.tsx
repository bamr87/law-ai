'use client'

import { LegalDisclaimerBanner } from '@/components/LegalDisclaimer'
import { fetchSharedAnalysis, type SharedAnalysis } from '@/lib/api'
import { useEffect, useState } from 'react'

type State =
  | { kind: 'loading' }
  | { kind: 'missing' }
  | { kind: 'ready'; run: SharedAnalysis }

/**
 * Renders one shared analysis (BL-20260429-26).
 *
 * Deliberately read-only and credential-free: the slug is the whole
 * credential, so there is nothing here to sign in to and nothing to act on.
 * Every refusal the backend can give — revoked, archived, unshareable, never
 * minted — arrives as the same 404 and is shown as the same message, because
 * telling them apart would turn this page into an oracle.
 */
export default function SharedAnalysisPanel({ slug }: { slug: string }) {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false
    void fetchSharedAnalysis(slug)
      .then((run) => {
        if (cancelled) return
        setState(run ? { kind: 'ready', run } : { kind: 'missing' })
      })
      .catch(() => {
        if (!cancelled) setState({ kind: 'missing' })
      })
    return () => {
      cancelled = true
    }
  }, [slug])

  if (state.kind === 'loading') {
    return (
      <p className="text-sm text-slate-500" role="status">
        Loading shared analysis…
      </p>
    )
  }

  if (state.kind === 'missing') {
    return (
      <div className="space-y-4">
        <div
          role="alert"
          className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200"
        >
          This share link is not available. It may have been revoked, or it may
          never have existed.
        </div>
        <LegalDisclaimerBanner />
      </div>
    )
  }

  const { run } = state
  return (
    <div className="space-y-6">
      <LegalDisclaimerBanner />

      {run.label && (
        <p className="text-sm text-slate-300">{run.label}</p>
      )}

      <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6">
        <h2 className="text-xs uppercase tracking-wider text-slate-500">
          Fact pattern
        </h2>
        <p className="mt-2 whitespace-pre-wrap text-sm text-slate-300">
          {run.request?.text ?? ''}
        </p>
      </section>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6">
        <h2 className="text-sm font-semibold text-slate-200">IRAC Brief</h2>
        <dl className="mt-3 space-y-3 text-sm">
          {(
            [
              ['Issue', run.irac.issue],
              ['Rule', run.irac.rule],
              ['Application', run.irac.application],
              ['Conclusion', run.irac.conclusion],
            ] as const
          ).map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs uppercase tracking-wider text-slate-500">
                {label}
              </dt>
              <dd className="mt-1 whitespace-pre-wrap text-slate-300">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      {run.precedents.precedents.length > 0 && (
        <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6">
          <h2 className="text-sm font-semibold text-slate-200">Precedents</h2>
          <ul className="mt-3 space-y-2 text-sm text-slate-300">
            {run.precedents.precedents.map((p) => (
              <li key={p.case_id || p.title}>
                <a
                  href={p.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-300 underline-offset-2 hover:underline"
                >
                  {p.title}
                </a>{' '}
                <span className="text-slate-500">
                  {p.court}
                  {p.year ? ` (${p.year})` : ''}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="text-xs text-slate-500">
        Shared run <code className="text-slate-400">{run.id}</code>
        {run.created_at ? ` · analysed ${run.created_at}` : ''}
      </p>
    </div>
  )
}
