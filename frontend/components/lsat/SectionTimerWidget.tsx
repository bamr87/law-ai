'use client'

import { useSetting } from '@/components/shell/useSetting'
import {
  averageSecondsPerQuestion,
  formatClock,
  secondsPerQuestion,
} from '@/lib/lsatTimer'
import {
  getTimerServerSnapshot,
  getTimerSnapshot,
  isSectionInProgress,
  pauseTimer,
  resetTimer,
  setTimerDuration,
  startTimer,
  subscribeTimer,
} from '@/lib/lsat/timerStore'
import { resolveDock } from '@/lib/shell/docks'
import {
  DOCKS,
  TIMER_DURATIONS,
  lsatTimerDock,
  lsatTimerDuration,
  lsatTimerVisible,
  type Dock,
  type TimerDuration,
} from '@/lib/settings/catalog'
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'

const DOCK_LABEL: Record<Dock, string> = {
  sidebar: 'Sidebar',
  inspector: 'Inspector',
  inline: 'In page',
}

const DURATION_LABEL: Record<TimerDuration, string> = {
  '5': '5 min',
  '10': '10 min',
  '35': '35 min',
}

export function useLsatTimer() {
  return useSyncExternalStore(
    subscribeTimer,
    getTimerSnapshot,
    getTimerServerSnapshot,
  )
}

/**
 * The LSAT section clock. A *view* over `lib/lsat/timerStore` — it owns no
 * clock state, so moving it between docks never resets a running section.
 *
 * `dock` is the zone asking to render it; the widget draws only if that zone
 * matches the user's preference, which is what lets one component serve three
 * mount points without the shell knowing where it belongs.
 *
 * static-parity: none — the static export has its own section clock at
 * `lsat-static/components/SectionTimer.tsx`. Docking is meaningless there:
 * it has no sidebar or inspector to move between, so spec 046 pinned its
 * drill head instead (BL-20260830-04 still tracks unifying the two).
 */
