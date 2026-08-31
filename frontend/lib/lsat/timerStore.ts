/**
 * The LSAT section clock, as a module-level store rather than component state.
 *
 * This is load-bearing, not a refactor for its own sake. The timer is dockable
 * (sidebar / inspector / in page) and the sidebar is a **parallel-route slot** —
 * a different React subtree from the page. A timer that kept its clock in
 * `useState` would unmount and remount when it moved, resetting a running
 * 35-minute section. Hoisting the clock here makes every dock a *view* of one
 * clock, so moving it is free.
 *
 * It also fixes a latent bug the single-mount design hid: two mounted timers
 * used to run two independent clocks.
 *
 * Deadline-based, not tick-accumulating: browsers throttle timers in
 * background tabs, so counting intervals drifts. Subtracting from a wall-clock
 * deadline does not.
 */

import { LSAT_SECTION_SECONDS } from '@/lib/lsatTimer'

export interface LsatTimerState {
  durationSeconds: number
  remainingSeconds: number
  running: boolean
  /** Pace inputs — the widget renders them wherever it is docked, so they
   * cannot live in the LSAT page's component tree either. */
  answered: number
  answeredSeconds: number
}

const INITIAL: LsatTimerState = {
  durationSeconds: LSAT_SECTION_SECONDS,
  remainingSeconds: LSAT_SECTION_SECONDS,
  running: false,
  answered: 0,
  answeredSeconds: 0,
}

const PERSIST_KEY = 'law-ai.lsat.timer.v1'

let state: LsatTimerState = INITIAL
let listeners = new Set<() => void>()
let deadline: number | null = null
let ticker: ReturnType<typeof setInterval> | null = null

/**
 * sessionStorage, so an accidental refresh mid-section does not cost a student
 * their clock. Not localStorage: a 35-minute section is a tab-lifetime thing,
 * and finding yesterday's half-spent timer waiting for you would be worse than
 * starting fresh.
 *
 * The *deadline* is persisted, not the remaining seconds, so time spent
 * reloading still counts against a running section — which is what a real
 * proctored clock does.
 */
function persist(): void {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(
      PERSIST_KEY,
      JSON.stringify({ ...state, deadline }),
    )
  } catch {
    /* private mode or quota — durability is a nicety, never a failure */
  }
}

function rehydrate(): void {
  if (typeof window === 'undefined') return
  try {
    const raw = window.sessionStorage.getItem(PERSIST_KEY)
    if (!raw) return
    const p = JSON.parse(raw) as Partial<LsatTimerState> & {
      deadline?: number | null
    }
    if (typeof p.durationSeconds !== 'number') return

    const restored: LsatTimerState = {
      durationSeconds: p.durationSeconds,
      remainingSeconds:
        typeof p.remainingSeconds === 'number'
          ? p.remainingSeconds
          : p.durationSeconds,
      running: false,
      answered: typeof p.answered === 'number' ? p.answered : 0,
      answeredSeconds:
        typeof p.answeredSeconds === 'number' ? p.answeredSeconds : 0,
    }

    if (p.running && typeof p.deadline === 'number') {
      const left = Math.max(0, Math.ceil((p.deadline - Date.now()) / 1000))
      restored.remainingSeconds = left
      if (left > 0) {
        state = { ...restored, running: true }
        deadline = p.deadline
        startTicking()
        return
      }
    }
    state = restored
  } catch {
    /* corrupt blob — start clean rather than crash the drill */
  }
}

function emit(next: Partial<LsatTimerState>): void {
  state = { ...state, ...next }
  persist()
  for (const l of listeners) l()
}

function stopTicking(): void {
  if (ticker !== null) {
    clearInterval(ticker)
    ticker = null
  }
}

function startTicking(): void {
  stopTicking()
  // 250ms so the displayed second flips promptly without a full rAF loop.
  ticker = setInterval(() => {
    if (deadline === null) return
    const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
    if (left === 0) {
      deadline = null
      stopTicking()
      emit({ remainingSeconds: 0, running: false })
      return
    }
    if (left !== state.remainingSeconds) emit({ remainingSeconds: left })
  }, 250)
}

export function subscribeTimer(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function getTimerSnapshot(): LsatTimerState {
  return state
}

/** Server render has no clock; hand back the pristine state. */
export function getTimerServerSnapshot(): LsatTimerState {
  return INITIAL
}

export function startTimer(): void {
  if (state.running || state.remainingSeconds <= 0) return
  deadline = Date.now() + state.remainingSeconds * 1000
  emit({ running: true })
  startTicking()
}

export function pauseTimer(): void {
  if (!state.running) return
  const left =
    deadline === null
      ? state.remainingSeconds
      : Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
  deadline = null
  stopTicking()
  emit({ running: false, remainingSeconds: left })
}

export function resetTimer(): void {
  deadline = null
  stopTicking()
  emit({ running: false, remainingSeconds: state.durationSeconds })
}

export function setTimerDuration(seconds: number): void {
  const d = Math.max(0, Math.floor(seconds))
  deadline = null
  stopTicking()
  emit({ durationSeconds: d, remainingSeconds: d, running: false })
}

/** Called by the drill on each graded question, to drive the pace readouts. */
export function recordAnswer(elapsedSeconds: number): void {
  emit({
    answered: state.answered + 1,
    answeredSeconds: state.answeredSeconds + Math.max(0, elapsedSeconds),
  })
}

/** True once the student has engaged the clock — what "follow me off the LSAT
 * routes" keys off. A paused-but-started section still counts as in progress. */
export function isSectionInProgress(s: LsatTimerState = state): boolean {
  return s.running || s.remainingSeconds < s.durationSeconds
}

/** Test seam — resets module state between cases. */
export function __resetTimerStore(): void {
  stopTicking()
  deadline = null
  listeners = new Set()
  state = INITIAL
  if (typeof window !== 'undefined') {
    try {
      window.sessionStorage.removeItem(PERSIST_KEY)
    } catch {
      /* ignore */
    }
  }
}

// Restore a section that was in progress when the tab last rendered. Runs once
// on module evaluation, before any component subscribes.
rehydrate()
