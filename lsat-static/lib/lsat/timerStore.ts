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
 *
 * This file is the single source of truth for *both* front ends. The static
 * export cannot import across app roots, so `make ui-sync` copies it verbatim
 * to `lsat-static/lib/lsat/timerStore.ts` and ux_audit R12 fails the build on
 * any drift (BL-20260830-04). Keep it framework-plain — one `react` import for
 * nothing, no `@/lib/api`, no settings catalog — or the mirror stops compiling
 * on the static side.
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
  /**
   * Questions still to answer in the running section, or null when the drill
   * cannot say. Drives the `N:NN left / q` readout, which is the number a
   * student actually paces against. `null`, not 0: "no stack open" and "you
   * have finished the stack" are different, and only the second one should
   * blank the readout by way of `secondsPerQuestion`.
   */
  remainingQuestions: number | null
  /**
   * Which section this clock is timing, or null before a drill has claimed it.
   *
   * The store has to be what remembers this, because it is the only thing that
   * outlives the drill. A component cannot tell "a fresh mount of the section
   * already running" from "a fresh mount of a different section": both are a
   * first render, and any ref it might compare against is reinitialised along
   * with it. The store is never remounted, so it can (BL-20260916-03).
   *
   * A plain string rather than `SectionCode` — this file is mirrored into the
   * static export and has to stay framework- and catalog-plain, and the clock
   * does not care what the sections are called.
   */
  section: string | null
}

const INITIAL: LsatTimerState = {
  durationSeconds: LSAT_SECTION_SECONDS,
  remainingSeconds: LSAT_SECTION_SECONDS,
  running: false,
  answered: 0,
  answeredSeconds: 0,
  remainingQuestions: null,
  section: null,
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
      // Deliberately not restored: the panel that knows how many questions are
      // left has not mounted yet, and a stale count from the last page load
      // would quote a pace for a stack that is no longer on screen. Whichever
      // panel mounts sets it again within a frame.
      remainingQuestions: null,
      // Restored, unlike the count above, and that asymmetry is the point: the
      // section is how the drill that mounts next recognises this clock as its
      // own. Dropping it would make every refresh look like a section switch
      // and reset the very clock this rehydrate exists to save.
      section: typeof p.section === 'string' ? p.section : null,
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

/**
 * Start a fresh section: the clock back to full *and* the pace counters clear.
 *
 * Deliberately not the same thing as `resetTimer`, which is the Reset button —
 * a learner who resets the clock part-way through a drill has still answered
 * the questions they answered, and throwing their average away would be a
 * surprise. Switching sections is the case where none of it carries over.
 */
export function resetSection(): void {
  deadline = null
  stopTicking()
  emit({
    running: false,
    remainingSeconds: state.durationSeconds,
    answered: 0,
    answeredSeconds: 0,
    remainingQuestions: null,
  })
}

/**
 * Claim the clock for `section`, resetting it only if it belonged to another.
 *
 * This is what a drill calls on mount, and it exists because the caller cannot
 * make that decision itself. `resetSection` above has always been correct; it
 * was simply unreachable. The static drill guarded it with
 * `useRef(section)` — sound only if the component survives the switch, and it
 * does not: `app/page.tsx` keys the view wrapper on `view`, so changing
 * section unmounts the drill and remounts a new one whose ref initialises to
 * the *new* section. The guard's condition was then true on every first run,
 * the early return always taken, and the reset never executed — while the
 * module-level store, by design, kept the previous section's counters. RC
 * inherited LR's clock and LG inherited RC's average (BL-20260916-03).
 *
 * Deciding it here fixes that without the caller needing to know whether it
 * was remounted, because the store is the one participant that was not.
 *
 * Idempotent on purpose. Re-claiming the section already running is a no-op,
 * so a remount *within* a section — moving the widget between docks, or a
 * refresh restoring through `rehydrate` — keeps its clock. That is the
 * property this store was hoisted out of `useState` to provide
 * (BL-20260830-04) and the one thing this must not cost.
 *
 * @returns true when a new section was actually started, so a caller can clear
 *   its own per-section state on the same event rather than guessing at it.
 */
export function beginSection(section: string): boolean {
  if (state.section === section) return false
  const switching = state.section !== null
  emit({ section })
  // The first section claimed on a page has nothing to carry over, so claiming
  // it must not wipe a clock the reader has already set going — choosing a
  // 10-minute preset, pressing Start, and then opening a drill is exactly that
  // case. Only a *change* of section resets.
  if (!switching) return false
  resetSection()
  return true
}

export function setTimerDuration(seconds: number): void {
  const d = Math.max(0, Math.floor(seconds))
  deadline = null
  stopTicking()
  emit({ durationSeconds: d, remainingSeconds: d, running: false })
}

/**
 * How many questions the drill still has to answer — the denominator of the
 * `N:NN left / q` readout (BL-20260829-01).
 *
 * The panel showing the questions is the only thing that knows this, and it is
 * a different React subtree from the timer whenever the clock is docked in the
 * sidebar or inspector, so it cannot be a prop. `null` clears it, which is
 * what a panel does on unmount — a stack you have navigated away from must not
 * keep quoting a pace.
 *
 * Deliberately *not* cleared by `resetTimer`: restarting the clock does not
 * change how many questions are in front of you, and the panel would have no
 * reason to re-announce the count. `resetSection` clears it, because that is
 * the drill moving on.
 */
export function setRemainingQuestions(n: number | null): void {
  const next = n === null ? null : Math.max(0, Math.floor(n))
  if (next === state.remainingQuestions) return
  emit({ remainingQuestions: next })
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
