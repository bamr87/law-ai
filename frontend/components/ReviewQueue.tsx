'use client'

import {
  approveReview,
  fetchReview,
  fetchReviews,
  rejectReview,
  type ReviewDetail,
  type ReviewQueue as ReviewQueueBody,
  type ReviewRow,
  type ReviewStatus,
} from '@/lib/api'
import { useCallback, useEffect, useState } from 'react'

/**
 * Web surface for the ingestion quarantine queue (BL-20260811-01).
 *
 * Spec 029 closed the HITL loop with Django admin and a management command —
 * both operator-only. This is the half a domain reviewer can actually use:
 * pick a row, read *why* it was quarantined and what the extractor produced,
 * then approve or reject with a rationale.
 *
 * Two deliberate choices:
 *
 * - **A rationale is required to reject.** An audit trail that records "no"
 *   without a reason is not an audit trail (constitution §4).
 * - **A failed commit is shown, not swallowed.** An approved row whose graph
 *   write threw is *not* in the corpus, and that is precisely the state a
 *   reviewer must be able to see and act on.
 */

const STATUS_TABS: { key: ReviewStatus; label: string; hint: string }[] = [
  { key: 'pending', label: 'Pending', hint: 'Waiting on a human decision' },
  { key: 'failed', label: 'Needs attention', hint: 'Approved, but the graph write failed' },
  { key: 'committed', label: 'Committed', hint: 'Approved and written to the graph' },
  { key: 'rejected', label: 'Rejected', hint: 'Declined by a reviewer' },
]

interface Feedback {
  tone: 'ok' | 'warn' | 'error'
  text: string
}

