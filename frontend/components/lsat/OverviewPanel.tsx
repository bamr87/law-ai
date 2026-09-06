'use client'

/**
 * Overview panel — section docs and the jump-off into each drill.
 *
 * Moved out of `LsatLab.tsx` unchanged in phase 1 of BL-20260830-02.
 *
 * static-parity: none — the static export's `Overview.tsx` renders the same
 * section cards from the build-time `content.json`; this one fetches
 * `/api/lsat/sections`, which also carries the live bank size.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { fetchLsatSections, type LsatSectionInfo } from '@/lib/api'
import { Detail, SkeletonGrid } from '@/components/lsat/LabPrimitives'
import { PRACTICE_TABS, type Tab } from '@/components/lsat/labTabs'

export default function OverviewPanel({ onJump }: { onJump: (t: Tab) => void }) {
  const [sections, setSections] = useState<LsatSectionInfo[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void (async () => {
      try {
        const body = await fetchLsatSections()
        setSections(body.sections)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load sections')
      }
    })()
  }, [])

  return (
    <section className="space-y-6">
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur">
        <div className="text-xs uppercase tracking-wider text-amber-400">
          About the LSAT
        </div>
        <h2 className="mt-1 text-2xl font-semibold text-slate-100">
          The four-section roadmap
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-400">
          The Law School Admission Test measures the reasoning and reading
          skills that drive law-school success: identifying conclusions,
          spotting flawed arguments, mapping passage structure, and translating
          dense prose into compact constraints. Pick a section below to drill
          questions, or read up first in the{' '}
          <Link
            href="/lsat/library"
            className="text-amber-300 underline underline-offset-2 hover:text-amber-200"
          >
            knowledge library
          </Link>{' '}
          — long-form articles on how the exam works, plus the catalog of every
          reasoning pattern it recycles.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {!sections && !error && <SkeletonGrid />}

      {sections && (
        <div className="grid gap-4 md:grid-cols-2">
          {sections.map((s) => (
            <article
              key={s.code}
              className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur transition hover:border-slate-600"
            >
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-slate-100">
                  {s.name}
                </h3>
                <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider text-slate-300">
                  {s.code}
                </span>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-slate-400">
                {s.description}
              </p>
              <dl className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-slate-500">
                <Detail label="Format" value={s.format} />
                <Detail label="Timing" value={s.timing} />
                <Detail label="Scoring" value={s.scoring} />
                <Detail
                  label={s.code === 'WS' ? 'Prompts in bank' : 'Items in bank'}
                  value={`${
                    s.code === 'WS'
                      ? (s.writing_prompt_count ?? 0)
                      : s.question_count
                  }`}
                />
              </dl>
              {s.tips.length > 0 && (
                <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-300">
                  {s.tips.slice(0, 3).map((t) => (
                    <li key={t}>{t}</li>
                  ))}
                </ul>
              )}
              <div className="mt-4 flex flex-wrap items-center gap-2">
                {PRACTICE_TABS.has(s.code as Tab) ? (
                  <button
                    onClick={() => onJump(s.code as Tab)}
                    className="inline-flex items-center gap-1 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow shadow-blue-500/20 transition hover:shadow-blue-500/40"
                  >
                    Practice {s.code} →
                  </button>
                ) : (
                  <span className="rounded-lg border border-slate-800 px-3 py-1.5 text-xs text-slate-500">
                    No drill in the lab yet
                  </span>
                )}
                {s.references.slice(0, 2).map((r) =>
                  r.url ? (
                    <a
                      key={r.url}
                      href={r.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-slate-400 underline hover:text-slate-200"
                    >
                      {r.title}
                    </a>
                  ) : null,
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
