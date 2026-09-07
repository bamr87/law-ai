'use client'

import { useCallback, useEffect, useState } from 'react'

import StudyFromMatter from '@/components/lsat/StudyFromMatter'
import MatterResearch from '@/components/matters/MatterResearch'
import {
  createMatterTask,
  fetchMatter,
  fetchMatterExport,
  fetchMatterTasks,
  updateMatterTask,
  type MatterRow,
  type MatterTaskRow,
} from '@/lib/api'

/**
 * One matter's workspace: its tasks, its study plan, its export.
 *
 * The slug is never trusted as an identity. `fetchMatter` resolves it against
 * the caller's own rows and returns `null` for a slug that is unknown *or*
 * owned by someone else — the two look identical here on purpose, so the page
 * cannot be used to test whether a matter exists.
 */
export default function MatterWorkspace({ slug }: { slug: string }) {
  const [matter, setMatter] = useState<MatterRow | null>(null)
  const [resolved, setResolved] = useState(false)
  const [tasks, setTasks] = useState<MatterTaskRow[]>([])
  const [title, setTitle] = useState('')
  const [dueAt, setDueAt] = useState('')

  const loadTasks = useCallback(async () => {
    try {
      setTasks((await fetchMatterTasks(slug)).tasks)
    } catch {
      setTasks([])
    }
  }, [slug])

  useEffect(() => {
    let live = true
    fetchMatter(slug)
      .then((row) => {
        if (!live) return
        setMatter(row)
        setResolved(true)
        if (row) void loadTasks()
      })
      .catch(() => {
        if (live) setResolved(true)
      })
    return () => {
      live = false
    }
  }, [slug, loadTasks])

  const addTask = useCallback(async () => {
    if (!title.trim()) return
    await createMatterTask(slug, {
      title: title.trim(),
      due_at: dueAt ? new Date(dueAt).toISOString() : null,
    })
    setTitle('')
    setDueAt('')
    await loadTasks()
  }, [dueAt, loadTasks, slug, title])

  const [bundle, setBundle] = useState<string | null>(null)
  const exportMatter = useCallback(async () => {
    setBundle(JSON.stringify(await fetchMatterExport(slug), null, 2))
  }, [slug])

  if (!resolved) return <p className="text-sm text-slate-400">Opening matter…</p>

  if (!matter) {
    return (
      <p className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 text-sm text-slate-400">
        No such matter. If you expected one here, sign in with the account that
        owns it.
      </p>
    )
  }

  return (
    <div className="space-y-6">
      <header className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5">
        <h2 className="text-lg font-semibold text-slate-100">{matter.name}</h2>
        <p className="mt-1 text-xs text-slate-400">
          Stage: {matter.stage}
          {matter.issue_tags.length > 0
            ? ` · ${matter.issue_tags.join(', ')}`
            : ''}
        </p>
      </header>

      <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Tasks
        </h3>
        <ul className="mt-3 space-y-2">
          {tasks.map((task) => (
            <li
              key={task.id}
              className="flex items-center justify-between gap-3 border-t border-slate-800 pt-2 text-sm"
            >
              <span className="min-w-0">
                <span
                  className={
                    task.status === 'done'
                      ? 'text-slate-400 line-through'
                      : 'text-slate-200'
                  }
                >
                  {task.title}
                </span>
                {task.due_at && (
                  <span className="ml-2 text-xs text-slate-400">
                    due {task.due_at.slice(0, 10)}
                  </span>
                )}
              </span>
              {task.status !== 'done' && (
                <button
                  type="button"
                  onClick={async () => {
                    await updateMatterTask(slug, task.id, { status: 'done' })
                    await loadTasks()
                  }}
                  className="shrink-0 rounded-lg border border-slate-700 px-2 py-1 text-xs text-emerald-300 hover:border-emerald-400"
                >
                  Done
                </button>
              )}
            </li>
          ))}
          {tasks.length === 0 && (
            <li className="text-xs text-slate-400">Nothing tracked yet.</li>
          )}
        </ul>
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <label className="text-xs text-slate-400">
            New task
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="mt-1 block rounded-lg border border-slate-700 bg-slate-950/60 px-2 py-1 text-sm text-slate-200"
            />
          </label>
          <label className="text-xs text-slate-400">
            Due
            <input
              type="date"
              value={dueAt}
              onChange={(event) => setDueAt(event.target.value)}
              className="mt-1 block rounded-lg border border-slate-700 bg-slate-950/60 px-2 py-1 text-sm text-slate-200"
            />
          </label>
          <button
            type="button"
            onClick={addTask}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:border-amber-400"
          >
            Add
          </button>
        </div>
      </section>

      <MatterResearch matterId={matter.id} jurisdiction={matter.jurisdiction} />

      <StudyFromMatter slug={slug} />

      <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Export this matter
        </h3>
        <p className="mt-1 text-xs text-slate-400">
          The full bundle — artifacts with their provenance trace ids,
          authorities, tasks and timeline.
        </p>
        <button
          type="button"
          onClick={exportMatter}
          className="mt-3 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:border-amber-400"
        >
          Build export
        </button>
        {bundle && (
          <pre className="mt-3 max-h-72 overflow-auto rounded-lg bg-slate-950/60 p-3 text-[11px] text-slate-300">
            {bundle}
          </pre>
        )}
      </section>
    </div>
  )
}
