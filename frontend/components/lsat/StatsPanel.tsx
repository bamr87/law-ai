/**
 * Stats panel — this session beside the all-time audit-log totals.
 *
 * Moved out of `LsatLab.tsx` unchanged in phase 1 of BL-20260830-02.
 *
 * static-parity: none — the static export's `Stats.tsx` reads attempts back
 * out of localStorage; this panel renders `/api/lsat/stats`, which is the
 * audit log's view and carries the assisted/unassisted split.
 */

import Link from 'next/link'

import type { LsatDiagnosisStats, LsatReviewItem, LsatStats } from '@/lib/api'
import type { SessionScore } from '@/components/lsat/labTabs'

export default function StatsPanel({
  session,
  stats,
}: {
  session: SessionScore
  stats: LsatStats | null
}) {
  // Reading is practice too (BL-20260903-05). It lived only in each browser's
  // localStorage, so the one half of the library's own loop that no surface
  // could report sat invisible next to drill accuracy.
  const showReading = typeof stats?.articles_total === 'number'
  return (
    <section className="space-y-4">
      <div
        className={
          'grid gap-4 ' + (showReading ? 'md:grid-cols-3' : 'md:grid-cols-2')
        }
      >
        <StatCard
          title="This session"
          attempts={session.attempts}
          correct={session.correct}
        />
        <StatCard
          title={
            stats?.scope === 'user' ? 'Your history' : 'All-time (audit log)'
          }
          attempts={stats?.attempts ?? 0}
          correct={stats?.correct ?? 0}
        />
        {showReading && (
          <ReadingCard
            read={stats?.articles_read ?? 0}
            total={stats?.articles_total ?? 0}
          />
        )}
      </div>
      <DiagnosisProgress diagnosis={stats?.diagnosis} />
      <WritingProgress writing={stats?.writing} />
      <ReviewQueue items={stats?.review_queue ?? []} />
      {stats?.by_section && Object.keys(stats.by_section).length > 0 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
            By section
          </h3>
          <table className="mt-3 w-full text-sm">
            <thead className="text-left text-[11px] uppercase tracking-wider text-slate-400">
              <tr>
                <th className="pb-2">Section</th>
                <th className="pb-2 text-right">Attempts</th>
                <th className="pb-2 text-right">Correct</th>
                <th className="pb-2 text-right">Accuracy</th>
                {showReading && <th className="pb-2 text-right">Read</th>}
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
                  {showReading && (
                    <td className="py-2 text-right tabular-nums">
                      {b.articles_read ?? 0}
                    </td>
                  )}
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
      <div className="text-[11px] uppercase tracking-wider text-slate-400">
        {title}
      </div>
      <div className="mt-2 text-3xl font-semibold tabular-nums text-slate-100">
        {correct}
        <span className="text-slate-400"> / {attempts}</span>
      </div>
      <div className="mt-1 text-sm text-slate-400">{pct}% accuracy</div>
    </div>
  )
}


/**
 * Library reading, beside drill accuracy (BL-20260903-05).
 *
 * Deliberately not shaped like the accuracy cards: articles read out of
 * articles published is a completion count, not a score, and rendering it as a
 * percentage next to two accuracy figures would invite reading it as one.
 */
function ReadingCard({ read, total }: { read: number; total: number }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur">
      <div className="text-[11px] uppercase tracking-wider text-slate-400">
        Library
      </div>
      <div className="mt-2 text-3xl font-semibold tabular-nums text-slate-100">
        {read}
        <span className="text-slate-400"> / {total}</span>
      </div>
      <div className="mt-1 text-sm text-slate-400">
        articles read ·{' '}
        <Link
          href="/lsat/library"
          className="text-amber-300 underline underline-offset-2 hover:text-amber-200"
        >
          keep reading
        </Link>
      </div>
    </div>
  )
}