export default function SectionTimerWidget({
  dock,
  onOwnRoute,
  openDocks,
}: {
  dock: Dock
  /** True when rendering on an LSAT route. */
  onOwnRoute: boolean
  /** Zones currently on screen, so a collapsed panel does not hide the clock. */
  openDocks: Dock[]
}) {
  const [preferred, setPreferred] = useSetting(lsatTimerDock)
  const [shownWhenIdle, setShownWhenIdle] = useSetting(lsatTimerVisible)
  const [duration, setDuration] = useSetting(lsatTimerDuration)
  const timer = useLsatTimer()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!menuOpen) return
    const onDown = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  // Adopt the saved drill length on mount, but never over a section already
  // under way — the store rehydrates a running clock from sessionStorage, and
  // resetting that to the preference would be the one thing a timer must not
  // do (BL-20260829-02).
  const wanted = Number(duration) * 60
  useEffect(() => {
    const s = getTimerSnapshot()
    if (isSectionInProgress(s)) return
    if (s.durationSeconds === wanted) return
    setTimerDuration(wanted)
  }, [wanted])

  // Off the LSAT routes the clock only follows you while a section is
  // actually in progress — otherwise every other module would carry a stopped
  // 35:00 for no reason. The same rule serves `lsat.timer.visible` (spec 051):
  // a user may hide an idle clock, never a running one.
  const inProgress = isSectionInProgress(timer)
  if (!onOwnRoute && !inProgress) return null
  if (!shownWhenIdle && !inProgress) return null
  if (dock !== resolveDock(preferred, { onOwnRoute, openDocks })) return null

  const { remainingSeconds, running, durationSeconds } = timer
  const expired = remainingSeconds === 0
  const warn = remainingSeconds > 0 && remainingSeconds <= 5 * 60
  const urgent = remainingSeconds > 0 && remainingSeconds <= 60
  // Straight from the store, never a prop: the clock docks into the sidebar
  // and the inspector, which are parallel-route slots — different React trees
  // from the panel that knows how many questions are left (BL-20260829-01).
  const pace = secondsPerQuestion(
    remainingSeconds,
    timer.remainingQuestions ?? 0,
  )
  const avg = averageSecondsPerQuestion(timer.answeredSeconds, timer.answered)
  const compact = dock !== 'inline'

  const clockClass =
    'font-mono tabular-nums ' +
    (compact ? 'text-2xl ' : 'text-lg ') +
    (expired || urgent
      ? 'text-red-300'
      : warn
        ? 'text-amber-300'
        : 'text-slate-100')

  return (
    <section
      aria-label="LSAT section timer"
      data-testid="lsat-timer"
      data-dock={dock}
      className={
        compact
          ? 'rounded-lg border border-slate-800 bg-slate-900/60 p-3'
          : 'flex flex-wrap items-center gap-3'
      }
    >
      <div className={compact ? '' : 'flex-1'}>
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] uppercase tracking-wider text-slate-400">
            Section timer
          </span>
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              aria-label="Section timer options"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((v) => !v)}
              className="rounded px-1.5 py-0.5 text-xs leading-none text-slate-400 transition hover:bg-slate-800 hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400"
            >
              <span aria-hidden="true">⋯</span>
            </button>
            {menuOpen && (
              <div
                role="menu"
                aria-label="Section timer options"
                style={{ zIndex: 'var(--z-popover)' }}
                className="absolute right-0 top-full mt-1 w-36 overflow-hidden rounded-md border border-slate-700 bg-slate-900 shadow-xl"
              >
                <p className="px-3 pb-1 pt-2 text-[10px] uppercase tracking-wider text-slate-400">
                  Move to
                </p>
                {DOCKS.map((d) => (
                  <button
                    key={d}
                    type="button"
                    role="menuitemradio"
                    aria-checked={d === preferred}
                    onClick={() => {
                      setPreferred(d)
                      setMenuOpen(false)
                    }}
                    className={
                      'flex w-full items-center justify-between px-3 py-1.5 text-left text-xs transition focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-amber-400 ' +
                      (d === preferred
                        ? 'bg-amber-500/10 text-amber-200'
                        : 'text-slate-300 hover:bg-slate-800')
                    }
                  >
                    {DOCK_LABEL[d]}
                    {d === preferred && <span aria-hidden="true">✓</span>}
                  </button>
                ))}
                {/* Hiding is a layout choice like docking, so it lives in the
                    same menu. It only applies while idle — the clock of a
                    section in progress is never hidden by anything. */}
                <button
                  type="button"
                  role="menuitemcheckbox"
                  aria-checked={shownWhenIdle}
                  onClick={() => {
                    setShownWhenIdle(!shownWhenIdle)
                    setMenuOpen(false)
                  }}
                  className={
                    'flex w-full items-center justify-between border-t border-slate-800 px-3 py-1.5 text-left text-xs transition focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-amber-400 ' +
                    (shownWhenIdle
                      ? 'text-slate-300 hover:bg-slate-800'
                      : 'bg-amber-500/10 text-amber-200')
                  }
                >
                  Show when idle
                  {shownWhenIdle && <span aria-hidden="true">✓</span>}
                </button>
                {/* Drill length. Locked once a section is under way: changing
                    the clock mid-run would silently discard the time already
                    spent, and a student who wanted that has Reset. */}
                <p className="border-t border-slate-800 px-3 pb-1 pt-2 text-[10px] uppercase tracking-wider text-slate-400">
                  Length
                </p>
                {TIMER_DURATIONS.map((d) => (
                  <button
                    key={d}
                    type="button"
                    role="menuitemradio"
                    aria-checked={d === duration}
                    disabled={inProgress}
                    title={
                      inProgress
                        ? 'Finish or reset the section before changing its length'
                        : undefined
                    }
                    onClick={() => {
                      setDuration(d)
                      setTimerDuration(Number(d) * 60)
                      setMenuOpen(false)
                    }}
                    className={
                      'flex w-full items-center justify-between px-3 py-1.5 text-left text-xs transition focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-amber-400 disabled:cursor-not-allowed disabled:opacity-40 ' +
                      (d === duration
                        ? 'bg-amber-500/10 text-amber-200'
                        : 'text-slate-300 hover:bg-slate-800')
                    }
                  >
                    {DURATION_LABEL[d]}
                    {d === duration && <span aria-hidden="true">✓</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div
          className={
            compact
              ? 'mt-1 flex flex-col gap-0.5'
              : 'flex items-baseline gap-2'
          }
        >
          <span
            role="timer"
            aria-label="Section time remaining"
            className={clockClass}
          >
            {formatClock(remainingSeconds)}
          </span>
          {expired && (
            <span className="text-xs font-medium text-red-300" role="status">
              Time&apos;s up — you can keep practicing
            </span>
          )}
          {!expired && pace != null && (
            <span
              className="text-xs tabular-nums text-slate-400"
              aria-label="Time remaining per question"
            >
              {formatClock(pace)} left / q
            </span>
          )}
          {avg != null && (
            <span
              className="text-xs tabular-nums text-slate-300"
              aria-label="Average time per question"
            >
              avg {formatClock(avg)} / q
            </span>
          )}
        </div>
      </div>

      <div className={'flex items-center gap-1.5 ' + (compact ? 'mt-2' : '')}>
        {!expired && (
          <button
            type="button"
            onClick={() => (running ? pauseTimer() : startTimer())}
            className="rounded-md border border-slate-700 bg-slate-900/60 px-2 py-1 text-[11px] font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400"
          >
            {running ? 'Pause' : 'Start'}
          </button>
        )}
        <button
          type="button"
          onClick={resetTimer}
          disabled={remainingSeconds === durationSeconds && !running}
          className="rounded-md border border-slate-700 bg-slate-900/60 px-2 py-1 text-[11px] font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Reset
        </button>
      </div>
    </section>
  )
}

export { isSectionInProgress }
