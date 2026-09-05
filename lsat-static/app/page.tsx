'use client'

import { useEffect, useRef, useState } from 'react'
import type { SectionCode } from '@/lib/types'
import { content, SECTIONS, sectionMeta } from '@/lib/data'
import Overview from '@/components/Overview'
import Drill from '@/components/Drill'
import Writing from '@/components/Writing'
import Library from '@/components/Library'
import Stats from '@/components/Stats'
import ShortcutHelp from '@/components/ShortcutHelp'
import { useShortcuts } from '@/lib/keyboard'

type View = 'overview' | SectionCode | 'writing' | 'library' | 'stats'

/**
 * Seven destinations at full length do not fit one row at ANY width: even at
 * 1280px "Logical Reasoning · Reading Comprehension · Logic Games ·
 * Argumentative Writing" plus the brand exceeds the content column, and the
 * row wrapped — which pushed the header to 101px on desktop and 136px on a
 * phone, and desynchronised the `--site-header-h` sticky offset the drill
 * head and passage column hang from.
 *
 * (Eight before the concept catalog moved inside the library, which is where
 * the vocabulary belongs anyway — next to the articles that teach it.)
 *
 * So the bar is compact everywhere and the section codes carry the sections,
 * which is how test-takers refer to them anyway. `full` is the accessible
 * name and the tooltip, so a screen reader hears "Logical Reasoning" and a
 * first-time visitor can hover — and the Overview cards and each drill's own
 * heading still spell every section out.
 */
const NAV: { id: View; label: string; full: string }[] = [
  { id: 'overview', label: 'Overview', full: 'Overview' },
  { id: 'LR', label: 'LR', full: 'Logical Reasoning' },
  { id: 'RC', label: 'RC', full: 'Reading Comprehension' },
  { id: 'LG', label: 'LG', full: 'Logic Games' },
  { id: 'writing', label: 'Writing', full: 'Argumentative Writing' },
  { id: 'library', label: 'Library', full: 'Library & concepts' },
  { id: 'stats', label: 'Stats', full: 'Stats' },
]

/**
 * How the header behaves as the page scrolls (narrow viewports only — the CSS
 * that gives these classes effect is inside a `max-width: 819px` query, since
 * the wide layout's sticky drill head and passage column hang off a header of
 * known height).
 *
 *   top       — at rest at the top of the page: brand row and nav strip.
 *   condensed — scrolled at all: the brand row collapses, leaving the nav.
 *   hidden    — scrolling down past a screenful: the whole bar slides away.
 *
 * Scrolling up returns to `condensed` immediately at any depth, so the nav is
 * always one short upward flick away rather than a scroll back to the top.
 */
type HeaderState = 'top' | 'condensed' | 'hidden'

/** Below this the page counts as "at the top" and the header is never hidden. */
const AT_TOP_PX = 8
/** Don't hide until the reader is past roughly a screenful of content. */
const HIDE_AFTER_PX = 220
/** Ignore scrolls smaller than this: momentum and rubber-banding both jitter. */
const DIRECTION_DELTA_PX = 6

function indexOfView(view: View): number {
  const i = NAV.findIndex((n) => n.id === view)
  return i === -1 ? 0 : i
}

