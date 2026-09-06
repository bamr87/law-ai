/**
 * Stats panel — this session beside the all-time audit-log totals.
 *
 * Moved out of `LsatLab.tsx` unchanged in phase 1 of BL-20260830-02.
 *
 * static-parity: none — the static export's `Stats.tsx` reads attempts back
 * out of localStorage; this panel renders `/api/lsat/stats`, which is the
 * audit log's view and carries the assisted/unassisted split.
 */

import type { LsatStats } from '@/lib/api'
import type { SessionScore } from '@/components/lsat/labTabs'

export default function StatsPanel({
  session,
  stats,
}: {
  session: SessionScore
  stats: LsatStats | null
}) {
  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <StatCard
          title="This session"
          attempts={session.attempts}
          correct={session.correct}
        />
        <StatCard
          title="All-time (audit log)"
          attempts={stats?.attempts ?? 0}
          correct={stats?.correct ?? 0}
        />
      </div>
      {stats?.by_section && Object.keys(stats.by_section).length > 0 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
            By section
          </h3>
          <table className="mt-3 w-full text-sm">
            <thead className="text-left text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="pb-2">Section</th>
                <th className="pb-2 text-right">Attempts</th>
                <th className="pb-2 text-right">Correct</th>
                <th className="pb-2 text-right">Accuracy</th>
              </tr>
            </thead>
            <tbody className="text-slate-200">
              {Object.entries(stats.by_section).map(([sec, b]) => (
                <tr key={sec} className="border-t border-slate-800">
                  <td className="py-2 font-mono text-slate-300">{sec}</td>
                  <td className="py-2 text-right tabular-nums">{b.attempts}</td>
                  <td className="py-2 text-right tabular-nums">{b.correct}</td>
                  <td className="py-2 text-right tabular-nums">
                    {Math.round(b.accuracy * 100)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function StatCard({
  title,
  attempts,
  correct,
}: {
  title: string
  attempts: number
  correct: number
}) {
  const pct = attempts > 0 ? Math.round((correct / attempts) * 100) : 0
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur">
      <div className="text-[11px] uppercase tracking-wider text-slate-500">
        {title}
      </div>
      <div className="mt-2 text-3xl font-semibold tabular-nums text-slate-100">
        {correct}
        <span className="text-slate-500"> / {attempts}</span>
      </div>
      <div className="mt-1 text-sm text-slate-400">{pct}% accuracy</div>
    </div>
  )
}
