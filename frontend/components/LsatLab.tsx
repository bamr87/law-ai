'use client'

/**
 * LSAT Lab — multi-section practice + AI tutor.
 *
 * The component is a top-level tab router. Each section gets its own
 * subview specialised for the question format (LR isolated stems, RC
 * passages, LG game setup + rules). Overview is a static documentation
 * surface. Stats hangs off the global header so it follows the learner
 * across tabs.
 *
 * This file owns the state the tabs share — the active tab, the session
 * score, the all-time stats — and nothing else. Every panel lives in its own
 * file under `components/lsat/` (BL-20260830-02, phase 1: a behaviour-
 * preserving split; phase 2 moves them onto `frontend/ui` primitives once
 * spec 039 lands):
 *
 *   OverviewPanel · LrPanel · PassagePanel (RC + LG) · WritingPanel (WS) ·
 *   QuestionCard · TutorPane · StatsPanel · AuthoringPanel · LabPrimitives ·
 *   labTabs
 *
 * Study material is deliberately *not* here. The concept catalog used to be a
 * seventh tab in this bar; it now lives in the library
 * (`/lsat/library`, `components/LsatLibrary.tsx`) next to the articles that
 * teach those concepts, so the lab is the place you practise and the library
 * is the place you read. Post-grade concept references still resolve inline
 * (`ConceptRefs`) — leaving a graded question to look a term up was never the
 * point.
 */

import { useRovingTabIndex } from '@/components/shell/useRovingTabIndex'
import { StickyToolbar } from '@/components/shell/PageLayout'
import { fetchLsatStats, type LsatStats } from '@/lib/api'
import SectionTimerWidget from '@/components/lsat/SectionTimerWidget'
import { recordAnswer } from '@/lib/lsat/timerStore'
import AuthoringPanel from '@/components/lsat/AuthoringPanel'
import { Stat } from '@/components/lsat/LabPrimitives'
import LrPanel from '@/components/lsat/LrPanel'
import OverviewPanel from '@/components/lsat/OverviewPanel'
import PassagePanel from '@/components/lsat/PassagePanel'
import StatsPanel from '@/components/lsat/StatsPanel'
import WritingPanel from '@/components/lsat/WritingPanel'
import {
  TAB_IDS,
  TABS,
  tabId,
  tabPanelId,
  type SessionScore,
  type Tab,
} from '@/components/lsat/labTabs'
import { useUrlState, useUrlWrite } from '@/lib/shell/viewState'
import { useCallback, useEffect, useState } from 'react'

// The ARIA id helpers stay importable from here for anything that linked a
// tab to its panel before the split.
export { tabId, tabPanelId }

