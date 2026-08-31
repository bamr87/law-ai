'use client'

/**
 * LSAT Lab — multi-section practice + concept catalog + AI tutor.
 *
 * The component is a top-level tab router. Each section gets its own
 * subview specialised for the question format (LR isolated stems, RC
 * passages, LG game setup + rules). Concepts and Overview are static
 * documentation surfaces. Stats hangs off the global header so it follows
 * the learner across tabs.
 */

import { useRovingTabIndex } from '@/components/shell/useRovingTabIndex'
import { StickyToolbar } from '@/components/shell/PageLayout'
import {
    approveLsatProposal,
    askLsatTutor,
    fetchLsatConcepts,
    fetchLsatGaps,
    fetchLsatPassage,
    fetchLsatPassages,
    fetchLsatProposals,
    fetchLsatQuestions,
    fetchLsatSections,
    fetchLsatStats,
    generateLsatProposals,
    gradeLsat,
    rejectLsatProposal,
    type LsatChoiceLabel,
    type LsatConcept,
    type LsatDifficulty,
    type LsatGapRow,
    type LsatGradeResponse,
    type LsatPassage,
    type LsatProposal,
    type LsatQuestion,
    type LsatSection,
    type LsatSectionInfo,
    type LsatStats,
    type LsatTutorResponse,
} from '@/lib/api'
import { QuestionElapsed } from '@/components/LsatTimer'
import SectionTimerWidget from '@/components/lsat/SectionTimerWidget'
import { recordAnswer } from '@/lib/lsat/timerStore'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

type Tab = 'overview' | 'LR' | 'RC' | 'LG' | 'concepts' | 'stats' | 'authoring'

const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: 'overview', label: 'Overview', hint: 'How the LSAT is built' },
  { id: 'LR', label: 'Logical Reasoning', hint: 'Drill short-argument questions' },
  { id: 'RC', label: 'Reading Comprehension', hint: 'Practice passage sets' },
  { id: 'LG', label: 'Logic Games', hint: 'Sequencing & grouping setups' },
  { id: 'concepts', label: 'Concepts', hint: 'Catalog of LSAT reasoning patterns' },
  { id: 'stats', label: 'Stats', hint: 'Your practice history' },
  { id: 'authoring', label: 'Authoring (HITL)', hint: 'Review AI-drafted questions' },
]

const DIFFICULTIES: { label: string; value: LsatDifficulty | 'any' }[] = [
  { label: 'Any', value: 'any' },
  { label: 'Easy', value: 'easy' },
  { label: 'Medium', value: 'med' },
  { label: 'Hard', value: 'hard' },
]

interface SessionScore {
  attempts: number
  correct: number
}

