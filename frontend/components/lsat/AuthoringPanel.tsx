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

import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  approveLsatProposal,
  fetchLsatFactoryStatus,
  fetchLsatGaps,
  fetchLsatProposals,
  draftLsatVariation,
  fetchLsatPlaybooks,
  generateLsatProposals,
  promoteLsatPassage,
  rejectLsatProposal,
  type LsatDifficulty,
  type LsatFactoryStatus,
  type LsatCrossCheckProposalDraft,
  type LsatDiagnosisOption,
  type LsatRewriteProposalDraft,
  type LsatTypeCheckProposalDraft,
  type LsatWritingProposalDraft,
  type LsatDraftReview,
  type LsatGapRow,
  type LsatGuideProposalDraft,
  type LsatGuideReview,
  type LsatJudgeVerdict,
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

  // Spec 054: draft a contrast variation of one bank question through the
  // author → gates → judge → revise loop. Same queue, same review.
  const [varSource, setVarSource] = useState('lr-002')
  const [varTarget, setVarTarget] = useState('')
  const [types, setTypes] = useState<LsatDiagnosisOption[]>([])
  const [varBusy, setVarBusy] = useState(false)
  const [varNote, setVarNote] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    fetchLsatPlaybooks('LR')
      .then((b) => {
        if (!live) return
        const opts = b.playbooks.map((pb) => ({ id: pb.archetype_id, name: pb.name }))
        setTypes(opts)
        setVarTarget((t) => t || opts[0]?.id || '')
      })
      .catch(() => {
        /* the form still accepts a typed id */
      })
    return () => {
      live = false
    }
  }, [])
  const onDraftVariation = useCallback(async () => {
    if (!varSource.trim() || !varTarget) return
    setVarBusy(true)
    setVarNote(null)
    setError(null)
    try {
      const r = await draftLsatVariation(varSource.trim(), varTarget)
      setVarNote(
        `${r.proposal_id} filed after ${r.rounds} round${r.rounds === 1 ? '' : 's'}` +
          (r.accepted ? '.' : ' — not accepted by the gates/judge; review carefully.'),
      )
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Variation draft failed')
    } finally {
      setVarBusy(false)
    }
  }, [varSource, varTarget, refresh])

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

  // BL-20260905-56: a `passage_set` job's invented passage is parked, and
  // every draft from that job refuses promotion (409) until a reviewer
  // promotes it. Reloading afterwards is the point: the drafts come back
  // carrying the new passage_id.
  const onPromotePassage = useCallback(
    async (id: string, path: string) => {
      setBusy(id)
      try {
        await promoteLsatPassage(path)
        await refresh()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Passage promotion failed')
      } finally {
        setBusy(null)
      }
    },
    [refresh],
  )

  // BL-20260905-83: pre-flagged drafts sort to the top. A reviewer with fifty
  // rows should not scroll to find the five the blind review doubted; the
  // order within each group is the API's (newest first).
  const ordered = useMemo(
    () => [...pending].sort((a, b) => flagRank(a) - flagRank(b)),
    [pending],
  )

  // BL-20260905-45: a guide the factory drafted beside a still-pending
  // question names that *proposal*, so the question card can say a guide is
  // waiting with it instead of leaving the pair to be spotted by eye.
  const guidesByProposal = useMemo(() => {
    const map = new Map<string, string[]>()
    for (const row of pending) {
      const target = row.meta?.guide_for_proposal
      if (row.proposal_kind !== 'guide' || !target) continue
      map.set(target, [...(map.get(target) ?? []), row.id])
    }
    return map
  }, [pending])

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

      <div className="rounded-2xl border border-violet-500/30 bg-violet-500/5 p-6">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-violet-300">
          Draft a contrast variation
        </h3>
        <p className="mt-1 text-xs text-slate-400">
          Re-ask one bank question as a different type on the same stimulus.
          The draft goes through the gates and the judge, is revised on their
          objections, and lands here pending like anything else.
        </p>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-xs text-slate-400">
            Source question
            <input
              value={varSource}
              onChange={(e) => setVarSource(e.target.value)}
              className="mt-1 w-32 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-200"
            />
          </label>
          <label className="flex flex-col text-xs text-slate-400">
            Re-ask as
            <select
              value={varTarget}
              onChange={(e) => setVarTarget(e.target.value)}
              className="mt-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
            >
              {types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={() => void onDraftVariation()}
            disabled={varBusy || !varTarget}
            className="rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-violet-500/20 transition disabled:cursor-not-allowed disabled:opacity-50"
          >
            {varBusy ? 'Drafting and reviewing…' : 'Draft variation'}
          </button>
        </div>
        {varNote && (
          <p role="status" className="mt-2 text-xs text-slate-300">
            {varNote}
          </p>
        )}
      </div>

      <FactoryStatusCard status={factory} />

      {gaps.length > 0 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            Weakest measured concepts
          </h3>
          <p className="mt-1 text-xs text-slate-400">
            Tomorrow&apos;s autonomy cycle will target the top row.
          </p>
          <table className="mt-3 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-slate-400">
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
          <div className="mt-4 text-sm text-slate-400">Loading…</div>
        ) : pending.length === 0 ? (
          <div className="mt-4 text-sm text-slate-400">
            No drafts waiting for review.
          </div>
        ) : (
          <div className="mt-4 space-y-4">
            {ordered.map((p) => (
              <ProposalCard
                key={p.id}
                proposal={p}
                busy={busy === p.id}
                linkedGuideIds={guidesByProposal.get(p.id) ?? []}
                onApprove={() => void onApprove(p.id)}
                onReject={() => void onReject(p.id)}
                onPromotePassage={(path) => void onPromotePassage(p.id, path)}
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
      <p className="mt-1 text-xs text-slate-400">
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
        <p className="mt-3 text-xs text-slate-400">
          By section: {sections.map(([code, n]) => `${code} ${n}`).join(' · ')}
        </p>
      )}

      {status.top_deficits.length > 0 && (
        <>
          <h4 className="mt-5 text-xs font-semibold uppercase tracking-wider text-slate-400">
            Next batch targets
          </h4>
          <table className="mt-2 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-slate-400">
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

      <p className="mt-4 text-xs text-slate-400">
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
        <p className="mt-1 text-xs text-slate-400">
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
      <dt className="text-[11px] uppercase tracking-wider text-slate-400">
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
        <span className="uppercase tracking-wider text-slate-400">
          Pedagogical review
        </span>
        <span className={`font-semibold uppercase ${tone}`}>{review.verdict}</span>
        {!review.symbolization_faithful && (
          <span className="rounded-md bg-amber-900/60 px-2 py-0.5 text-amber-300">
            symbolization unfaithful
          </span>
        )}
        <span className="text-slate-600">·</span>
        <span className="text-slate-400">{review.model}</span>
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

/**
 * Judge-tier verdict on a drafted question (BL-20260702-02).
 *
 * The factory's adversarial reviewer wrote an objection into
 * `meta.factory.judge` and nothing rendered it, so the reviewer re-derived it
 * by hand. Advisory, like every other badge here: `fail` does not reject.
 * A judge that disagreed with the drafted key is the loudest line on the card
 * because it is the one failure a human cannot spot by skimming.
 */
export function JudgeVerdictPanel({ verdict }: { verdict: LsatJudgeVerdict }) {
  if (verdict.degraded) {
    return (
      <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs text-slate-400">
        <span className="uppercase tracking-wider text-slate-400">Judge</span>{' '}
        not reviewed — no provider answered
      </div>
    )
  }
  const tone =
    verdict.verdict === 'pass'
      ? 'text-emerald-300'
      : verdict.verdict === 'flag'
        ? 'text-amber-300'
        : 'text-red-300'
  return (
    <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="uppercase tracking-wider text-slate-400">Judge</span>
        <span className={`font-semibold uppercase ${tone}`}>
          {verdict.verdict}
        </span>
        {verdict.key_agrees === false && (
          <span className="rounded-md bg-red-900/60 px-2 py-0.5 text-red-300">
            key disputed{verdict.solved_key ? ` · solved ${verdict.solved_key}` : ''}
          </span>
        )}
        {!verdict.single_best_answer && (
          <span className="rounded-md bg-amber-900/60 px-2 py-0.5 text-amber-300">
            second defensible choice
          </span>
        )}
        <span className="text-slate-600">·</span>
        <span className="text-slate-400">{verdict.model}</span>
      </div>
      {verdict.rationale && (
        <p className="mt-1 text-slate-400">{verdict.rationale}</p>
      )}
      {verdict.issues.length > 0 && (
        <ul className="mt-2 space-y-1 text-amber-300">
          {verdict.issues.map((issue, i) => (
            <li key={i}>{issue}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Pre-flagged rows first (BL-20260905-83); everything else keeps API order. */
function flagRank(proposal: LsatProposal): number {
  const review = proposal.meta?.review ?? null
  return review && 'flagged' in review && review.flagged ? 0 : 1
}

export function ProposalCard({
  proposal,
  busy,
  linkedGuideIds = [],
  onApprove,
  onReject,
  onPromotePassage,
}: {
  proposal: LsatProposal
  busy: boolean
  /** Pending guide drafts authored beside this question (BL-20260905-45). */
  linkedGuideIds?: string[]
  onApprove: () => void
  onReject: () => void
  /** Promote the passage this draft's job parked (BL-20260905-56). */
  onPromotePassage?: (pendingPassagePath: string) => void
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
          <span className="text-slate-400">
            confidence {(proposal.confidence * 100).toFixed(0)}%
          </span>
          <span className="text-slate-600">·</span>
          <span className="text-slate-400">{proposal.model}</span>
          <span className="ml-auto font-mono text-slate-600">{proposal.id}</span>
        </header>
        <p className="mt-3 text-sm font-medium text-slate-200">{g.method}</p>
        <ol className="mt-2 space-y-2 text-sm">
          {g.steps.map((s, i) => (
            <li key={i} className="text-slate-400">
              <span className="font-mono text-slate-400">{i + 1}.</span>{' '}
              <span className="uppercase text-[10px] tracking-wider text-sky-300">
                {s.kind}
              </span>{' '}
              <span className="text-slate-300">{s.title}</span>
              {s.spoiler && (
                <span className="ml-1 text-[10px] uppercase text-amber-400">
                  spoiler
                </span>
              )}
              <p className="mt-0.5 whitespace-pre-wrap text-xs text-slate-400">
                {s.text}
              </p>
            </li>
          ))}
        </ol>
        {proposal.meta?.guide_for_proposal && (
          <p className="mt-3 text-xs text-sky-300">
            Drafted with pending question{' '}
            <span className="font-mono text-slate-400">
              {proposal.meta.guide_for_proposal}
            </span>
          </p>
        )}
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

  // Spec 054: a rewrite replaces an existing item in place. Show the reviewer
  // what the judge objected to, what changed, and both versions side by side.
  if (proposal.proposal_kind === 'rewrite') {
    const r = proposal.draft as LsatRewriteProposalDraft
    const original = proposal.meta?.original_judge ?? null
    const final = proposal.meta?.final_review ?? null
    return (
      <article
        data-testid="rewrite-proposal-card"
        className="rounded-xl border border-sky-800/60 bg-slate-950/60 p-4"
      >
        <header className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-md bg-sky-900/60 px-2 py-0.5 font-mono text-sky-300">
            rewrite
          </span>
          <span className="rounded-md bg-slate-800 px-2 py-0.5 font-mono text-slate-300">
            {r.question_id}
          </span>
          <span className="text-slate-400">{proposal.model}</span>
          {final && <FinalReviewBadge verdict={final} />}
          <span className="ml-auto font-mono text-slate-600">{proposal.id}</span>
        </header>
        <p className="mt-3 text-sm text-slate-200">{r.change_summary}</p>
        {original && (
          <div className="mt-2 rounded-md border border-amber-800/60 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
            Judge on the original: <span className="font-mono">{original.verdict}</span>
            {original.key_agrees === false ? ' (blind key disagreed)' : ''}
            {original.issues.length > 0 && (
              <ul className="ml-4 mt-1 list-disc">
                {original.issues.map((i) => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        <div className="mt-3 whitespace-pre-wrap text-sm text-slate-300">{r.stem}</div>
        <ol className="mt-3 space-y-1 text-sm">
          {r.choices.map((c) => (
            <li
              key={c.label}
              className={c.label === r.correct ? 'text-emerald-300' : 'text-slate-300'}
            >
              <span className="mr-2 font-mono">{c.label}.</span>
              {c.text}
            </li>
          ))}
        </ol>
        <details className="mt-3 text-sm text-slate-400">
          <summary className="cursor-pointer text-slate-300">Explanation</summary>
          <p className="mt-2 whitespace-pre-wrap">{r.explanation}</p>
        </details>
        {proposal.meta?.revisions && <RevisionHistory revisions={proposal.meta.revisions} />}
        <footer className="mt-4 flex items-center justify-end gap-2">
          <button
            onClick={onReject}
            disabled={busy}
            className="rounded-md border border-slate-600 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            Keep original
          </button>
          <button
            onClick={onApprove}
            disabled={busy}
            className="rounded-md border border-emerald-700/60 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-900/40 disabled:opacity-50"
          >
            Approve &rarr; replace {r.question_id}
          </button>
        </footer>
      </article>
    )
  }

  // Spec 054: a type-check row is a disagreement about the question's type.
  // Approving it restamps the question with the model's read; rejecting it
  // keeps the stamp. Neither writes a question, so it has its own card.
  if (proposal.proposal_kind === 'typecheck') {
    const t = proposal.draft as LsatTypeCheckProposalDraft
    return (
      <article
        data-testid="typecheck-proposal-card"
        className="rounded-xl border border-violet-800/60 bg-slate-950/60 p-4"
      >
        <header className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-md bg-violet-900/60 px-2 py-0.5 font-mono text-violet-300">
            type check
          </span>
          <span className="rounded-md bg-slate-800 px-2 py-0.5 font-mono text-slate-300">
            {t.question_id}
          </span>
          <span className="text-slate-400">{t.model}</span>
          <span className="ml-auto font-mono text-slate-600">{proposal.id}</span>
        </header>
        <p className="mt-3 text-sm text-slate-300">
          Stamped <span className="font-mono text-emerald-400">{t.stamped_archetype ?? '—'}</span>
          ; the model read it as{' '}
          <span className="font-mono text-amber-300">{t.model_archetype}</span>
          {t.cue_archetype && t.cue_archetype !== t.stamped_archetype && (
            <>
              {' '}
              (stem cues say <span className="font-mono">{t.cue_archetype}</span>)
            </>
          )}
          .
        </p>
        <div className="mt-2 whitespace-pre-wrap text-sm text-slate-400">{t.stem}</div>
        <details className="mt-3 text-sm text-slate-400">
          <summary className="cursor-pointer text-slate-300">Model&apos;s reasoning</summary>
          <p className="mt-2 whitespace-pre-wrap">{t.rationale}</p>
        </details>
        <footer className="mt-4 flex items-center justify-end gap-2">
          <button
            onClick={onReject}
            disabled={busy}
            className="rounded-md border border-slate-600 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            Keep current stamp
          </button>
          <button
            onClick={onApprove}
            disabled={busy}
            className="rounded-md border border-amber-700/60 px-3 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-900/40 disabled:opacity-50"
          >
            Restamp as {t.model_archetype}
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
          <span className="text-slate-400">{c.model}</span>
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

  // BL-20260831-28: the factory drafts writing prompts into the same queue.
  // A WS draft has no `choices`, so without its own card it fell through to
  // the question card below and threw inside `d.choices.map`, taking the whole
  // review list down with it.
  if (proposal.proposal_kind === 'writing_prompt') {
    const w = proposal.draft as LsatWritingProposalDraft
    return (
      <article
        data-testid="writing-proposal-card"
        className="rounded-xl border border-violet-800/60 bg-slate-950/60 p-4"
      >
        <header className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-md bg-violet-900/60 px-2 py-0.5 font-mono text-violet-300">
            writing prompt
          </span>
          {w.difficulty && (
            <span className="rounded-md bg-slate-800 px-2 py-0.5 text-slate-300">
              {w.difficulty}
            </span>
          )}
          <span className="text-slate-400">{proposal.model}</span>
          <span className="ml-auto font-mono text-slate-600">{proposal.id}</span>
        </header>
        <p className="mt-3 text-sm font-medium text-slate-200">{w.title}</p>
        <p className="mt-1 text-sm text-slate-300">{w.issue}</p>
        <p className="mt-2 whitespace-pre-wrap text-sm text-slate-400">{w.context}</p>
        <ul className="mt-3 space-y-1 text-sm">
          {(w.positions ?? []).map((pos) => (
            <li key={pos.id} className="text-slate-400">
              <span className="font-mono text-slate-400">{pos.id}</span>{' '}
              <span className="text-slate-300">{pos.name}</span> — {pos.summary}
            </li>
          ))}
        </ul>
        <details className="mt-3 text-sm text-slate-400">
          <summary className="cursor-pointer text-slate-300">
            Perspectives &amp; task
          </summary>
          <ol className="mt-2 space-y-1">
            {(w.perspectives ?? []).map((pv) => (
              <li key={pv.id}>{pv.text}</li>
            ))}
          </ol>
          <p className="mt-2 whitespace-pre-wrap text-slate-300">{w.task}</p>
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
            className="rounded-md border border-emerald-700/60 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-900/40 disabled:opacity-50"
          >
            Approve &rarr; writing library
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
  const judge = proposal.meta?.factory?.judge ?? null
  // BL-20260905-56: a parked passage still blocks this draft's promotion.
  const pendingPassage = d.passage_id
    ? null
    : (proposal.meta?.factory?.pending_passage_path ?? null)
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
        {proposal.meta?.variation_of && (
          <span
            className="rounded-md bg-violet-900/60 px-2 py-0.5 font-mono text-violet-200"
            title="Contrast variation: same stimulus as the named question, re-asked as a different type"
          >
            variation of {proposal.meta.variation_of}
            {proposal.meta.factory?.archetype_id
              ? ` → ${String(proposal.meta.factory.archetype_id)}`
              : ''}
          </span>
        )}
        {proposal.meta?.final_review && (
          <FinalReviewBadge verdict={proposal.meta.final_review} />
        )}
        <span className="text-slate-400">
          confidence {(proposal.confidence * 100).toFixed(0)}%
        </span>
        <span className="text-slate-600">·</span>
        <span className="text-slate-400">{proposal.model}</span>
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
      {judge && <JudgeVerdictPanel verdict={judge} />}
      {proposal.meta?.revisions && (
        <RevisionHistory revisions={proposal.meta.revisions} />
      )}
      {linkedGuideIds.length > 0 && (
        <p className="mt-3 text-xs text-sky-300">
          {linkedGuideIds.length === 1
            ? '1 solve guide drafted with this item'
            : `${linkedGuideIds.length} solve guides drafted with this item`}
          {' · '}
          <span className="font-mono text-slate-400">
            {linkedGuideIds.join(', ')}
          </span>
        </p>
      )}
      {pendingPassage && (
        <div className="mt-3 rounded-lg border border-amber-800/60 bg-amber-950/20 p-3 text-xs text-amber-200">
          <p>
            This draft&apos;s job invented its own passage. Promote the passage
            first — approving the draft now is refused.
          </p>
          <p className="mt-1 font-mono text-[10px] text-slate-400">
            {pendingPassage}
          </p>
          <button
            onClick={() => onPromotePassage?.(pendingPassage)}
            disabled={busy || !onPromotePassage}
            className="mt-2 rounded-md border border-amber-600/60 px-3 py-1.5 text-xs font-semibold text-amber-200 hover:bg-amber-900/40 disabled:opacity-50"
          >
            Promote passage
          </button>
        </div>
      )}
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

/**
 * The author → gates → judge → revise history behind a contrast variation
 * (spec 054). A reviewer sees what was objected to each round and whether the
 * final draft was accepted; an unaccepted draft is still here on purpose,
 * flagged, because a human is the gate — the loop only improves what they see.
 */
export function RevisionHistory({
  revisions,
}: {
  revisions: NonNullable<NonNullable<LsatProposal['meta']>['revisions']>
}) {
  return (
    <details
      data-testid="revision-history"
      className={
        'mt-3 rounded-md border px-3 py-2 text-xs ' +
        (revisions.accepted
          ? 'border-slate-800 text-slate-400'
          : 'border-amber-800/60 bg-amber-950/20 text-amber-200')
      }
    >
      <summary className="cursor-pointer">
        {revisions.rounds.length} drafting round{revisions.rounds.length === 1 ? '' : 's'} ·{' '}
        {revisions.accepted ? 'accepted by the gates and the judge' : 'NOT accepted — cap reached'}
      </summary>
      <ol className="mt-2 space-y-2">
        {revisions.rounds.map((r) => (
          <li key={r.round}>
            <span className="font-mono text-slate-300">round {r.round}</span>{' '}
            <span className="text-slate-500">{r.model}</span>
            {r.accepted && <span className="ml-1 text-emerald-300">✓</span>}
            {r.gate_issues.length > 0 && (
              <ul className="ml-4 list-disc text-slate-400">
                {r.gate_issues.map((g) => (
                  <li key={g}>gate: {g}</li>
                ))}
              </ul>
            )}
            {r.judge && (
              <div className="ml-4 text-slate-400">
                judge: {r.judge.verdict}
                {r.judge.key_agrees === false ? ' (blind key disagrees)' : ''}
                {r.judge.issues.length > 0 ? ` — ${r.judge.issues.join(' · ')}` : ''}
              </div>
            )}
          </li>
        ))}
      </ol>
    </details>
  )
}

/**
 * The final reviewer's verdict (spec 054: Fable, a different model from the
 * judge inside the loop). A `fail` here left the draft filed but unaccepted;
 * it is the last independent read before a human decides.
 */
export function FinalReviewBadge({
  verdict,
}: {
  verdict: LsatJudgeVerdict & { role?: string }
}) {
  const cls =
    verdict.verdict === 'pass'
      ? 'bg-emerald-900/60 text-emerald-300'
      : verdict.verdict === 'flag'
        ? 'bg-amber-900/60 text-amber-200'
        : 'bg-red-900/60 text-red-300'
  return (
    <span
      data-testid="final-review-badge"
      className={'rounded-md px-2 py-0.5 font-mono ' + cls}
      title={
        `Final review (${verdict.model}): ${verdict.verdict}` +
        (verdict.issues.length ? ` — ${verdict.issues.join(' · ')}` : '')
      }
    >
      final review: {verdict.verdict}
    </span>
  )
}
