'use client'

import { useState } from 'react'
import type { SectionCode } from '@/lib/types'
import { content, SECTIONS, sectionMeta } from '@/lib/data'
import Overview from '@/components/Overview'
import Drill from '@/components/Drill'
import Concepts from '@/components/Concepts'
import Stats from '@/components/Stats'

type View = 'overview' | SectionCode | 'concepts' | 'stats'

const NAV: { id: View; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'LR', label: 'LR Drill' },
  { id: 'RC', label: 'Reading Comp' },
  { id: 'LG', label: 'Logic Games' },
  { id: 'concepts', label: 'Concepts' },
  { id: 'stats', label: 'Stats' },
]

export default function Page() {
  const [view, setView] = useState<View>('overview')
  const [announcement, setAnnouncement] = useState('')

  return (
    <>
      <header className="site-header">
        <div className="wrap">
          <div className="brand">
            <span aria-hidden="true">⚖️</span> LSAT Practice
            <span className="brand-sub">Law AI · static edition</span>
          </div>
          <nav aria-label="Sections" className="nav">
            {NAV.map((n) => (
              <button
                key={n.id}
                type="button"
                className={'nav-link' + (view === n.id ? ' nav-link-active' : '')}
                aria-current={view === n.id ? 'page' : undefined}
                onClick={() => setView(n.id)}
              >
                {n.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main id="view" className="wrap" tabIndex={-1}>
        {view === 'overview' && <Overview onStart={(s) => setView(s)} />}
        {SECTIONS.includes(view as SectionCode) && (
          <Drill section={view as SectionCode} onAnnounce={setAnnouncement} />
        )}
        {view === 'concepts' && <Concepts />}
        {view === 'stats' && <Stats />}
      </main>

      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>

      {/* Deliberately NOT a <footer>: the root layout renders the UPL
          disclaimer as this page's one contentinfo landmark, and a bare
          <footer> here would make a second. Same defect the platform homepage
          had (BL-20260830-06). */}
      <div className="site-footer">
        <div className="wrap">
          <span>
            {content.counts.total} items · updated{' '}
            {new Date(content.generated_at).toISOString().slice(0, 10)}
          </span>
          <span>
            Original practice content · progress stored only in this browser ·{' '}
            <a href="https://github.com/bamr87/law-ai" rel="noreferrer">
              source
            </a>
          </span>
        </div>
      </div>
    </>
  )
}
