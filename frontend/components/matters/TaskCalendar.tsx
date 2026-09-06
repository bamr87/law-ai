'use client'

import { useCallback, useEffect, useState } from 'react'

import {
  fetchMatterCalendar,
  updateMatterTask,
  type MatterCalendar,
  type MatterTaskRow,
} from '@/lib/api'

/**
 * Deadlines across every matter the caller owns (BL-20260817-02).
 *
 * The action stage could only record what someone chose to log as an
 * artifact; this is the surface that answers "what is due". Three buckets
 * rather than a month grid: overdue is the only thing that changes what you
 * do next, and a grid buries it in whitespace.
 *
 * Due dates are user-entered — nothing here computes a court deadline from a
 * rule of procedure (spec 036 NG1), and the copy says so.
 */
export default function TaskCalendar({ days = 30 }: { days?: number }) {
  const [calendar, setCalendar] = useState<MatterCalendar | null>(null)
  const [signedOut, setSignedOut] = useState(false)

  const load = useCallback(async () => {
    try {
      setCalendar(await fetchMatterCalendar(days))
      setSignedOut(false)
    } catch {
      setSignedOut(true)
    }
  }, [days])

  useEffect(() => {
    void load()
  }, [load])

  const complete = useCallback(
    async (task: MatterTaskRow) => {
      if (!task.matter_slug) return
      await updateMatterTask(task.matter_slug, task.id, { status: 'done' })
      await load()
    },
    [load],
  )

  if (signedOut) return null
  if (!calendar) {
    return <p className="text-sm text-slate-500">Loading deadlines…</p>
  }

  if (calendar.count === 0) {
    return (
      <p className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 text-sm text-slate-400">
        Nothing due in the next {calendar.window_days} days.
      </p>
    )
  }

  return (
    <div className="space-y-4">
      <Bucket
        title="Overdue"
        tone="text-rose-300"
        tasks={calendar.overdue}
        onComplete={complete}
      />
      <Bucket
        title="Today"
        tone="text-amber-300"
        tasks={calendar.today}
        onComplete={complete}
      />
      <Bucket
        title="Upcoming"
        tone="text-slate-300"
        tasks={calendar.upcoming}
        onComplete={complete}
      />
      <p className="text-[11px] text-slate-500">
        Due dates are the ones you entered. Law AI does not compute filing
        deadlines from court rules.
      </p>
    </div>
  )
}

function Bucket({
  title,
  tone,
  tasks,
  onComplete,
}: {
  title: string
  tone: string
  tasks: MatterTaskRow[]
  onComplete: (task: MatterTaskRow) => void
}) {
  if (tasks.length === 0) return null
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5">
      <h3
        className={`text-sm font-semibold uppercase tracking-wider ${tone}`}
      >
        {title}
      </h3>
      <ul className="mt-3 space-y-2">
        {tasks.map((task) => (
          <li
            key={task.id}
            className="flex items-center justify-between gap-3 border-t border-slate-800 pt-2 text-sm"
          >
            <span className="min-w-0">
              <span className="text-slate-200">{task.title}</span>
              <span className="ml-2 text-xs text-slate-500">
                {task.matter_name}
                {task.due_at ? ` · ${formatDue(task.due_at)}` : ''}
              </span>
            </span>
            <button
              type="button"
              onClick={() => onComplete(task)}
              className="shrink-0 rounded-lg border border-slate-700 px-2 py-1 text-xs text-emerald-300 hover:border-emerald-400"
            >
              Done
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

function formatDue(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toISOString().slice(0, 10)
}
