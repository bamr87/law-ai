'use client'

/**
 * Playbook browser — every question type the exam recycles, with how to spot
 * it, what it asks, how to work it, and the traps it plants (spec 053 FR-8).
 *
 * The reference half of the diagnosis exercise: the drill asks the learner to
 * name a type and marks the call; this is where the whole catalog can be read
 * end to end. Each entry carries the drill link back into the lab, so reading
 * about a type and practising it are one click apart. No LLM anywhere — the
 * catalog is data, so this renders identically offline.
 *
 * static-parity: none — the catalog is not in content.json yet; the static mirror is BL-20260907-16.
 */

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import { useRovingTabIndex } from '@/components/shell/useRovingTabIndex'
import {
  fetchLsatPlaybooks,
  type LsatPlaybook,
  type LsatSection,
  type LsatTrap,
} from '@/lib/api'

const SECTIONS: { id: LsatSection; label: string }[] = [
  { id: 'LR', label: 'Logical Reasoning' },
  { id: 'RC', label: 'Reading Comprehension' },
  { id: 'LG', label: 'Logic Games' },
]

/** Where "Drill this type" goes. Only LR filters by archetype server-side
 *  (spec 053 FR-9); passage sections drill the type's primary concept, which
 *  is the filter the passage panels already understand. */
export function drillHref(pb: LsatPlaybook): string {
  if (pb.section === 'LR')
    return `/lsat?tab=LR&archetype=${encodeURIComponent(pb.archetype_id)}`
  const concept = pb.concepts[0]
  return `/lsat?tab=${pb.section}${
    concept ? `&concept=${encodeURIComponent(concept)}` : ''
  }`
}

export default function PlaybookBrowser() {
  const [books, setBooks] = useState<LsatPlaybook[] | null>(null)
  const [traps, setTraps] = useState<LsatTrap[]>([])
  const [error, setError] = useState<string | null>(null)
  const [section, setSection] = useState<LsatSection>(() => {
    // A deep link `#lr-weaken` opens on the section it names.
    if (typeof window !== 'undefined') {
      const prefix = window.location.hash.replace('#', '').slice(0, 2).toUpperCase()
      if (prefix === 'RC' || prefix === 'LG') return prefix
    }
    return 'LR'
  })

  useEffect(() => {
    let live = true
    fetchLsatPlaybooks()
      .then((body) => {
        if (!live) return
        setBooks(body.playbooks)
        setTraps(body.traps)
      })
      .catch((e: unknown) => {
        if (live) setError(e instanceof Error ? e.message : 'Failed to load')
      })
    return () => {
      live = false
    }
  }, [])

  // Scroll to a hash target once the catalog has rendered.
  useEffect(() => {
    if (!books || typeof window === 'undefined') return
    const id = window.location.hash.replace('#', '')
    if (id) document.getElementById(id)?.scrollIntoView({ block: 'start' })
  }, [books])

  const shown = useMemo(
    () => (books ?? []).filter((b) => b.section === section),
    [books, section],
  )

  const roving = useRovingTabIndex({
    count: SECTIONS.length,
    activeIndex: SECTIONS.findIndex((s) => s.id === section),
    onActivate: (i) => setSection(SECTIONS[i].id),
  })

  return (
    <div className="space-y-6">
      <div role="tablist" aria-label="Playbook sections" className="flex flex-wrap gap-1">
        {SECTIONS.map((s, i) => {
          const active = s.id === section
          return (
            <button
              key={s.id}
              {...roving.itemProps(i)}
              role="tab"
              aria-selected={active}
              aria-controls={`playbooks-${s.id}`}
              onClick={() => setSection(s.id)}
              className={
                'tap-target rounded-lg px-3 py-2 text-sm font-medium transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 ' +
                (active
                  ? 'bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-md shadow-blue-500/20'
                  : 'text-slate-300 hover:bg-slate-800/60 hover:text-white')
              }
            >
              {s.label}
            </button>
          )
        })}
      </div>

      {error && (
        <p role="alert" className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </p>
      )}
      {!books && !error && (
        <p role="status" className="text-sm text-slate-400">
          Loading the playbooks…
        </p>
      )}

      {books && (
        <div id={`playbooks-${section}`} role="tabpanel" className="space-y-4">
          <p className="text-xs text-slate-400">
            {shown.length} question type{shown.length === 1 ? '' : 's'}. Turn on
            “Diagnose first” in the lab to be quizzed on them before each question.
          </p>
          {shown.map((pb) => (
            <PlaybookCard key={pb.archetype_id} pb={pb} />
          ))}
        </div>
      )}

      {traps.length > 0 && (
        <section
          aria-labelledby="trap-glossary"
          className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-5"
        >
          <h2 id="trap-glossary" className="text-sm font-semibold uppercase tracking-wider text-amber-300">
            Trap glossary
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            The wrong-answer patterns the exam reuses across every section. Learn
            them once; they come back on every page.
          </p>
          <dl className="mt-3 grid gap-3 md:grid-cols-2">
            {traps.map((t) => (
              <div key={t.id} id={`trap-${t.id}`} className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                <dt className="text-sm font-medium text-amber-100">{t.name}</dt>
                <dd className="mt-1 text-xs text-slate-400">{t.summary}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </div>
  )
}

function PlaybookCard({ pb }: { pb: LsatPlaybook }) {
  return (
    <article
      id={pb.archetype_id}
      className="scroll-mt-24 rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-slate-400">
            {pb.section} · {pb.family.replace(/-/g, ' ')}
          </div>
          <h3 className="mt-1 text-lg font-semibold text-slate-100">{pb.name}</h3>
          <p className="mt-1 text-sm text-slate-300">{pb.task}</p>
        </div>
        <Link
          href={drillHref(pb)}
          className="shrink-0 rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-amber-300 hover:border-amber-400"
        >
          Drill this type →
        </Link>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-slate-400">
            How to spot it
          </div>
          <ul className="mt-1 space-y-1 text-xs italic text-slate-300">
            {pb.cues.map((c) => (
              <li key={c}>“{c}”</li>
            ))}
          </ul>
          {pb.confused_with.length > 0 && (
            <p className="mt-2 text-xs text-slate-400">
              Not to be confused with:{' '}
              {pb.confused_with.map((c, i) => (
                <span key={c.id}>
                  {i > 0 && ' · '}
                  <a href={`#${c.id}`} className="underline underline-offset-2 hover:text-slate-200">
                    {c.name}
                  </a>
                </span>
              ))}
            </p>
          )}
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-slate-400">
            Method
          </div>
          <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm text-slate-200">
            {pb.method.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ol>
          <div className="mt-2 text-xs text-slate-400">
            Strategies: {pb.strategies.map((s) => s.name).join(' · ')}
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-amber-300">
            Traps
          </div>
          <ul className="mt-1 space-y-1 text-sm">
            {pb.traps.map((t) => (
              <li key={t.id}>
                <a href={`#trap-${t.id}`} className="font-medium text-amber-100 underline-offset-2 hover:underline">
                  {t.name}
                </a>
                <span className="text-slate-400"> — {t.summary}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </article>
  )
}
