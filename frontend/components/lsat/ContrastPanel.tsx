'use client'

/**
 * Contrast panel — the same stimulus, asked as other question types (spec 054).
 *
 * Shown after grading. A learner who has just weakened an argument sees that
 * the same argument is also asked as a Strengthen and as a Necessary
 * Assumption question, what each of those tasks wants, and — for the item
 * they just answered — the note on where the key moved and why. Sibling notes
 * stay behind a disclosure so reading about one variation never spoils the
 * next one before it is attempted.
 *
 * static-parity: none — contrast sets are served by the contrast endpoint;
 * the static mirror is BL-20260908-01.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { fetchLsatContrast, type LsatContrastSet, type LsatSection } from '@/lib/api'

/** Where "try it" goes: the LR drill opened on that exact question. */
export function tryHref(section: LsatSection, questionId: string): string {
  return `/lsat?tab=${section}&question=${encodeURIComponent(questionId)}`
}

export default function ContrastPanel({
  questionId,
  section,
}: {
  questionId: string
  section: LsatSection
}) {
  const [set, setSet] = useState<LsatContrastSet | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let live = true
    fetchLsatContrast(questionId, { spoilers: true })
      .then((s) => {
        if (live) setSet(s)
      })
      .catch(() => {
        if (live) setFailed(true)
      })
    return () => {
      live = false
    }
  }, [questionId])

  // A question with no variations has nothing to contrast; render nothing
  // rather than an empty frame on every graded card.
  if (failed || !set || set.count < 2) return null
  const current = set.members.find((m) => m.id === questionId)
  const others = set.members.filter((m) => m.id !== questionId)

  return (
    <section
      aria-label="Same argument, different question"
      className="mt-4 rounded-lg border border-violet-500/30 bg-violet-500/5 p-4"
    >
      <div className="text-[11px] uppercase tracking-wider text-violet-300">
        Same argument, different question
      </div>
      {current?.contrast_note && (
        <p className="mt-2 text-sm leading-relaxed text-slate-200">
          {current.contrast_note}
        </p>
      )}
      <ul className="mt-3 space-y-2">
        {others.map((m) => (
          <li
            key={m.id}
            className="flex flex-wrap items-start justify-between gap-2 rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2"
          >
            <div className="min-w-0">
              <div className="text-sm font-medium text-slate-100">
                {m.archetype_name ?? m.archetype_id ?? m.id}
                {m.is_root && (
                  <span className="ml-2 text-[10px] uppercase tracking-wider text-slate-500">
                    original
                  </span>
                )}
              </div>
              <div className="text-xs italic text-slate-400">“{m.question_sentence}”</div>
              {m.task && <div className="mt-1 text-xs text-slate-400">{m.task}</div>}
              {m.contrast_note && (
                <details className="mt-1 text-xs text-slate-400">
                  <summary className="cursor-pointer text-slate-500">
                    What changes (spoiler)
                  </summary>
                  <p className="mt-1">{m.contrast_note}</p>
                </details>
              )}
            </div>
            <Link
              href={tryHref(section, m.id)}
              className="shrink-0 rounded-lg border border-slate-700 px-2 py-1 text-xs text-amber-300 hover:border-amber-400"
            >
              Try it →
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