export default function Page() {
  const [view, setView] = useState<View>('overview')
  const [announcement, setAnnouncement] = useState('')
  const navRef = useRef<HTMLElement | null>(null)
  const [navScrollable, setNavScrollable] = useState(false)
  const [headerState, setHeaderState] = useState<HeaderState>('top')
  const [helpOpen, setHelpOpen] = useState(false)

  // The two bindings that operate the help dialog keep working while it is
  // open — everything else on the page is suspended behind it.
  useShortcuts(
    {
      '?': () => setHelpOpen((v) => !v),
      // Bound only while the dialog is up. Claiming Escape unconditionally
      // would swallow it from anything else that wants it — the writing
      // editor uses it to leave the text field.
      ...(helpOpen ? { Escape: () => setHelpOpen(false) } : {}),
    },
    { whileModal: true },
  )

  // Section movement is `[` / `]` rather than arrows, so the answer radiogroup
  // keeps the arrow keys for choosing between choices.
  useShortcuts({
    '[': () => setView((v) => NAV[Math.max(0, indexOfView(v) - 1)].id),
    ']': () => setView((v) => NAV[Math.min(NAV.length - 1, indexOfView(v) + 1)].id),
  })

  // Direction-aware header. A plain "hide past N pixels" rule strands the nav
  // behind a long scroll back; keying on direction means a flick upward brings
  // it straight back, which is the behaviour every reader already expects.
  useEffect(() => {
    let lastY = window.scrollY
    let queued = false

    const update = () => {
      queued = false
      const y = window.scrollY
      const dy = y - lastY
      if (y > AT_TOP_PX && Math.abs(dy) < DIRECTION_DELTA_PX) return
      lastY = y
      if (y <= AT_TOP_PX) setHeaderState('top')
      else if (dy > 0 && y > HIDE_AFTER_PX) setHeaderState('hidden')
      else setHeaderState('condensed')
    }

    const onScroll = () => {
      if (queued) return
      queued = true
      requestAnimationFrame(update)
    }

    window.addEventListener('scroll', onScroll, { passive: true })
    update()
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // A scrolling nav can leave the current destination off-screen — most
  // obviously when a phone lands on Stats, the last pill. Pull the active one
  // into view on every change.
  useEffect(() => {
    const nav = navRef.current
    if (!nav) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    nav.querySelector('[aria-current="page"]')?.scrollIntoView({
      inline: 'center',
      block: 'nearest',
      behavior: reduced ? 'auto' : 'smooth',
    })
    // A destination change starts a new reading task, so put the reader at the
    // top of it and give the header back. Without this, switching away from a
    // drill you had scrolled deep into drops you into the middle of the next
    // view with the header still hidden.
    window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' })
    setHeaderState('top')
  }, [view])

  // Fade the trailing edge only while the strip really does overflow. Observed
  // rather than measured once: the labels are the same at every width, so
  // whether the row overflows depends entirely on the viewport, and a
  // rotation or a resized window would otherwise keep a stale answer.
  useEffect(() => {
    const nav = navRef.current
    if (!nav) return
    const measure = () => setNavScrollable(nav.scrollWidth > nav.clientWidth + 1)
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(measure)
    ro.observe(nav)
    return () => ro.disconnect()
  }, [])

  return (
    <>
      <header
        className={`site-header site-header-${headerState}`}
        // A hidden header is still in the tab order, and a browser will not
        // always scroll a transformed sticky element into view — so any focus
        // landing inside brings it back rather than leaving a keyboard user
        // typing into something they cannot see.
        onFocus={() => setHeaderState((s) => (s === 'hidden' ? 'condensed' : s))}
      >
        <div className="wrap">
          <div className="brand">
            <span aria-hidden="true">⚖️</span> LSAT Practice
            <span className="brand-sub">Law AI · static edition</span>
          </div>
          <nav
            aria-label="Sections"
            className={'nav' + (navScrollable ? ' nav-scrollable' : '')}
            ref={navRef}
          >
            {NAV.map((n) => (
              <button
                key={n.id}
                type="button"
                className={'nav-link' + (view === n.id ? ' nav-link-active' : '')}
                aria-current={view === n.id ? 'page' : undefined}
                aria-label={n.full}
                title={n.full}
                onClick={() => setView(n.id)}
              >
                {n.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main id="view" className="wrap" tabIndex={-1}>
        {/* Keyed so switching destination replays the entrance animation. The
            wrapper, not <main> itself: remounting the landmark would move the
            skip-link target out from under a keyboard user mid-navigation. */}
        <div className="view-anim" key={view}>
          {view === 'overview' && <Overview onStart={(s) => setView(s)} />}
          {SECTIONS.includes(view as SectionCode) && (
            <Drill section={view as SectionCode} onAnnounce={setAnnouncement} />
          )}
          {view === 'writing' && <Writing onAnnounce={setAnnouncement} />}
          {view === 'library' && <Library onAnnounce={setAnnouncement} />}
          {view === 'stats' && <Stats />}
        </div>
      </main>

      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>

      {helpOpen && <ShortcutHelp onClose={() => setHelpOpen(false)} />}

      {/* Deliberately NOT a <footer>: the root layout renders the UPL
          disclaimer as this page's one contentinfo landmark, and a bare
          <footer> here would make a second. Same defect the platform homepage
          had (BL-20260830-06). */}
      <div className="site-footer">
        <div className="wrap">
          <span>
            {content.counts.total} items · updated{' '}
            {new Date(content.generated_at).toISOString().slice(0, 10)} ·{' '}
            <button
              type="button"
              className="linklike"
              onClick={() => setHelpOpen(true)}
            >
              Keyboard shortcuts (<kbd>?</kbd>)
            </button>
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