export default function LsatLab() {
  // The tab is URL state, not component state (BL-20260831-02): `?tab=RC` is a
  // link a study group can share, and Back steps between sections instead of
  // leaving the lab.
  // A concept deep link (BL-20260905-01). The library's catalog says "drill
  // them in the lab"; `/lsat?concept=<id>` is what makes that one click rather
  // than "open the lab, find the section, filter by hand". A concept in the URL
  // also decides where the lab opens — on the drill, not on Overview — while
  // an explicit `?tab=` still wins, so a link can name both.
  const [concept] = useUrlState<string>('concept', { fallback: '' })
  const [tab, setTab] = useUrlState<Tab>('tab', {
    fallback: concept ? 'LR' : 'overview',
    allowed: TAB_IDS,
  })
  // Dropping the filter has to pin the tab in the same navigation: the concept
  // is what was defaulting the lab onto the drill, so removing it alone would
  // bounce the learner back to Overview. `replace`, not `push` — dismissing a
  // filter is not a place you want Back to return you to.
  const writeUrl = useUrlWrite('replace')
  const clearConcept = useCallback(
    () => writeUrl({ concept: null, tab }),
    [tab, writeUrl],
  )
  const [globalStats, setGlobalStats] = useState<LsatStats | null>(null)
  const [session, setSession] = useState<SessionScore>({
    attempts: 0,
    correct: 0,
    assisted: 0,
  })
  const refreshStats = useCallback(async () => {
    try {
      setGlobalStats(await fetchLsatStats())
    } catch {
      /* non-fatal */
    }
  }, [])

  useEffect(() => {
    void refreshStats()
  }, [refreshStats])

  const onAttempt = useCallback(
    (correct: boolean, elapsedSeconds = 0, hintsUsed = 0) => {
      setSession((s) => ({
        attempts: s.attempts + 1,
        correct: s.correct + (correct ? 1 : 0),
        assisted: s.assisted + (hintsUsed > 0 ? 1 : 0),
      }))
      // Pace lives in the timer store, not here: the timer can be docked in a
      // side panel, which is a different React subtree from this page.
      recordAnswer(elapsedSeconds)
      void refreshStats()
    },
    [refreshStats],
  )

  return (
    <div className="space-y-6">
      <Header session={session} globalStats={globalStats} />
      <TabBar tab={tab} onChange={setTab} />
      {/* tabIndex 0: the panel is scrollable content, so it has to be
        * reachable by keyboard once the tab bar hands focus on. */}
      <div
        role="tabpanel"
        id={tabPanelId(tab)}
        aria-labelledby={tabId(tab)}
        tabIndex={0}
        className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400"
      >
        {tab === 'overview' && <OverviewPanel onJump={setTab} />}
        {tab === 'LR' && (
          <LrPanel
            onAttempt={onAttempt}
            concept={concept || undefined}
            onClearConcept={concept ? clearConcept : undefined}
          />
        )}
        {tab === 'RC' && <PassagePanel section="RC" onAttempt={onAttempt} />}
        {tab === 'LG' && <PassagePanel section="LG" onAttempt={onAttempt} />}
        {tab === 'WS' && <WritingPanel />}
        {tab === 'stats' && <StatsPanel session={session} stats={globalStats} />}
        {tab === 'authoring' && <AuthoringPanel />}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Header + nav
// ---------------------------------------------------------------------------

function Header({
  session,
  globalStats,
}: {
  session: SessionScore
  globalStats: LsatStats | null
}) {
  const accuracy =
    session.attempts > 0
      ? Math.round((session.correct / session.attempts) * 100)
      : null
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3 text-sm backdrop-blur">
      {/* The timer is dockable (spec 043). It renders here only when the user
        * has chosen the "In page" dock; otherwise it lives in a side panel and
        * this slot collapses. */}
      <SectionTimerWidget
        dock="inline"
        onOwnRoute
        openDocks={['sidebar', 'inspector']}
      />
      <div className="flex flex-wrap items-center justify-end gap-4">
        <Stat
          label="Session"
          value={`${session.correct}/${session.attempts}`}
          sub={
            accuracy != null
              ? session.assisted > 0
                ? `${accuracy}% · ${session.assisted} assisted`
                : `${accuracy}%`
              : '—'
          }
        />
        <span className="h-6 w-px bg-slate-800" />
        <Stat
          label="All-time"
          value={
            globalStats ? `${globalStats.correct}/${globalStats.attempts}` : '—'
          }
          sub={
            globalStats && globalStats.attempts > 0
              ? `${Math.round(globalStats.accuracy * 100)}%`
              : '—'
          }
        />
      </div>
    </div>
  )
}

function TabBar({ tab, onChange }: { tab: Tab; onChange: (t: Tab) => void }) {
  // Pinned under the page header: the section switcher is the control a
  // student reaches for most, and hunting for it after scrolling through a
  // reading-comprehension passage is the difference between a drill and a
  // chore.
  //
  // One tab stop, arrows move within it (WAI-ARIA tabs pattern). Before this
  // the bar was seven separate tab stops with dead arrow keys, so a keyboard
  // user had to page through the whole switcher to reach the questions.
  const roving = useRovingTabIndex({
    count: TABS.length,
    activeIndex: TABS.findIndex((t) => t.id === tab),
    onActivate: (i) => onChange(TABS[i].id),
  })

  return (
    <StickyToolbar>
      <div
        role="tablist"
        aria-label="LSAT Lab sections"
        className="flex flex-wrap gap-1"
      >
        {TABS.map((t, i) => {
          const active = t.id === tab
          return (
            <button
              key={t.id}
              {...roving.itemProps(i)}
              id={tabId(t.id)}
              role="tab"
              aria-selected={active}
              aria-controls={tabPanelId(t.id)}
              title={t.hint}
              onClick={() => onChange(t.id)}
              className={
                'tap-target min-w-[120px] flex-1 rounded-lg px-3 py-2 text-sm font-medium transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 ' +
                (active
                  ? 'bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-md shadow-blue-500/20'
                  : 'text-slate-300 hover:bg-slate-800/60 hover:text-white')
              }
            >
              {t.label}
            </button>
          )
        })}
      </div>
    </StickyToolbar>
  )
}
