'use client'

/**
 * Authoring panel — the HITL queue for AI-drafted questions and solve guides
 * (spec 019 FR-12, spec 045).
 *
 * Moved out of `LsatLab.tsx` unchanged in phase 1 of BL-20260830-02.
 *
 * static-parity: none — authoring is a reviewer surface over the proposal
 * API and the agent runtime; the published static site is read-only by
 * design (spec 025).
 */

import { useCallback, useEffect, useState } from 'react'

import {
  approveLsatProposal,
  fetchLsatFactoryStatus,
  fetchLsatGaps,
  fetchLsatProposals,
  generateLsatProposals,
  rejectLsatProposal,
  type LsatDifficulty,
  type LsatFactoryStatus,
  type LsatCrossCheckProposalDraft,
  type LsatDraftReview,
  type LsatGapRow,
  type LsatGuideProposalDraft,
  type LsatGuideReview,
  type LsatProposal,
  type LsatProposalDraft,
  type LsatSection,
} from '@/lib/api'
import { ErrorBanner } from '@/components/lsat/LabPrimitives'
import ValidationReport from '@/components/lsat/ValidationReport'

export default function AuthoringPanel() {
  const [pending, setPending] = useState<LsatProposal[]>([])
  const [gaps, setGaps] = useState<LsatGapRow[]>([])
  // The factory's own view of what the next batch will target
  // (BL-20260702-06). Loaded beside the queue but never allowed to break it:
  // the reviewer's job is the drafts in front of them, and a coverage snapshot
  // that failed to load is not a reason to hide the queue.
  const [factory, setFactory] = useState<LsatFactoryStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [section, setSection] = useState<LsatSection>('LR')
  const [difficulty, setDifficulty] = useState<LsatDifficulty>('med')
  const [count, setCount] = useState(1)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [p, g] = await Promise.all([
        fetchLsatProposals('pending', 50),
        fetchLsatGaps(10),
      ])
      setPending(p.proposals)
      setGaps(g.gaps)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load proposals')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Separate from `refresh`, and silent on failure: `status()` loads the whole
  // bank and lists 500 proposals, so it is a page-load snapshot rather than
  // something to re-run after every approval.
  useEffect(() => {
    let live = true
    void (async () => {
      try {
        const body = await fetchLsatFactoryStatus()
        if (live) setFactory(body)
      } catch {
        /* the queue is the point; the snapshot is context */
      }
    })()
    return () => {
      live = false
    }
  }, [])

  const onGenerate = useCallback(async () => {
    setGenerating(true)
    setError(null)
    try {
      await generateLsatProposals({ section, difficulty, count })
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }, [section, difficulty, count, refresh])

  const onApprove = useCallback(
    async (id: string) => {
      setBusy(id)
      try {
        await approveLsatProposal(id)
        setPending((rows) => rows.filter((r) => r.id !== id))
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Approve failed')
      } finally {
        setBusy(null)
      }
    },
    [],
  )

  const onReject = useCallback(async (id: string) => {
    setBusy(id)
    try {
      await rejectLsatProposal(id)
      setPending((rows) => rows.filter((r) => r.id !== id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Reject failed')
    } finally {
      setBusy(null)
    }
  }, [])

  return (
    <section className="space-y-6">
      {/* Spec 045 FR-15: question-set accuracy review. */}
      <ValidationReport />

      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur">
        <div className="text-xs uppercase tracking-wider text-amber-400">
          Human-in-the-loop
        </div>
        <h2 className="mt-1 text-2xl font-semibold text-slate-100">
          Authoring queue
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-400">
          The <code className="text-slate-300">LSATContentAuthor</code> agent
          drafts new questions targeting the concepts where learners score
          lowest. Every draft lands here for human review before it joins the
          live question bank.
        </p>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          Generate new draft
        </h3>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-xs text-slate-400">
            Section
            <select
              value={section}
              onChange={(e) => setSection(e.target.value as LsatSection)}
              className="mt-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
            >
              <option value="LR">Logical Reasoning</option>
              <option value="RC">Reading Comprehension</option>
              <option value="LG">Logic Games</option>
            </select>
          </label>
          <label className="flex flex-col text-xs text-slate-400">
            Difficulty
            <select
              value={difficulty}
              onChange={(e) =>
                setDifficulty(e.target.value as LsatDifficulty)
              }
              className="mt-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
            >
              <option value="easy">Easy</option>
              <option value="med">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </label>
          <label className="flex flex-col text-xs text-slate-400">
            Count
            <input
              type="number"
              min={1}
              max={10}
              value={count}
              onChange={(e) =>
                setCount(Math.max(1, Math.min(10, Number(e.target.value) || 1)))
              }
              className="mt-1 w-24 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
            />
          </label>
          <button
            onClick={() => void onGenerate()}
            disabled={generating}
            className="rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-blue-500/20 transition disabled:cursor-not-allowed disabled:opacity-50"
          >
            {generating ? 'Drafting…' : 'Draft questions'}
          </button>
        </div>
      </div>

      <FactoryStatusCard status={factory} />

      {gaps.length > 0 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            Weakest measured concepts
          </h3>
          <p className="mt-1 text-xs text-slate-500">
            Tomorrow&apos;s autonomy cycle will target the top row.
          </p>
          <table className="mt-3 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="py-2 pr-4">Section</th>
                <th className="py-2 pr-4">Concept</th>
                <th className="py-2 pr-4">Attempts</th>
                <th className="py-2 pr-4">Accuracy</th>
              </tr>
            </thead>
            <tbody>
              {gaps.map((g, i) => (
                <tr
                  key={`${g.section}-${g.concept}-${i}`}
                  className="border-t border-slate-800/70 text-slate-300"
                >
                  <td className="py-2 pr-4 font-mono text-xs">{g.section}</td>
                  <td className="py-2 pr-4">{g.concept}</td>
                  <td className="py-2 pr-4">{g.attempts}</td>
                  <td className="py-2 pr-4">
                    {Math.round(g.accuracy * 100)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {error && <ErrorBanner message={error} onRetry={refresh} />}

      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            Pending review ({pending.length})
          </h3>
          <button
            onClick={() => void refresh()}
            className="text-xs text-blue-400 hover:text-blue-300"
          >
            Refresh
          </button>
        </div>
        {loading ? (
          <div className="mt-4 text-sm text-slate-500">Loading…</div>
        ) : pending.length === 0 ? (
          <div className="mt-4 text-sm text-slate-500">
            No drafts waiting for review.
          </div>
        ) : (
          <div className="mt-4 space-y-4">
            {pending.map((p) => (
              <ProposalCard
                key={p.id}
                proposal={p}
                busy={busy === p.id}
                onApprove={() => void onApprove(p.id)}
                onReject={() => void onReject(p.id)}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

/**
 * Factory status — what the next batch will target (BL-20260702-06).
 *
 * The Authoring queue showed the drafts and the weakest measured concepts, and
 * nothing about the machine that produced them: no coverage matrix, no
 * manifest, no gate counts. A reviewer approving a `weaken / hard` draft could
 * not tell whether that cell was the worst hole in the bank or already full.
 *
 * Rendered from one page-load snapshot. `factory.status()` loads the whole
 * bank and lists 500 proposals, so this is deliberately not on a timer.
 */
function FactoryStatusCard({ status }: { status: LsatFactoryStatus | null }) {
  if (!status) return null
  const sections = Object.entries(status.bank_by_section).sort()
  const executors = Object.entries(status.pending_gates.by_executor).sort(
    (a, b) => b[1] - a[1],
  )
  const manifest = status.latest_manifest_summary
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
        Factory status
      </h3>
      <p className="mt-1 text-xs text-slate-500">
        The coverage the next batch is planned against — a snapshot taken when
        this tab opened.
      </p>

      <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <FactoryStat label="Questions in bank" value={status.bank_total} />
        <FactoryStat label="Writing prompts" value={status.writing_prompts} />
        <FactoryStat
          label="Cells with a deficit"
          value={`${status.cells_with_deficit} / ${status.coverage_cells}`}
        />
        <FactoryStat
          label="Pending from the factory"
          value={`${status.pending_from_factory} / ${status.pending_proposals}`}
        />
      </dl>

      {sections.length > 0 && (
        <p className="mt-3 text-xs text-slate-500">
          By section: {sections.map(([code, n]) => `${code} ${n}`).join(' · ')}
        </p>
      )}

      {status.top_deficits.length > 0 && (
        <>
          <h4 className="mt-5 text-xs font-semibold uppercase tracking-wider text-slate-400">
            Next batch targets
          </h4>
          <table className="mt-2 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="py-1 pr-4">Archetype</th>
                <th className="py-1 pr-4">Difficulty</th>
                <th className="py-1 pr-4">Have</th>
                <th className="py-1 pr-4">Want</th>
              </tr>
            </thead>
            <tbody>
              {status.top_deficits.slice(0, 5).map((cell) => (
                <tr
                  key={`${cell.archetype_id}-${cell.difficulty}`}
                  className="border-t border-slate-800/70 text-slate-300"
                >
                  <td className="py-1 pr-4 font-mono text-xs">
                    {cell.archetype_id}
                  </td>
                  <td className="py-1 pr-4">{cell.difficulty}</td>
                  <td className="py-1 pr-4 tabular-nums">{cell.have}</td>
                  <td className="py-1 pr-4 tabular-nums">{cell.want}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <p className="mt-4 text-xs text-slate-500">
        {manifest ? (
          <>
            Last manifest{' '}
            <code className="rounded bg-slate-950/60 px-1 py-0.5 text-slate-300">
              {manifest.manifest_id}
            </code>{' '}
            · {manifest.jobs} job{manifest.jobs === 1 ? '' : 's'} ·{' '}
            {Object.entries(manifest.by_tier)
              .sort()
              .map(([tier, n]) => `${tier} ${n}`)
              .join(' · ')}
          </>
        ) : (
          'No generation manifest has been written yet.'
        )}
      </p>
      {(executors.length > 0 ||
        status.pending_gates.answer_balance_flagged > 0) && (
        <p className="mt-1 text-xs text-slate-500">
          Queued drafts:{' '}
          {executors.length > 0
            ? executors.map(([name, n]) => `${name} ×${n}`).join(' · ')
            : 'none'}
          {status.pending_gates.answer_balance_flagged > 0 && (
            <span className="ml-2 rounded-full bg-amber-500/15 px-2 py-0.5 text-amber-200">
              {status.pending_gates.answer_balance_flagged} flagged for answer
              balance
            </span>
          )}
        </p>
      )}
    </div>
  )
}

function FactoryStat({
  label,
  value,
}: {
  label: string
  value: string | number
}) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wider text-slate-500">
        {label}
      </dt>
      <dd className="mt-0.5 text-lg font-semibold tabular-nums text-slate-100">
        {value}
      </dd>
    </div>
  )
}

/**
 * Blind pre-review badge (BL-20260527-04).
 *
 * Advisory only: a flagged draft is still approvable and a clean one is still
 * a draft. The badge exists so a reviewer with fifty pending rows knows which
 * five to open first.
 */
export function DraftReviewBadge({ review }: { review: LsatDraftReview }) {
  if (review.degraded) {
    return (
      <span
        title={review.rationale}
        className="rounded-md bg-slate-800 px-2 py-0.5 text-[10px] uppercase tracking-wider text-slate-400"
      >
        not reviewed
      </span>
    )
  }
  return (
    <span
      title={review.rationale}
      className={
        review.flagged
          ? 'rounded-md bg-amber-900/60 px-2 py-0.5 text-[10px] uppercase tracking-wider text-amber-300'
          : 'rounded-md bg-slate-800 px-2 py-0.5 text-[10px] uppercase tracking-wider text-slate-400'
      }
    >
      {review.flagged ? 'pre-flagged ' : 'review '}
      {(review.overall * 100).toFixed(0)}%
      {review.flags.length > 0 && ` · ${review.flags.join(', ')}`}
    </span>
  )
}

/**
 * Judge-tier verdict on a solve-guide draft (BL-20260830-15).
 *
 * Advisory: `pass` does not promote and `reject` does not delete — a human
 * editor still decides. `unreviewed` means no provider answered, which must
 * never read as approval.
 */
export function GuideReviewPanel({ review }: { review: LsatGuideReview }) {
  const broken = review.step_findings.filter((f) => !f.follows)
  const tone =
    review.verdict === 'pass'
      ? 'text-emerald-300'
      : review.verdict === 'unreviewed'
        ? 'text-slate-400'
        : 'text-amber-300'
  return (
    <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="uppercase tracking-wider text-slate-500">
          Pedagogical review
        </span>
        <span className={`font-semibold uppercase ${tone}`}>{review.verdict}</span>
        {!review.symbolization_faithful && (
          <span className="rounded-md bg-amber-900/60 px-2 py-0.5 text-amber-300">
            symbolization unfaithful
          </span>
        )}
        <span className="text-slate-600">·</span>
        <span className="text-slate-500">{review.model}</span>
      </div>
      {review.summary && <p className="mt-1 text-slate-400">{review.summary}</p>}
      {broken.length > 0 && (
        <ul className="mt-2 space-y-1 text-amber-300">
          {broken.map((f) => (
            <li key={f.index}>
              <span className="font-mono">step {f.index}:</span> {f.note || 'does not follow'}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function ProposalCard({
  proposal,
  busy,
  onApprove,
  onReject,
}: {
  proposal: LsatProposal
  busy: boolean
  onApprove: () => void
  onReject: () => void
}) {
  // Spec 045: guide drafts share the queue but have a different shape.
  if (proposal.proposal_kind === 'guide') {
    const g = proposal.draft as LsatGuideProposalDraft
    const guideReview = (proposal.meta?.review ?? null) as LsatGuideReview | null
    return (
      <article className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
        <header className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-md bg-sky-900/60 px-2 py-0.5 font-mono text-sky-300">
            solve guide
          </span>
          <span className="rounded-md bg-slate-800 px-2 py-0.5 font-mono text-slate-300">
            {g.question_id}
          </span>
          <span className="text-slate-500">
            confidence {(proposal.confidence * 100).toFixed(0)}%
          </span>
          <span className="text-slate-600">·</span>
          <span className="text-slate-500">{proposal.model}</span>
          <span className="ml-auto font-mono text-slate-600">{proposal.id}</span>
        </header>
        <p className="mt-3 text-sm font-medium text-slate-200">{g.method}</p>
        <ol className="mt-2 space-y-2 text-sm">
          {g.steps.map((s, i) => (
            <li key={i} className="text-slate-400">
              <span className="font-mono text-slate-500">{i + 1}.</span>{' '}
              <span className="uppercase text-[10px] tracking-wider text-sky-300">
                {s.kind}
              </span>{' '}
              <span className="text-slate-300">{s.title}</span>
              {s.spoiler && (
                <span className="ml-1 text-[10px] uppercase text-amber-400">
                  spoiler
                </span>
              )}
              <p className="mt-0.5 whitespace-pre-wrap text-xs text-slate-500">
                {s.text}
              </p>
            </li>
          ))}
        </ol>
        {guideReview && <GuideReviewPanel review={guideReview} />}
        <footer className="mt-4 flex items-center justify-end gap-2">
          <button
            onClick={onReject}
            disabled={busy}
            className="rounded-md border border-red-700/60 px-3 py-1.5 text-xs font-semibold text-red-300 hover:bg-red-900/40 disabled:opacity-50"
          >
            Reject
          </button>
          <button
            onClick={onApprove}
            disabled={busy}
            className="rounded-md border border-emerald-700/60 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-900/40 disabled:opacity-50"
          >
            Approve → guides
          </button>
        </footer>
      </article>
    )
  }

  // BL-20260831-21: a cross-check row is a disagreement report, not a draft.
  // Approving it says the key is right; rejecting it says the question needs
  // an edit. Neither writes content, so it gets its own compact card.
  if (proposal.proposal_kind === 'crosscheck') {
    const c = proposal.draft as LsatCrossCheckProposalDraft
    return (
      <article className="rounded-xl border border-amber-800/60 bg-slate-950/60 p-4">
        <header className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-md bg-amber-900/60 px-2 py-0.5 font-mono text-amber-300">
            cross-check
          </span>
          <span className="rounded-md bg-slate-800 px-2 py-0.5 font-mono text-slate-300">
            {c.question_id}
          </span>
          <span className="text-slate-500">{c.model}</span>
          <span className="ml-auto font-mono text-slate-600">{proposal.id}</span>
        </header>
        <p className="mt-3 text-sm text-slate-300">
          Key says <span className="font-mono text-emerald-400">{c.bank_choice}</span>
          ; the chain answered{' '}
          <span className="font-mono text-amber-300">{c.model_choice ?? '—'}</span>.
        </p>
        <div className="mt-2 whitespace-pre-wrap text-sm text-slate-400">{c.stem}</div>
        <details className="mt-3 text-sm text-slate-400">
          <summary className="cursor-pointer text-slate-300">
            Model&apos;s reasoning
          </summary>
          <p className="mt-2 whitespace-pre-wrap">{c.rationale}</p>
        </details>
        <footer className="mt-4 flex items-center justify-end gap-2">
          <button
            onClick={onReject}
            disabled={busy}
            className="rounded-md border border-red-700/60 px-3 py-1.5 text-xs font-semibold text-red-300 hover:bg-red-900/40 disabled:opacity-50"
          >
            Key is wrong
          </button>
          <button
            onClick={onApprove}
            disabled={busy}
            className="rounded-md border border-emerald-700/60 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-900/40 disabled:opacity-50"
          >
            Key verified
          </button>
        </footer>
      </article>
    )
  }

  const d = proposal.draft as LsatProposalDraft
  // A question proposal's review is always the draft shape; the union exists
  // because guide proposals share the `meta.review` slot.
  const rawReview = proposal.meta?.review ?? null
  const review =
    rawReview && 'overall' in rawReview ? (rawReview as LsatDraftReview) : null
  return (
    <article
      className={
        review?.flagged
          ? 'rounded-xl border border-amber-800/60 bg-slate-950/60 p-4'
          : 'rounded-xl border border-slate-800 bg-slate-950/60 p-4'
      }
    >
      <header className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-md bg-slate-800 px-2 py-0.5 font-mono text-slate-300">
          {d.section}
        </span>
        {review && <DraftReviewBadge review={review} />}
        <span className="rounded-md bg-slate-800 px-2 py-0.5 text-slate-300">
          {d.difficulty}
        </span>
        <span className="text-slate-500">
          confidence {(proposal.confidence * 100).toFixed(0)}%
        </span>
        <span className="text-slate-600">·</span>
        <span className="text-slate-500">{proposal.model}</span>
        <span className="ml-auto font-mono text-slate-600">{proposal.id}</span>
      </header>
      <div className="mt-3 whitespace-pre-wrap text-sm text-slate-200">
        {d.stem}
      </div>
      <ol className="mt-3 space-y-1 text-sm">
        {d.choices.map((c) => (
          <li
            key={c.label}
            className={
              c.label === d.correct
                ? 'text-emerald-400'
                : 'text-slate-400'
            }
          >
            <span className="font-mono">{c.label}.</span> {c.text}
            {c.label === d.correct && (
              <span className="ml-2 text-xs uppercase tracking-wider">
                correct
              </span>
            )}
          </li>
        ))}
      </ol>
      <details className="mt-3 text-sm text-slate-400">
        <summary className="cursor-pointer text-slate-300">Explanation</summary>
        <p className="mt-2 whitespace-pre-wrap">{d.explanation}</p>
      </details>
      <footer className="mt-4 flex items-center justify-end gap-2">
        <button
          onClick={onReject}
          disabled={busy}
          className="rounded-md border border-red-700/60 px-3 py-1.5 text-xs font-semibold text-red-300 hover:bg-red-900/40 disabled:opacity-50"
        >
          Reject
        </button>
        <button
          onClick={onApprove}
          disabled={busy}
          className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {busy ? 'Working…' : 'Approve & promote'}
        </button>
      </footer>
    </article>
  )
}