export default function LsatLab() {
  const [tab, setTab] = useState<Tab>('overview')
  const [globalStats, setGlobalStats] = useState<LsatStats | null>(null)
  const [session, setSession] = useState<SessionScore>({ attempts: 0, correct: 0 })
  const [pace, setPace] = useState({ answered: 0, totalSeconds: 0 })

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
    (correct: boolean, elapsedSeconds = 0) => {
      setSession((s) => ({
        attempts: s.attempts + 1,
        correct: s.correct + (correct ? 1 : 0),
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
      <Header session={session} globalStats={globalStats} pace={pace} />
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
        {tab === 'LR' && <LrPanel onAttempt={onAttempt} />}
        {tab === 'RC' && <PassagePanel section="RC" onAttempt={onAttempt} />}
        {tab === 'LG' && <PassagePanel section="LG" onAttempt={onAttempt} />}
        {tab === 'concepts' && <ConceptsPanel />}
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
  pace,
}: {
  session: SessionScore
  globalStats: LsatStats | null
  pace: { answered: number; totalSeconds: number }
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
          sub={accuracy != null ? `${accuracy}%` : '—'}
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

export const tabId = (t: Tab) => `lsat-tab-${t}`
export const tabPanelId = (t: Tab) => `lsat-panel-${t}`

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
                'min-w-[120px] flex-1 rounded-lg px-3 py-2 text-sm font-medium transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 ' +
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

// ---------------------------------------------------------------------------
// Overview panel — section docs
// ---------------------------------------------------------------------------

function OverviewPanel({ onJump }: { onJump: (t: Tab) => void }) {
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
          questions, or open the Concepts tab for a catalog of every reasoning
          pattern the test recycles.
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
                <Detail label="Items in bank" value={`${s.question_count}`} />
              </dl>
              {s.tips.length > 0 && (
                <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-300">
                  {s.tips.slice(0, 3).map((t) => (
                    <li key={t}>{t}</li>
                  ))}
                </ul>
              )}
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <button
                  onClick={() => onJump(s.code as Tab)}
                  className="inline-flex items-center gap-1 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow shadow-blue-500/20 transition hover:shadow-blue-500/40"
                >
                  Practice {s.code} →
                </button>
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

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="uppercase tracking-wider text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-slate-300">{value}</dd>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Logical Reasoning panel — single isolated question at a time
// ---------------------------------------------------------------------------

function LrPanel({
  onAttempt,
}: {
  onAttempt: (correct: boolean, elapsedSeconds: number) => void
}) {
  const [difficulty, setDifficulty] = useState<LsatDifficulty | 'any'>('any')
  const [question, setQuestion] = useState<LsatQuestion | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const body = await fetchLsatQuestions({
        limit: 1,
        section: 'LR',
        difficulty: difficulty === 'any' ? undefined : difficulty,
      })
      setQuestion(body.questions[0] ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [difficulty])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <section className="space-y-4">
      <Toolbar
        difficulty={difficulty}
        onDifficulty={setDifficulty}
        rightLabel={`Section: Logical Reasoning`}
      />
      {loading && <SkeletonQuestion />}
      {!loading && error && <ErrorBanner message={error} onRetry={load} />}
      {!loading && !error && question && (
        <QuestionCard
          question={question}
          onResolved={(r, elapsed) => onAttempt(r.correct, elapsed)}
          onNext={load}
        />
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Passage / game panel (shared by RC + LG)
// ---------------------------------------------------------------------------

function PassagePanel({
  section,
  onAttempt,
}: {
  section: 'RC' | 'LG'
  onAttempt: (correct: boolean, elapsedSeconds: number) => void
}) {
  const [passages, setPassages] = useState<LsatPassage[] | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [questions, setQuestions] = useState<LsatQuestion[]>([])
  const [activePassage, setActivePassage] = useState<LsatPassage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loadingPassages, setLoadingPassages] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [elapsedQuestionId, setElapsedQuestionId] = useState<string | null>(
    null,
  )

  useEffect(() => {
    void (async () => {
      setLoadingPassages(true)
      setError(null)
      try {
        const body = await fetchLsatPassages(section)
        setPassages(body.passages)
        if (body.passages.length > 0 && !activeId) {
          setActiveId(body.passages[0].id)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load passages')
      } finally {
        setLoadingPassages(false)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section])

  useEffect(() => {
    if (!activeId) return
    void (async () => {
      setLoadingDetail(true)
      setElapsedQuestionId(null)
      try {
        const body = await fetchLsatPassage(activeId)
        setActivePassage(body.passage)
        setQuestions(body.questions)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load passage')
      } finally {
        setLoadingDetail(false)
      }
    })()
  }, [activeId])

  const headline = section === 'RC' ? 'Reading Comprehension' : 'Logic Games'

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3 backdrop-blur">
        <div className="text-xs uppercase tracking-wider text-slate-500">
          Section: {headline}
        </div>
        {passages && passages.length > 0 && (
          <div className="flex items-center gap-2">
            <label
              htmlFor="passage-select"
              className="text-xs uppercase tracking-wider text-slate-500"
            >
              {section === 'LG' ? 'Game' : 'Passage'}
            </label>
            <select
              id="passage-select"
              value={activeId ?? ''}
              onChange={(e) => setActiveId(e.target.value)}
              className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200 focus:border-blue-500 focus-ring"
            >
              {passages.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {loadingPassages && <SkeletonGrid />}
      {error && <ErrorBanner message={error} />}
      {!loadingPassages && passages && passages.length === 0 && (
        <p className="text-sm text-slate-400">
          No {headline.toLowerCase()} passages have been authored yet.
        </p>
      )}

      {activePassage && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <PassageReader passage={activePassage} />
          <div className="space-y-4">
            {loadingDetail && <SkeletonQuestion />}
            {!loadingDetail &&
              questions.map((q) => (
                <QuestionCard
                  key={q.id}
                  question={q}
                  onResolved={(r, elapsed) => onAttempt(r.correct, elapsed)}
                  compact
                  elapsedEnabled={elapsedQuestionId === q.id}
                  onActivate={() => setElapsedQuestionId(q.id)}
                />
              ))}
            {!loadingDetail && questions.length === 0 && (
              <p className="text-sm text-slate-400">
                No questions linked to this {section === 'LG' ? 'game' : 'passage'}.
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

function PassageReader({ passage }: { passage: LsatPassage }) {
  return (
    <article className="shell-sticky-aside shell-panel-scroll max-h-[calc(100dvh-var(--shell-masthead-h)-var(--shell-pageheader-h)-var(--shell-toolbar-h)-3rem)] rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur">
      <div className="text-[11px] uppercase tracking-wider text-amber-400">
        {passage.section === 'LG' ? 'Game setup' : 'Reading passage'}
      </div>
      <h3 className="mt-1 text-lg font-semibold text-slate-100">
        {passage.title}
      </h3>
      {passage.summary && (
        <p className="mt-1 text-xs italic text-slate-500">{passage.summary}</p>
      )}
      {passage.passage && (
        <p className="mt-4 whitespace-pre-line text-sm leading-relaxed text-slate-200">
          {passage.passage}
        </p>
      )}
      {passage.setup && (
        <p className="mt-4 whitespace-pre-line text-sm leading-relaxed text-slate-200">
          {passage.setup}
        </p>
      )}
      {passage.rules.length > 0 && (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="text-[11px] uppercase tracking-wider text-slate-500">
            Rules
          </div>
          <ul className="mt-2 list-inside list-decimal space-y-1 text-sm text-slate-200">
            {passage.rules.map((r) => (
              <li key={r}>{r.replace(/^\d+\.\s*/, '')}</li>
            ))}
          </ul>
        </div>
      )}
    </article>
  )
}

// ---------------------------------------------------------------------------
// Question card — used by all sections
// ---------------------------------------------------------------------------

function QuestionCard({
  question,
  onResolved,
  onNext,
  compact,
  elapsedEnabled = true,
  onActivate,
}: {
  question: LsatQuestion
  onResolved: (r: LsatGradeResponse, elapsedSeconds: number) => void
  onNext?: () => void
  compact?: boolean
  elapsedEnabled?: boolean
  onActivate?: () => void
}) {
  const [selected, setSelected] = useState<LsatChoiceLabel | null>(null)
  const [result, setResult] = useState<LsatGradeResponse | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showTutor, setShowTutor] = useState(false)
  const elapsedRef = useRef(0)

  // One tab stop for the whole choice list, arrows move and select within it —
  // the same pattern `lsat-static/components/QuestionCard.tsx` has always had.
  // Under exam-style time pressure, tabbing through five choices to reach the
  // submit button is a real cost, and it was the platform's alone to pay.
  const choiceRoving = useRovingTabIndex({
    count: question.choices.length,
    activeIndex: selected
      ? question.choices.findIndex((c) => c.label === selected)
      : -1,
    orientation: 'vertical',
    onActivate: (i) => {
      if (result === null) setSelected(question.choices[i].label)
    },
  })

  // Reset when the question changes.
  useEffect(() => {
    setSelected(null)
    setResult(null)
    setShowTutor(false)
    setError(null)
    elapsedRef.current = 0
  }, [question.id])

  const submit = async () => {
    if (!selected || submitting) return
    const elapsed = elapsedRef.current
    setSubmitting(true)
    setError(null)
    try {
      const r = await gradeLsat(question.id, selected)
      setResult(r)
      onResolved(r, elapsed)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Grade failed')
    } finally {
      setSubmitting(false)
    }
  }

  // Keyboard drilling: A–E pick a choice, Enter submits. Scoped to the card
  // (events bubble from the focused choice buttons) so stacked RC/LG cards
  // never react to one another's keypresses. Disabled once graded, and we
  // ignore keys typed into the tutor's text input.
  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (result || submitting) return
    // Let modified shortcuts (Ctrl/⌘/Alt+key, e.g. Select All) reach the browser.
    if (e.ctrlKey || e.metaKey || e.altKey) return
    const tag = (e.target as HTMLElement).tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA') return
    const key = e.key.toUpperCase()
    if (['A', 'B', 'C', 'D', 'E'].includes(key)) {
      if (question.choices.some((c) => c.label === key)) {
        setSelected(key as LsatChoiceLabel)
        e.preventDefault()
      }
    } else if (e.key === 'Enter' && selected) {
      e.preventDefault()
      void submit()
    }
  }

  return (
    <div
      onKeyDown={handleKeyDown}
      onFocusCapture={onActivate}
      onPointerDown={onActivate}
      className={
        'rounded-2xl border border-slate-800 bg-slate-900/40 backdrop-blur ' +
        (compact ? 'p-4' : 'p-6')
      }
    >
      {/* Persistent live region so screen readers announce the grade result. */}
      <p className="sr-only" role="status" aria-live="polite">
        {result
          ? result.correct
            ? 'Correct.'
            : `Incorrect. The correct answer was ${result.correct_choice}.`
          : ''}
      </p>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wider text-slate-500">
        <span className="font-mono text-slate-400">{question.id}</span>
        <span className="text-slate-700">·</span>
        <span>{question.section}</span>
        <span className="text-slate-700">·</span>
        <DiffBadge difficulty={question.difficulty} />
        {question.concepts && question.concepts.length > 0 && (
          <>
            <span className="text-slate-700">·</span>
            <span className="normal-case text-slate-400">
              {question.concepts.slice(0, 3).join(' · ')}
            </span>
          </>
        )}
        <QuestionElapsed
          key={question.id}
          frozen={result !== null || submitting || !elapsedEnabled}
          onTick={(s) => {
            elapsedRef.current = s
          }}
        />
      </div>

      <p className="whitespace-pre-line text-base leading-relaxed text-slate-100">
        {question.stem}
      </p>

      <ul
        className="mt-5 space-y-2"
        role="radiogroup"
        aria-label="Answer choices"
      >
        {question.choices.map((c, i) => {
          const isSelected = selected === c.label
          const showResult = result !== null
          const isCorrect = showResult && c.label === result.correct_choice
          const isWrongPick =
            showResult && isSelected && c.label !== result.correct_choice
          let cls =
            'group flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left text-sm transition '
          if (showResult) {
            if (isCorrect)
              cls += 'border-emerald-500/50 bg-emerald-500/10 text-emerald-100'
            else if (isWrongPick)
              cls += 'border-red-500/50 bg-red-500/10 text-red-100'
            else cls += 'border-slate-800 bg-slate-950/40 text-slate-400'
          } else if (isSelected) {
            cls += 'border-blue-500/60 bg-blue-500/10 text-blue-100'
          } else {
            cls +=
              'border-slate-800 bg-slate-950/40 text-slate-200 hover:border-slate-600 hover:bg-slate-900/60'
          }
          return (
            <li key={c.label}>
              <button
                type="button"
                {...choiceRoving.itemProps(i)}
                role="radio"
                aria-checked={isSelected}
                disabled={showResult}
                onClick={() => setSelected(c.label)}
                className={cls}
              >
                {/* The letter stays in the accessible name on purpose. The
                  * static site hides it, but in a drill the letter *is* the
                  * answer's identity — it is what a student records and what
                  * the tutor refers back to. "Alpha" alone loses that. */}
                <span
                  className={
                    'mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ' +
                    (isSelected || isCorrect
                      ? 'border-current'
                      : 'border-slate-700 text-slate-400 group-hover:border-slate-500')
                  }
                >
                  {c.label}
                </span>
                <span>{c.text}</span>
              </button>
            </li>
          )
        })}
      </ul>

      {!result && (
        <p className="mt-2 text-[11px] text-slate-500">
          Keyboard:{' '}
          <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
            A
          </kbd>
          –
          <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
            E
          </kbd>{' '}
          to choose ·{' '}
          <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
            Enter
          </kbd>{' '}
          to submit
        </p>
      )}

      {error && (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {error}
        </p>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-3">
        {!result && (
          <button
            onClick={() => void submit()}
            disabled={!selected || submitting}
            className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-500/20 transition hover:shadow-blue-500/40 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
          >
            {submitting ? 'Grading…' : 'Submit'}
          </button>
        )}
        {result && (
          <>
            <span
              className={
                'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ' +
                (result.correct
                  ? 'bg-emerald-500/15 text-emerald-300 ring-1 ring-inset ring-emerald-500/30'
                  : 'bg-red-500/15 text-red-300 ring-1 ring-inset ring-red-500/30')
              }
            >
              {result.correct
                ? 'Correct'
                : `Incorrect — answer was ${result.correct_choice}`}
            </span>
            <button
              onClick={() => setShowTutor((v) => !v)}
              className="inline-flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-200 transition hover:bg-amber-500/20"
            >
              {showTutor ? 'Hide AI Tutor' : 'Ask AI Tutor'}
            </button>
            {onNext && (
              <button
                onClick={onNext}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
              >
                Next →
              </button>
            )}
          </>
        )}
      </div>

      {result && (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/60 p-4">
          <div className="text-[11px] uppercase tracking-wider text-slate-500">
            Author rationale
          </div>
          <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-slate-300">
            {result.explanation}
          </p>
          {question.references && question.references.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {question.references.map((r) =>
                r.url ? (
                  <a
                    key={r.url + r.title}
                    href={r.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-slate-400 underline hover:text-slate-200"
                  >
                    ↗ {r.title}
                  </a>
                ) : (
                  <span
                    key={r.title}
                    className="text-xs italic text-slate-500"
                  >
                    {r.note ?? r.title}
                  </span>
                ),
              )}
            </div>
          )}
        </div>
      )}

      {showTutor && result && (
        <TutorPane
          questionId={question.id}
          userChoice={selected}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// AI Tutor pane
// ---------------------------------------------------------------------------

function TutorPane({
  questionId,
  userChoice,
}: {
  questionId: string
  userChoice: LsatChoiceLabel | null
}) {
  const [followUp, setFollowUp] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<LsatTutorResponse | null>(null)

  const ask = useCallback(
    async (overrideQuestion?: string) => {
      setLoading(true)
      setError(null)
      try {
        const r = await askLsatTutor({
          question_id: questionId,
          user_choice: userChoice,
          user_question: overrideQuestion ?? followUp ?? null,
        })
        setResponse(r)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Tutor failed')
      } finally {
        setLoading(false)
      }
    },
    [questionId, userChoice, followUp],
  )

  // Auto-fire the first call when the pane opens with no follow-up so the
  // learner sees coaching immediately.
  useEffect(() => {
    if (!response && !loading) void ask('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/[0.03] p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[11px] uppercase tracking-wider text-amber-300">
          AI Tutor
        </div>
        {response && (
          <div className="text-[10px] uppercase tracking-wider text-slate-500">
            {response.used_llm ? response.model : 'offline fallback'} ·{' '}
            {Math.round(response.confidence * 100)}% conf · {Math.round(response.latency_ms)}ms
          </div>
        )}
      </div>

      {loading && (
        <div className="mt-3 animate-pulse space-y-2">
          <div className="h-3 w-3/4 rounded bg-slate-800" />
          <div className="h-3 w-2/3 rounded bg-slate-800" />
          <div className="h-3 w-1/2 rounded bg-slate-800" />
        </div>
      )}

      {error && !loading && (
        <p className="mt-2 text-sm text-red-300" role="alert">
          {error}
          <button
            onClick={() => void ask()}
            className="ml-2 underline hover:text-red-200"
          >
            Retry
          </button>
        </p>
      )}

      {response && !loading && (
        <>
          <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-slate-200">
            {response.coaching}
          </p>
          {response.next_steps.length > 0 && (
            <div className="mt-3">
              <div className="text-[11px] uppercase tracking-wider text-slate-500">
                Next steps
              </div>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-300">
                {response.next_steps.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          )}
          {response.concepts.length > 0 && (
            <div className="mt-3">
              <div className="text-[11px] uppercase tracking-wider text-slate-500">
                Concepts in play
              </div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {response.concepts.map((c) => (
                  <span
                    key={c.id}
                    title={c.summary}
                    className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] text-slate-200"
                  >
                    {c.name}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <input
          type="text"
          aria-label="Ask the tutor a follow-up question"
          value={followUp}
          onChange={(e) => setFollowUp(e.target.value)}
          placeholder="Ask a follow-up — e.g. 'Why is C wrong?'"
          className="min-w-[260px] flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600 focus:border-amber-500 focus-ring-practice"
        />
        <button
          onClick={() => void ask()}
          disabled={loading}
          className="rounded-md bg-amber-500/80 px-3 py-1.5 text-xs font-semibold text-slate-950 transition hover:bg-amber-400 disabled:opacity-40"
        >
          {loading ? 'Thinking…' : 'Ask'}
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Concepts panel
// ---------------------------------------------------------------------------

function ConceptsPanel() {
  const [section, setSection] = useState<LsatSection | 'any'>('any')
  const [concepts, setConcepts] = useState<LsatConcept[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)

  useEffect(() => {
    void (async () => {
      setConcepts(null)
      setError(null)
      try {
        const body = await fetchLsatConcepts(
          section === 'any' ? undefined : section,
        )
        setConcepts(body.concepts)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load')
      }
    })()
  }, [section])

  const grouped = useMemo(() => {
    if (!concepts) return []
    const map = new Map<string, LsatConcept[]>()
    for (const c of concepts) {
      const key = c.sections[0] ?? 'misc'
      map.set(key, [...(map.get(key) ?? []), c])
    }
    return Array.from(map.entries())
  }, [concepts])

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3 backdrop-blur">
        <div>
          <div className="text-xs uppercase tracking-wider text-amber-400">
            Concept catalog
          </div>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">
            The reasoning patterns the LSAT recycles. Each concept ships a
            short summary, worked examples, and links to deeper material.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label
            htmlFor="concepts-section"
            className="text-xs uppercase tracking-wider text-slate-500"
          >
            Filter
          </label>
          <select
            id="concepts-section"
            value={section}
            onChange={(e) =>
              setSection(e.target.value as LsatSection | 'any')
            }
            className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200 focus:border-blue-500 focus-ring"
          >
            <option value="any">All sections</option>
            <option value="LR">Logical Reasoning</option>
            <option value="RC">Reading Comprehension</option>
            <option value="LG">Logic Games</option>
          </select>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}
      {!concepts && !error && <SkeletonGrid />}
      {concepts && grouped.length === 0 && (
        <p className="text-sm text-slate-400">No concepts match this filter.</p>
      )}
      {concepts &&
        grouped.map(([sec, items]) => (
          <div key={sec} className="space-y-2">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
              {sec}
            </h3>
            <div className="grid gap-3 md:grid-cols-2">
              {items.map((c) => {
                const open = openId === c.id
                return (
                  <article
                    key={c.id}
                    className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 backdrop-blur transition hover:border-slate-600"
                  >
                    <button
                      onClick={() => setOpenId(open ? null : c.id)}
                      className="flex w-full items-start justify-between gap-2 text-left"
                    >
                      <div>
                        <h4 className="text-sm font-semibold text-slate-100">
                          {c.name}
                        </h4>
                        <p className="mt-1 text-xs text-slate-400">
                          {c.summary}
                        </p>
                      </div>
                      <span className="text-slate-500">{open ? '−' : '+'}</span>
                    </button>
                    {open && (
                      <div className="mt-3 space-y-2 border-t border-slate-800 pt-3 text-sm">
                        {c.detail && (
                          <p className="leading-relaxed text-slate-300">
                            {c.detail}
                          </p>
                        )}
                        {c.examples.length > 0 && (
                          <div>
                            <div className="text-[11px] uppercase tracking-wider text-slate-500">
                              Example
                            </div>
                            <p className="mt-1 italic text-slate-300">
                              {c.examples[0]}
                            </p>
                          </div>
                        )}
                        {c.see_also.length > 0 && (
                          <div className="text-xs text-slate-400">
                            See also: {c.see_also.join(', ')}
                          </div>
                        )}
                        {c.references.length > 0 && (
                          <div className="flex flex-wrap gap-2 pt-1">
                            {c.references.map((r) =>
                              r.url ? (
                                <a
                                  key={r.url}
                                  href={r.url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-xs text-slate-400 underline hover:text-slate-200"
                                >
                                  ↗ {r.title}
                                </a>
                              ) : null,
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </article>
                )
              })}
            </div>
          </div>
        ))}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Stats panel
// ---------------------------------------------------------------------------

function StatsPanel({
  session,
  stats,
}: {
  session: SessionScore
  stats: LsatStats | null
}) {
  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <StatCard
          title="This session"
          attempts={session.attempts}
          correct={session.correct}
        />
        <StatCard
          title="All-time (audit log)"
          attempts={stats?.attempts ?? 0}
          correct={stats?.correct ?? 0}
        />
      </div>
      {stats?.by_section && Object.keys(stats.by_section).length > 0 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
            By section
          </h3>
          <table className="mt-3 w-full text-sm">
            <thead className="text-left text-[11px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="pb-2">Section</th>
                <th className="pb-2 text-right">Attempts</th>
                <th className="pb-2 text-right">Correct</th>
                <th className="pb-2 text-right">Accuracy</th>
              </tr>
            </thead>
            <tbody className="text-slate-200">
              {Object.entries(stats.by_section).map(([sec, b]) => (
                <tr key={sec} className="border-t border-slate-800">
                  <td className="py-2 font-mono text-slate-300">{sec}</td>
                  <td className="py-2 text-right tabular-nums">{b.attempts}</td>
                  <td className="py-2 text-right tabular-nums">{b.correct}</td>
                  <td className="py-2 text-right tabular-nums">
                    {Math.round(b.accuracy * 100)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function StatCard({
  title,
  attempts,
  correct,
}: {
  title: string
  attempts: number
  correct: number
}) {
  const pct = attempts > 0 ? Math.round((correct / attempts) * 100) : 0
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur">
      <div className="text-[11px] uppercase tracking-wider text-slate-500">
        {title}
      </div>
      <div className="mt-2 text-3xl font-semibold tabular-nums text-slate-100">
        {correct}
        <span className="text-slate-500"> / {attempts}</span>
      </div>
      <div className="mt-1 text-sm text-slate-400">{pct}% accuracy</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shared bits
// ---------------------------------------------------------------------------

function Toolbar({
  difficulty,
  onDifficulty,
  rightLabel,
}: {
  difficulty: LsatDifficulty | 'any'
  onDifficulty: (d: LsatDifficulty | 'any') => void
  rightLabel: string
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3 backdrop-blur">
      <div className="flex items-center gap-2">
        <label
          htmlFor="lsat-diff"
          className="text-xs uppercase tracking-wider text-slate-500"
        >
          Difficulty
        </label>
        <select
          id="lsat-diff"
          value={difficulty}
          onChange={(e) =>
            onDifficulty(e.target.value as LsatDifficulty | 'any')
          }
          className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200 focus:border-blue-500 focus-ring"
        >
          {DIFFICULTIES.map((d) => (
            <option key={d.value} value={d.value}>
              {d.label}
            </option>
          ))}
        </select>
      </div>
      <div className="text-xs uppercase tracking-wider text-slate-500">
        {rightLabel}
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  sub,
}: {
  label: string
  value: string
  sub?: string
}) {
  return (
    <div className="text-right">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">
        {label}
      </div>
      <div className="font-mono text-sm tabular-nums text-slate-100">
        {value}
        {sub && <span className="ml-1.5 text-xs text-slate-500">({sub})</span>}
      </div>
    </div>
  )
}

function DiffBadge({ difficulty }: { difficulty: LsatDifficulty }) {
  const styles: Record<LsatDifficulty, string> = {
    easy: 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30',
    med: 'bg-amber-500/15 text-amber-300 ring-amber-500/30',
    hard: 'bg-red-500/15 text-red-300 ring-red-500/30',
  }
  const label =
    difficulty === 'med'
      ? 'Medium'
      : difficulty[0].toUpperCase() + difficulty.slice(1)
  return (
    <span
      className={
        'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset ' +
        styles[difficulty]
      }
    >
      {label}
    </span>
  )
}

function SkeletonQuestion() {
  return (
    <div className="animate-pulse space-y-4 rounded-2xl border border-slate-800 bg-slate-900/40 p-6">
      <div className="h-3 w-32 rounded bg-slate-800" />
      <div className="h-5 w-full rounded bg-slate-800" />
      <div className="h-5 w-5/6 rounded bg-slate-800" />
      <div className="h-5 w-2/3 rounded bg-slate-800" />
      <div className="space-y-2 pt-3">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="h-12 w-full rounded-lg bg-slate-800/60" />
        ))}
      </div>
    </div>
  )
}

function SkeletonGrid() {
  return (
    <div className="grid animate-pulse gap-3 md:grid-cols-2">
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          className="h-40 rounded-2xl border border-slate-800 bg-slate-900/40"
        />
      ))}
    </div>
  )
}

function ErrorBanner({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300"
    >
      {message}
      {onRetry && (
        <button
          onClick={onRetry}
          className="ml-3 underline hover:text-red-200"
        >
          Retry
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Authoring panel — HITL queue for AI-drafted questions (spec 019 FR-12)
// ---------------------------------------------------------------------------

function AuthoringPanel() {
  const [pending, setPending] = useState<LsatProposal[]>([])
  const [gaps, setGaps] = useState<LsatGapRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const [section, setSection] = useState<LsatSection>('LR')
  const [difficulty, setDifficulty] = useState<LsatDifficulty>('med')
  const [count, setCount] = useState(1)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [p, g] = await Promise.all([
        fetchLsatProposals('pending', 50),
        fetchLsatGaps(10),
      ])
      setPending(p.proposals)
      setGaps(g.gaps)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load proposals')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const onGenerate = useCallback(async () => {
    setGenerating(true)
    setError(null)
    try {
      await generateLsatProposals({ section, difficulty, count })
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }, [section, difficulty, count, refresh])

  const onApprove = useCallback(
    async (id: string) => {
      setBusy(id)
      try {
        await approveLsatProposal(id)
        setPending((rows) => rows.filter((r) => r.id !== id))
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Approve failed')
      } finally {
        setBusy(null)
      }
    },
    [],
  )

  const onReject = useCallback(async (id: string) => {
    setBusy(id)
    try {
      await rejectLsatProposal(id)
      setPending((rows) => rows.filter((r) => r.id !== id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Reject failed')
    } finally {
      setBusy(null)
    }
  }, [])

  return (
    <section className="space-y-6">
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur">
        <div className="text-xs uppercase tracking-wider text-amber-400">
          Human-in-the-loop
        </div>
        <h2 className="mt-1 text-2xl font-semibold text-slate-100">
          Authoring queue
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-400">
          The <code className="text-slate-300">LSATContentAuthor</code> agent
          drafts new questions targeting the concepts where learners score
          lowest. Every draft lands here for human review before it joins the
          live question bank.
        </p>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          Generate new draft
        </h3>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-xs text-slate-400">
            Section
            <select
              value={section}
              onChange={(e) => setSection(e.target.value as LsatSection)}
              className="mt-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
            >
              <option value="LR">Logical Reasoning</option>
              <option value="RC">Reading Comprehension</option>
              <option value="LG">Logic Games</option>
            </select>
          </label>
          <label className="flex flex-col text-xs text-slate-400">
            Difficulty
            <select
              value={difficulty}
              onChange={(e) =>
                setDifficulty(e.target.value as LsatDifficulty)
              }
              className="mt-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
            >
              <option value="easy">Easy</option>
              <option value="med">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </label>
          <label className="flex flex-col text-xs text-slate-400">
            Count
            <input
              type="number"
              min={1}
              max={10}
              value={count}
              onChange={(e) =>
                setCount(Math.max(1, Math.min(10, Number(e.target.value) || 1)))
              }
              className="mt-1 w-24 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
            />
          </label>
          <button
            onClick={() => void onGenerate()}
            disabled={generating}
            className="rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-md shadow-blue-500/20 transition disabled:cursor-not-allowed disabled:opacity-50"
          >
            {generating ? 'Drafting…' : 'Draft questions'}
          </button>
        </div>
      </div>

      {gaps.length > 0 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            Weakest measured concepts
          </h3>
          <p className="mt-1 text-xs text-slate-500">
            Tomorrow&apos;s autonomy cycle will target the top row.
          </p>
          <table className="mt-3 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="py-2 pr-4">Section</th>
                <th className="py-2 pr-4">Concept</th>
                <th className="py-2 pr-4">Attempts</th>
                <th className="py-2 pr-4">Accuracy</th>
              </tr>
            </thead>
            <tbody>
              {gaps.map((g, i) => (
                <tr
                  key={`${g.section}-${g.concept}-${i}`}
                  className="border-t border-slate-800/70 text-slate-300"
                >
                  <td className="py-2 pr-4 font-mono text-xs">{g.section}</td>
                  <td className="py-2 pr-4">{g.concept}</td>
                  <td className="py-2 pr-4">{g.attempts}</td>
                  <td className="py-2 pr-4">
                    {Math.round(g.accuracy * 100)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {error && <ErrorBanner message={error} onRetry={refresh} />}

      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            Pending review ({pending.length})
          </h3>
          <button
            onClick={() => void refresh()}
            className="text-xs text-blue-400 hover:text-blue-300"
          >
            Refresh
          </button>
        </div>
        {loading ? (
          <div className="mt-4 text-sm text-slate-500">Loading…</div>
        ) : pending.length === 0 ? (
          <div className="mt-4 text-sm text-slate-500">
            No drafts waiting for review.
          </div>
        ) : (
          <div className="mt-4 space-y-4">
            {pending.map((p) => (
              <ProposalCard
                key={p.id}
                proposal={p}
                busy={busy === p.id}
                onApprove={() => void onApprove(p.id)}
                onReject={() => void onReject(p.id)}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

function ProposalCard({
  proposal,
  busy,
  onApprove,
  onReject,
}: {
  proposal: LsatProposal
  busy: boolean
  onApprove: () => void
  onReject: () => void
}) {
  const d = proposal.draft
  return (
    <article className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
      <header className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-md bg-slate-800 px-2 py-0.5 font-mono text-slate-300">
          {d.section}
        </span>
        <span className="rounded-md bg-slate-800 px-2 py-0.5 text-slate-300">
          {d.difficulty}
        </span>
        <span className="text-slate-500">
          confidence {(proposal.confidence * 100).toFixed(0)}%
        </span>
        <span className="text-slate-600">·</span>
        <span className="text-slate-500">{proposal.model}</span>
        <span className="ml-auto font-mono text-slate-600">{proposal.id}</span>
      </header>
      <div className="mt-3 whitespace-pre-wrap text-sm text-slate-200">
        {d.stem}
      </div>
      <ol className="mt-3 space-y-1 text-sm">
        {d.choices.map((c) => (
          <li
            key={c.label}
            className={
              c.label === d.correct
                ? 'text-emerald-400'
                : 'text-slate-400'
            }
          >
            <span className="font-mono">{c.label}.</span> {c.text}
            {c.label === d.correct && (
              <span className="ml-2 text-xs uppercase tracking-wider">
                correct
              </span>
            )}
          </li>
        ))}
      </ol>
      <details className="mt-3 text-sm text-slate-400">
        <summary className="cursor-pointer text-slate-300">Explanation</summary>
        <p className="mt-2 whitespace-pre-wrap">{d.explanation}</p>
      </details>
      <footer className="mt-4 flex items-center justify-end gap-2">
        <button
          onClick={onReject}
          disabled={busy}
          className="rounded-md border border-red-700/60 px-3 py-1.5 text-xs font-semibold text-red-300 hover:bg-red-900/40 disabled:opacity-50"
        >
          Reject
        </button>
        <button
          onClick={onApprove}
          disabled={busy}
          className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {busy ? 'Working…' : 'Approve & promote'}
        </button>
      </footer>
    </article>
  )
}