/** `lr-necessary-assumption` → `Necessary assumption` for a stats row. */
export function humanizeArchetype(id: string): string {
  const words = id.replace(/^(lr|rc|lg)-/, '').split('-').join(' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/**
 * Question-type recognition across attempts (spec 053 FR-7).
 *
 * Kept apart from answer accuracy because it measures a different skill, and
 * shaped around the two readouts a learner can act on: which types they misread
 * (weakest first, each linking to its playbook) and which pairs they swap.
 * "You keep calling necessary assumptions sufficient" is the sentence this
 * card exists to say.
 */
function DiagnosisProgress({ diagnosis }: { diagnosis?: LsatDiagnosisStats }) {
  if (!diagnosis || diagnosis.attempts === 0) return null
  const pct = (n: number) => `${Math.round(n * 100)}%`
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Question-type recognition
        </h3>
        <Link
          href="/lsat/playbooks"
          className="text-xs text-amber-300 underline underline-offset-2 hover:text-amber-200"
        >
          All playbooks
        </Link>
      </div>
      <div className="mt-3 flex flex-wrap gap-6">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-slate-400">
            Type named
          </div>
          <div className="text-2xl font-semibold tabular-nums text-slate-100">
            {diagnosis.type_correct}
            <span className="text-slate-400"> / {diagnosis.attempts}</span>
          </div>
          <div className="text-xs text-slate-400">
            {pct(diagnosis.type_accuracy)} · {pct(diagnosis.family_accuracy)} right
            family
          </div>
        </div>
        {diagnosis.strategy_attempts > 0 && (
          <div>
            <div className="text-[11px] uppercase tracking-wider text-slate-400">
              Strategy named
            </div>
            <div className="text-2xl font-semibold tabular-nums text-slate-100">
              {diagnosis.strategy_correct}
              <span className="text-slate-400"> / {diagnosis.strategy_attempts}</span>
            </div>
            <div className="text-xs text-slate-400">{pct(diagnosis.strategy_accuracy)}</div>
          </div>
        )}
      </div>
      {diagnosis.confusions.length > 0 && (
        <div className="mt-4">
          <div className="text-[11px] uppercase tracking-wider text-slate-400">
            Most often confused
          </div>
          <ul className="mt-1 space-y-1 text-sm text-slate-200">
            {diagnosis.confusions.map((c) => (
              <li key={`${c.chosen}>${c.actual}`}>
                Called{' '}
                <Link
                  href={`/lsat/playbooks#${c.actual}`}
                  className="text-sky-300 underline underline-offset-2 hover:text-sky-200"
                >
                  {humanizeArchetype(c.actual)}
                </Link>{' '}
                “{humanizeArchetype(c.chosen)}”
                <span className="text-slate-400"> ×{c.count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {diagnosis.weakest.length > 0 && (
        <p className="mt-3 text-xs text-slate-400">
          Weakest types:{' '}
          {diagnosis.weakest.map((id, i) => (
            <span key={id}>
              {i > 0 && ' · '}
              <Link
                href={`/lsat/playbooks#${id}`}
                className="underline underline-offset-2 hover:text-slate-200"
              >
                {humanizeArchetype(id)}
              </Link>
            </span>
          ))}
        </p>
      )}
    </div>
  )
}

/**
 * Argumentative Writing across attempts (BL-20260831-27).
 *
 * Evaluations were persisted from the day the evaluator shipped and read back
 * by nothing, so a learner could not see writing progress the way `lsat_grade`
 * events power everything above. Rendered as a trend rather than a headline
 * number because a single band means very little and the *direction* is the
 * whole point — and every band is labelled as machine-derived, because the
 * real writing section carries no score at all.
 */
function WritingProgress({
  writing,
}: {
  writing?: NonNullable<LsatStats['writing']>
}) {
  if (!writing || writing.attempts === 0) return null
  const best = writing.best_band
  const latest = writing.latest_band
  const prompts = Object.entries(writing.by_prompt).sort((a, b) => b[1] - a[1])
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Argumentative Writing
        </h3>
        <Link
          href="/lsat?tab=WS"
          className="text-xs text-amber-300 underline underline-offset-2 hover:text-amber-200"
        >
          Draft another
        </Link>
      </div>
      <p className="mt-1 text-xs text-slate-400">
        {writing.attempts} evaluation{writing.attempts === 1 ? '' : 's'} · bands
        are machine-derived
        {writing.model ? ` (${writing.model}` : ''}
        {writing.model && writing.prompt_version
          ? `, prompt ${writing.prompt_version})`
          : writing.model
            ? ')'
            : ''}
        {writing.degraded > 0 &&
          ` · ${writing.degraded} from the degraded fallback`}
        . The real section is unscored.
      </p>
      <div className="mt-3 flex flex-wrap gap-6">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-slate-400">
            Latest band
          </div>
          <div className="text-2xl font-semibold tabular-nums text-slate-100">
            {latest === null ? '—' : latest.toFixed(2)}
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-slate-400">
            Best band
          </div>
          <div className="text-2xl font-semibold tabular-nums text-slate-100">
            {best === null ? '—' : best.toFixed(2)}
          </div>
        </div>
      </div>
      {writing.band_trend.length > 1 && (
        <ol
          aria-label="Weighted band by attempt, oldest first"
          className="mt-3 flex flex-wrap gap-1.5"
        >
          {writing.band_trend.map((band, i) => (
            <li
              key={i}
              className="rounded-md border border-slate-700 bg-slate-950/50 px-2 py-0.5 font-mono text-xs tabular-nums text-slate-300"
            >
              {band.toFixed(1)}
            </li>
          ))}
        </ol>
      )}
      {prompts.length > 0 && (
        <p className="mt-3 text-xs text-slate-400">
          By prompt:{' '}
          {prompts
            .map(([id, n]) => `${id} ×${n}`)
            .join(' · ')}
        </p>
      )}
    </div>
  )
}


/**
 * Due for review (BL-20260503-05).
 *
 * Only a signed-in learner has a schedule, so an empty queue renders nothing
 * at all rather than an empty-state that would be permanent for anonymous
 * practice. Each row links back into the drill for its section, carrying the
 * question's first concept so the lab opens on the right material.
 */
function ReviewQueue({ items }: { items: LsatReviewItem[] }) {
  if (items.length === 0) return null
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
        Due for review
      </h3>
      <p className="mt-1 text-xs text-slate-400">
        Missed questions come back first; ones you keep getting right recede.
      </p>
      <ul className="mt-3 space-y-2">
        {items.map((item) => {
          const concept = item.concepts?.[0]
          const href = `/lsat?tab=${item.section || 'LR'}${
            concept ? `&concept=${encodeURIComponent(concept)}` : ''
          }`
          return (
            <li
              key={item.question_id}
              className="flex items-center justify-between gap-3 border-t border-slate-800 pt-2 text-sm"
            >
              <span className="min-w-0">
                <span className="font-mono text-slate-300">
                  {item.question_id}
                </span>
                <span className="ml-2 text-xs text-slate-400">
                  {item.reason === 'missed'
                    ? 'missed last time'
                    : `box ${item.box}`}
                </span>
              </span>
              <Link
                href={href}
                className="shrink-0 rounded-lg border border-slate-700 px-2 py-1 text-xs text-amber-300 hover:border-amber-400"
              >
                Drill {item.section || 'LR'}
              </Link>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
