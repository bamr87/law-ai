'use client'

import { useCallback, useState } from 'react'

import { deleteAccount, fetchAccountExport } from '@/lib/api'

/**
 * Take your data, or leave (BL-20260817-01).
 *
 * The export is rendered in the page rather than pushed as a download,
 * because a JSON bundle a user can read before saving is a better answer to
 * "what do you hold about me" than a file that lands in Downloads unseen.
 *
 * Deletion asks for the username back and says plainly what survives: audit
 * records of decisions the account made are kept and de-identified
 * (constitution §4), because rewriting history is not a privacy feature.
 */
export default function AccountData() {
  const [bundle, setBundle] = useState<string | null>(null)
  const [confirm, setConfirm] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const doExport = useCallback(async () => {
    setBusy(true)
    try {
      setBundle(JSON.stringify(await fetchAccountExport(), null, 2))
      setStatus(null)
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setBusy(false)
    }
  }, [])

  const doDelete = useCallback(async () => {
    setBusy(true)
    try {
      await deleteAccount(confirm)
      setStatus(
        'Account deleted. Your matters are archived and your sign-in no longer works.',
      )
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Deletion failed')
    } finally {
      setBusy(false)
    }
  }, [confirm])

  return (
    <section className="space-y-4">
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Export everything
        </h3>
        <p className="mt-1 text-xs text-slate-400">
          One JSON bundle: every matter, its artifacts with their provenance
          trace ids, authorities, tasks and timeline.
        </p>
        <button
          type="button"
          onClick={doExport}
          disabled={busy}
          className="mt-3 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:border-amber-400 disabled:opacity-50"
        >
          Build export
        </button>
        {bundle && (
          <pre className="mt-3 max-h-72 overflow-auto rounded-lg bg-slate-950/60 p-3 text-[11px] text-slate-300">
            {bundle}
          </pre>
        )}
      </div>

      <div className="rounded-2xl border border-rose-900/60 bg-slate-900/40 p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-rose-300">
          Delete this account
        </h3>
        <p className="mt-1 text-xs text-slate-400">
          Your matters are archived, your API tokens revoked, your share links
          killed and your study history erased. Records of decisions the
          account made stay in the audit log, de-identified — an audit trail
          that could be rewritten would not be one.
        </p>
        <label className="mt-3 block text-xs text-slate-400">
          Type your username to confirm
          <input
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950/60 px-2 py-1 text-sm text-slate-200"
          />
        </label>
        <button
          type="button"
          onClick={doDelete}
          disabled={busy || confirm.trim() === ''}
          className="mt-3 rounded-lg border border-rose-800 px-3 py-1.5 text-xs text-rose-300 hover:border-rose-500 disabled:opacity-50"
        >
          Delete account
        </button>
      </div>

      {status && (
        <p role="status" className="text-xs text-slate-400">
          {status}
        </p>
      )}
    </section>
  )
}
