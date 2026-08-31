'use client'

import { useState } from 'react'

import { fetchLsatValidation, type LsatValidationReport } from '@/lib/api'

/**
 * Question-set accuracy review for the Authoring tab (spec 041 FR-15).
 *
 * Runs the deterministic validation report on demand: per-question
 * integrity issues, answer-key distribution per section (reported as
 * counts, never judged), and every stored AI cross-check verdict —
 * disagreements listed by question so a reviewer can re-verify the key.
 */
export default function ValidationReport() {
  const [report, setReport] = useState<LsatValidationReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setLoading(true)
    setError(null)
    try {
      setReport(await fetchLsatValidation())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Validation failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section
      aria-label="Question set validation"
      className="rounded-xl border border-slate-800 bg-slate-900/40 p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-200">
            Question-set review
          </h3>
          <p className="text-xs text-slate-500">
            Deterministic accuracy checks + stored AI cross-check verdicts.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void run()}
          disabled={loading}
          className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-200 transition hover:bg-sky-500/20 disabled:opacity-40"
        >
          {loading ? 'Reviewing…' : report ? 'Re-run review' : 'Run review'}
        </button>
      </div>

      {error && (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {error}
        </p>
      )}

      {report && (
        <div className="mt-4 space-y-4 text-sm">
          <p className="text-slate-300">
            {report.question_count} questions · {report.guide_count} solve
            guides ·{' '}
            <span
              className={
                report.issue_count > 0 ? 'text-amber-300' : 'text-emerald-300'
              }
            >
              {report.issue_count} integrity issue
              {report.issue_count === 1 ? '' : 's'}
            </span>
          </p>

          {report.issues.length > 0 && (
            <ul className="space-y-1">
              {report.issues.map((issue, i) => (
                <li key={i} className="text-xs text-amber-200">
                  <span className="font-mono text-slate-400">
                    {issue.question_id}
                  </span>{' '}
                  <span className="uppercase text-[10px] tracking-wider text-amber-400">
                    {issue.kind}
                  </span>{' '}
                  <span className="text-slate-400">{issue.detail}</span>
                </li>
              ))}
            </ul>
          )}

          <div>
            <h4 className="text-[11px] uppercase tracking-wider text-slate-500">
              Answer-key distribution (counts, not correctness)
            </h4>
            <div className="mt-1 overflow-x-auto">
              <table className="min-w-[280px] border-collapse text-xs">
                <thead>
                  <tr>
                    <th scope="col" className="p-1.5" aria-label="section" />
                    {['A', 'B', 'C', 'D', 'E'].map((label) => (
                      <th
                        key={label}
                        scope="col"
                        className="p-1.5 text-center font-mono text-slate-400"
                      >
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(report.answer_distribution).map(
                    ([section, counts]) => (
                      <tr key={section} className="border-t border-slate-800/70">
                        <th
                          scope="row"
                          className="p-1.5 text-left font-mono text-slate-300"
                        >
                          {section}
                        </th>
                        {['A', 'B', 'C', 'D', 'E'].map((label) => (
                          <td
                            key={label}
                            className="p-1.5 text-center text-slate-400"
                          >
                            {counts[label] ?? 0}
                          </td>
                        ))}
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div>
            <h4 className="text-[11px] uppercase tracking-wider text-slate-500">
              AI cross-checks
            </h4>
            {report.cross_checks.checked === 0 ? (
              <p className="mt-1 text-xs text-slate-500">
                None run yet — use “Cross-check this answer” on a graded
                question, or the API, to build corroboration.
              </p>
            ) : (
              <>
                <p className="mt-1 text-xs text-slate-400">
                  {report.cross_checks.checked} checked ·{' '}
                  <span className="text-emerald-300">
                    {report.cross_checks.agreements} agree
                  </span>{' '}
                  ·{' '}
                  <span
                    className={
                      report.cross_checks.disagreements.length > 0
                        ? 'text-amber-300'
                        : 'text-slate-400'
                    }
                  >
                    {report.cross_checks.disagreements.length} disagree
                  </span>
                </p>
                {report.cross_checks.disagreements.length > 0 && (
                  <ul className="mt-1 space-y-1">
                    {report.cross_checks.disagreements.map((d) => (
                      <li key={d.question_id} className="text-xs text-amber-200">
                        <span className="font-mono text-slate-300">
                          {d.question_id}
                        </span>{' '}
                        key {d.bank_choice}, blind solve picked{' '}
                        {d.model_choice ?? '—'} ({d.model}) — re-verify the
                        answer key.
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