export default function ReviewQueue() {
  const [status, setStatus] = useState<ReviewStatus>('pending')
  const [queue, setQueue] = useState<ReviewQueueBody | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ReviewDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

  const [reviewer, setReviewer] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<Feedback | null>(null)

  // Nothing is set before the first `await`: a synchronous setState inside the
  // mount effect cascades a render (and eslint's set-state-in-effect rule says
  // so). The skeleton is armed by the tab click, which is an event, not an
  // effect.
  const load = useCallback(async (next: ReviewStatus) => {
    try {
      const body = await fetchReviews(next)
      setQueue(body)
      setError(null)
    } catch (err) {
      setQueue(null)
      setError(err instanceof Error ? err.message : 'request failed')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(status)
  }, [load, status])

  const open = useCallback(async (id: string) => {
    setSelectedId(id)
    setDetail(null)
    setDetailError(null)
    setFeedback(null)
    try {
      setDetail(await fetchReview(id))
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : 'request failed')
    }
  }, [])

  const decide = useCallback(
    async (verb: 'approve' | 'reject') => {
      if (!selectedId) return
      if (verb === 'reject' && !note.trim()) {
        setFeedback({
          tone: 'error',
          text: 'A rejection needs a rationale — the audit trail records why, not just no.',
        })
        return
      }
      setBusy(true)
      setFeedback(null)
      try {
        const body = { reviewer: reviewer.trim(), note: note.trim() }
        const result =
          verb === 'approve'
            ? await approveReview(selectedId, body)
            : await rejectReview(selectedId, body)
        if (verb === 'reject') {
          setFeedback({ tone: 'ok', text: 'Rejected. Nothing was written to the graph.' })
        } else if (result.committed) {
          setFeedback({
            tone: 'ok',
            text: `Approved and committed${result.edges ? ` (${result.edges} edge(s))` : ''}.`,
          })
        } else {
          setFeedback({
            tone: 'warn',
            text:
              result.commit_error ||
              'Approved, but the item did not reach the graph. It stays in “Needs attention”.',
          })
        }
        setNote('')
        setDetail({ ...(detail as ReviewDetail), ...result.review })
        await load(status)
      } catch (err) {
        setFeedback({
          tone: 'error',
          text: err instanceof Error ? err.message : 'request failed',
        })
      } finally {
        setBusy(false)
      }
    },
    [detail, load, note, reviewer, selectedId, status],
  )

  return (
    <div className="space-y-4">
      <nav aria-label="Quarantine queue filters" className="flex flex-wrap gap-2">
        {STATUS_TABS.map((tab) => {
          const count = queue?.counts?.[tab.key]
          const active = tab.key === status
          return (
            <button
              key={tab.key}
              type="button"
              title={tab.hint}
              aria-current={active ? 'true' : undefined}
              onClick={() => {
                if (tab.key === status) return
                setLoading(true)
                setStatus(tab.key)
                setSelectedId(null)
                setDetail(null)
              }}
              className={`rounded-md border px-3 py-1.5 text-xs font-medium ${
                active
                  ? 'border-slate-400 bg-slate-800 text-slate-100'
                  : 'border-slate-700 text-slate-300 hover:border-slate-500 hover:bg-slate-800'
              }`}
            >
              {tab.label}
              {typeof count === 'number' ? ` (${count})` : ''}
            </button>
          )
        })}
      </nav>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <section
          aria-label="Quarantined documents"
          className="rounded-xl border border-slate-800 bg-slate-900/40 p-4"
        >
          {loading && <p className="text-sm text-slate-500">Loading…</p>}
          {error && (
            <p
              role="alert"
              className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-sm text-red-300"
            >
              Failed to load the queue: {error}
            </p>
          )}
          {!loading && !error && queue && queue.reviews.length === 0 && (
            <p className="rounded-md border border-slate-700 bg-slate-800/40 p-3 text-sm text-slate-400">
              Nothing in “{STATUS_TABS.find((t) => t.key === status)?.label}”.
              An empty queue means no document is in this state — not that
              ingestion is idle.
            </p>
          )}
          {!loading && !error && queue && queue.reviews.length > 0 && (
            <ul className="space-y-2">
              {queue.reviews.map((row) => (
                <li key={row.id}>
                  <button
                    type="button"
                    onClick={() => void open(row.id)}
                    aria-current={row.id === selectedId ? 'true' : undefined}
                    className={`w-full rounded-md border p-3 text-left ${
                      row.id === selectedId
                        ? 'border-slate-400 bg-slate-800'
                        : 'border-slate-800 bg-slate-900/60 hover:border-slate-600'
                    }`}
                  >
                    <span className="block truncate font-mono text-xs text-slate-300">
                      {row.id}
                    </span>
                    <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                      <Chip>{row.kind}</Chip>
                      <Chip>{row.source}</Chip>
                      <Chip>confidence {row.confidence.toFixed(2)}</Chip>
                      <span>{row.reason || 'no reason recorded'}</span>
                    </span>
                    {row.commit_error && (
                      <span className="mt-1 block text-xs text-amber-300">
                        Commit failed — not in the graph
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section
          aria-label="Review detail"
          className="rounded-xl border border-slate-800 bg-slate-900/40 p-4"
        >
          {!selectedId && (
            <p className="text-sm text-slate-500">
              Select a document to see why it was quarantined and what the
              extractor produced.
            </p>
          )}
          {selectedId && detailError && (
            <p
              role="alert"
              className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-sm text-red-300"
            >
              Failed to load the document: {detailError}
            </p>
          )}
          {selectedId && !detail && !detailError && (
            <p className="text-sm text-slate-500">Loading document…</p>
          )}
          {detail && (
            <ReviewDetailPanel
              detail={detail}
              reviewer={reviewer}
              note={note}
              busy={busy}
              feedback={feedback}
              onReviewer={setReviewer}
              onNote={setNote}
              onDecide={decide}
            />
          )}
        </section>
      </div>
    </div>
  )
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded border border-slate-700 px-1.5 py-0.5 font-mono text-[11px] text-slate-300">
      {children}
    </span>
  )
}

function ReviewDetailPanel({
  detail,
  reviewer,
  note,
  busy,
  feedback,
  onReviewer,
  onNote,
  onDecide,
}: {
  detail: ReviewDetail
  reviewer: string
  note: string
  busy: boolean
  feedback: Feedback | null
  onReviewer: (value: string) => void
  onNote: (value: string) => void
  onDecide: (verb: 'approve' | 'reject') => void | Promise<void>
}) {
  const decided = detail.approved !== null
  return (
    <div className="space-y-3">
      <header>
        <h2 className="break-all font-mono text-sm text-slate-100">{detail.id}</h2>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-400">
          <Field label="Kind" value={detail.kind} />
          <Field label="Source" value={detail.source} />
          <Field label="Confidence" value={detail.confidence.toFixed(2)} />
          <Field label="Reason" value={detail.reason || 'not recorded'} />
          <Field
            label="Decision"
            value={
              detail.approved === null
                ? 'pending'
                : detail.approved
                  ? 'approved'
                  : 'rejected'
            }
          />
          <Field label="Reviewer" value={detail.reviewer || 'unattributed'} />
        </dl>
        {detail.review_note && (
          <p className="mt-2 text-xs text-slate-300">
            <span className="text-slate-500">Rationale: </span>
            {detail.review_note}
          </p>
        )}
      </header>

      {detail.commit_error && (
        <p
          role="alert"
          className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200"
        >
          Approved, but the graph write failed, so this item is <em>not</em> in
          the corpus: {detail.commit_error}
        </p>
      )}

      <details className="rounded-md border border-slate-800 bg-slate-950/60">
        <summary className="cursor-pointer px-3 py-2 text-xs text-slate-300">
          Extracted payload
        </summary>
        <pre className="max-h-80 overflow-auto px-3 pb-3 font-mono text-[11px] leading-relaxed text-slate-300">
          {JSON.stringify(detail.payload, null, 2)}
        </pre>
      </details>

      <div className="space-y-2">
        <label className="block text-xs text-slate-400" htmlFor="review-reviewer">
          Reviewer (ignored when you are signed in — your account is used)
        </label>
        <input
          id="review-reviewer"
          value={reviewer}
          onChange={(e) => onReviewer(e.target.value)}
          className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100"
        />
        <label className="block text-xs text-slate-400" htmlFor="review-note">
          Rationale (required to reject)
        </label>
        <textarea
          id="review-note"
          value={note}
          rows={3}
          onChange={(e) => onNote(e.target.value)}
          className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100"
        />
      </div>

      {feedback && (
        <p
          role="status"
          className={`rounded-md border p-2 text-xs ${
            feedback.tone === 'ok'
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
              : feedback.tone === 'warn'
                ? 'border-amber-500/40 bg-amber-500/10 text-amber-200'
                : 'border-red-500/40 bg-red-500/10 text-red-200'
          }`}
        >
          {feedback.text}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void onDecide('approve')}
          className="rounded-md border border-emerald-500/50 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
        >
          {decided && detail.approved ? 'Re-commit' : 'Approve & commit'}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void onDecide('reject')}
          className="rounded-md border border-red-500/50 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-200 hover:bg-red-500/20 disabled:opacity-50"
        >
          Reject
        </button>
      </div>
      <p className="text-[11px] text-slate-500">
        Approving writes to the knowledge graph through the same audited
        service the admin actions and <code>manage.py review_queue</code> use.
        Every decision is recorded with who made it and why.
      </p>
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-slate-500">{label}</dt>
      <dd className="truncate text-slate-200">{value}</dd>
    </>
  )
}
