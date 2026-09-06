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
  fetchLsatGaps,
  fetchLsatProposals,
  generateLsatProposals,
  rejectLsatProposal,
  type LsatDifficulty,
  type LsatGapRow,
  type LsatGuideProposalDraft,
  type LsatProposal,
  type LsatProposalDraft,
  type LsatSection,
} from '@/lib/api'
import { ErrorBanner } from '@/components/lsat/LabPrimitives'
import ValidationReport from '@/components/lsat/ValidationReport'

export default function AuthoringPanel() {
  const [pending, setPending] = useState<LsatProposal[]>([])
  const [gaps, setGaps] = useState<LsatGapRow[]>([])
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

  const d = proposal.draft as LsatProposalDraft
  return (
    <article className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
      <header className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-md bg-slate-800 px-2 py-0.5 font-mono text-slate-300">
          {d.section}
        </span>
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
