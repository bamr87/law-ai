'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { fetchMatterStudyPlan, type MatterStudyPlan } from '@/lib/api'

/**
 * "Study from this matter" (BL-20260817-04).
 *
 * static-parity: none — the static export has no accounts and no matters, so
 * there is nothing for it to build a plan from; the drill deep links this
 * panel emits (`/lsat?concept=…`) are the part the static site already has.
 *
 * The matter's issue tags choose the reasoning concepts; the learner's own
 * attempt history chooses the order, so a concept they have never practised
 * leads and one they are already solid on sinks. Tags the curated map does
 * not cover are shown rather than hidden — an unmapped tag is a gap in the
 * map, and the person reading this is exactly who can report it.
 */
export default function StudyFromMatter({ slug }: { slug: string }) {
  const [plan, setPlan] = useState<MatterStudyPlan | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let live = true
    fetchMatterStudyPlan(slug)
      .then((body) => {
        if (live) setPlan(body)
      })
      .catch(() => {
        if (live) setError(true)
      })
    return () => {
      live = false
    }
  }, [slug])

  if (error) return null
  if (!plan) return <p className="text-sm text-slate-500">Building a study plan…</p>

  if (plan.concepts.length === 0) {
    return (
      <p className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 text-sm text-slate-400">
        No study material maps to this matter&rsquo;s issue tags yet
        {plan.unmapped_tags.length > 0
          ? ` (${plan.unmapped_tags.join(', ')})`
          : ''}
        . Add a tag the doctrine map covers, or extend the map.
      </p>
    )
  }

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
        Study from this matter
      </h3>
      <p className="mt-1 text-xs text-slate-500">
        Reasoning concepts this matter&rsquo;s issues rely on, weakest first.
      </p>
      <ul className="mt-3 space-y-3">
        {plan.concepts.map((concept) => (
          <li key={concept.concept_id} className="border-t border-slate-800 pt-3">
            <div className="flex items-baseline justify-between gap-3">
              <Link
                href={`/lsat?concept=${encodeURIComponent(concept.concept_id)}`}
                className="text-sm font-semibold text-slate-100 hover:text-amber-300"
              >
                {concept.name}
              </Link>
              <span className="text-[11px] uppercase tracking-wider text-slate-500">
                {concept.status === 'unpractised'
                  ? 'not practised'
                  : `${Math.round((concept.accuracy ?? 0) * 100)}% over ${concept.attempts}`}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {concept.why || concept.summary}
            </p>
            <p className="mt-1 text-[11px] text-slate-600">
              From: {concept.from_tags.join(', ')}
              {concept.articles.length > 0
                ? ` · ${concept.articles.length} library article(s)`
                : ''}
              {concept.drills.length > 0
                ? ` · ${concept.drills.length} drill(s)`
                : ''}
            </p>
          </li>
        ))}
      </ul>
      {plan.unmapped_tags.length > 0 && (
        <p className="mt-3 text-[11px] text-slate-600">
          No mapping yet for: {plan.unmapped_tags.join(', ')}
        </p>
      )}
    </section>
  )
}
