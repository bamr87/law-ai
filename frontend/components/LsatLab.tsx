'use client'

/**
 * LSAT Lab — multi-section practice + concept catalog + AI tutor.
 *
 * Top-level tab router rendered through the shared EDGAR `Page` shell. Each
 * section gets its own subview specialised for the question format (LR
 * isolated stems, RC passages, LG game setup + rules). Data flows through the
 * React Query LSAT hooks in `lib/queries`; Concepts and Overview are static
 * documentation surfaces. The session/all-time scoreboard hangs off the page
 * header so it follows the learner across tabs.
 */

import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Page,
  Panel,
  Select,
  SkeletonLines,
  StatGrid,
  Table,
  Tabs,
  type Column,
  type StatItem,
  type TabItem,
} from '@/components/ui'
import { useHydrated } from '@/lib/useHydrated'
import {
  useAskTutor,
  useGenerateProposals,
  useGradeLsat,
  useLsatConcepts,
  useLsatGaps,
  useLsatPassage,
  useLsatPassages,
  useLsatProposals,
  useLsatQuestions,
  useLsatSections,
  useLsatStats,
  useReviewProposal,
} from '@/lib/queries'
import type {
  LsatChoiceLabel,
  LsatConcept,
  LsatDifficulty,
  LsatGapRow,
  LsatGradeResponse,
  LsatPassage,
  LsatProposal,
  LsatQuestion,
  LsatSection,
  LsatSectionInfo,
  LsatStats,
} from '@/lib/api'
import {
  BookOpen,
  BrainCircuit,
  FileText,
  Library,
  type LucideIcon,
  PencilRuler,
  Puzzle,
  Sparkles,
  TrendingUp,
} from 'lucide-react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useMemo, useState } from 'react'

type Tab = 'overview' | 'LR' | 'RC' | 'LG' | 'concepts' | 'stats' | 'authoring'

const TAB_ICONS: Record<Tab, LucideIcon> = {
  overview: BookOpen,
  LR: BrainCircuit,
  RC: FileText,
  LG: Puzzle,
  concepts: Library,
  stats: TrendingUp,
  authoring: PencilRuler,
}

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

const DIFF_TONE: Record<LsatDifficulty, 'success' | 'warning' | 'danger'> = {
  easy: 'success',
  med: 'warning',
  hard: 'danger',
}

interface SessionScore {
  attempts: number
  correct: number
}

export default function LsatLab() {
  const hydrated = useHydrated()

  // The active section is deep-linkable (?tab=LR) so a learner can share or
  // bookmark a direct link into any drill, and a reload lands back on it. We
  // seed local state from the URL on mount and mirror changes back so the
  // back button and shared links work without re-deriving every render.
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const urlTab = searchParams.get('tab')
  const [tab, setTabState] = useState<Tab>(
    TABS.some((t) => t.id === urlTab) ? (urlTab as Tab) : 'overview',
  )
  const setTab = useCallback(
    (next: Tab) => {
      setTabState(next)
      const params = new URLSearchParams(searchParams.toString())
      if (next === 'overview') params.delete('tab')
      else params.set('tab', next)
      const qs = params.toString()
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false })
    },
    [router, pathname, searchParams],
  )

  const [session, setSession] = useState<SessionScore>({ attempts: 0, correct: 0 })

  // All-time scoreboard. The grade mutation invalidates ['lsat','stats'] on
  // success, so this refreshes itself after every attempt — no manual refetch.
  const statsQ = useLsatStats()
  const globalStats = statsQ.data ?? null

  const onAttempt = useCallback((correct: boolean) => {
    setSession((s) => ({
      attempts: s.attempts + 1,
      correct: s.correct + (correct ? 1 : 0),
    }))
  }, [])

  const sessionAccuracy =
    session.attempts > 0
      ? Math.round((session.correct / session.attempts) * 100)
      : null

  const stats: StatItem[] = [
    {
      label: 'Session',
      value: `${session.correct}/${session.attempts}`,
      hint: sessionAccuracy != null ? `${sessionAccuracy}% accuracy` : 'no attempts yet',
    },
    {
      label: 'All-time',
      value: globalStats ? `${globalStats.correct}/${globalStats.attempts}` : '—',
      hint:
        globalStats && globalStats.attempts > 0
          ? `${Math.round(globalStats.accuracy * 100)}% accuracy`
          : 'audit log',
    },
  ]

  const tabItems: TabItem[] = TABS.map((t) => {
    const Icon = TAB_ICONS[t.id]
    return { id: t.id, label: t.label, icon: <Icon className="h-3.5 w-3.5" aria-hidden /> }
  })

  return (
    <Page
      eyebrow="Practice & study"
      title="LSAT Lab"
      tagline={
        <>
          A full LSAT workbench: drill Logical Reasoning, Reading Comprehension,
          and Logic Games against an open-source bank, browse the catalog of
          recurring reasoning patterns, and ask the local Ollama-powered tutor to
          walk you through any item. Every attempt and tutor call is auditable via{' '}
          <code className="text-ink">/api/lsat/*</code>.
        </>
      }
    >
      {!hydrated ? (
        <SkeletonLines rows={6} />
      ) : (
        <>
          <StatGrid items={stats} min={170} />

          <Tabs
            items={tabItems}
            active={tab}
            onChange={(id) => setTab(id as Tab)}
            aria-label="LSAT Lab sections"
          />

          <div>
            {tab === 'overview' && <OverviewPanel onJump={setTab} />}
            {tab === 'LR' && <LrPanel onAttempt={onAttempt} />}
            {tab === 'RC' && <PassagePanel key="RC" section="RC" onAttempt={onAttempt} />}
            {tab === 'LG' && <PassagePanel key="LG" section="LG" onAttempt={onAttempt} />}
            {tab === 'concepts' && <ConceptsPanel />}
            {tab === 'stats' && <StatsPanel session={session} stats={globalStats} />}
            {tab === 'authoring' && <AuthoringPanel />}
          </div>
        </>
      )}
    </Page>
  )
}

// ---------------------------------------------------------------------------
// Overview panel — section docs
// ---------------------------------------------------------------------------

function OverviewPanel({ onJump }: { onJump: (t: Tab) => void }) {
  const sectionsQ = useLsatSections()
  const sections = sectionsQ.data?.sections ?? null

  return (
    <section className="flex flex-col gap-5">
      <Card className="p-6">
        <div className="text-xs font-semibold uppercase tracking-wide text-brand">
          About the LSAT
        </div>
        <h2 className="mt-1.5 text-xl font-semibold text-ink">
          The four-section roadmap
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          The Law School Admission Test measures the reasoning and reading skills
          that drive law-school success: identifying conclusions, spotting flawed
          arguments, mapping passage structure, and translating dense prose into
          compact constraints. Pick a section below to drill questions, or open
          the Concepts tab for a catalog of every reasoning pattern the test
          recycles.
        </p>
      </Card>

      {sectionsQ.isError && (
        <ErrorState
          message={(sectionsQ.error as Error)?.message ?? 'Failed to load sections'}
          onRetry={() => void sectionsQ.refetch()}
        />
      )}

      {!sections && !sectionsQ.isError && <SkeletonGrid />}

      {sections && (
        <div className="grid gap-4 md:grid-cols-2">
          {sections.map((s) => (
            <SectionCard key={s.code} section={s} onJump={onJump} />
          ))}
        </div>
      )}
    </section>
  )
}

function SectionCard({
  section: s,
  onJump,
}: {
  section: LsatSectionInfo
  onJump: (t: Tab) => void
}) {
  return (
    <Card interactive className="p-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-base font-semibold text-ink">{s.name}</h3>
        <Badge tone="neutral" uppercase className="font-mono">
          {s.code}
        </Badge>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-muted">{s.description}</p>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
        <Detail label="Format" value={s.format} />
        <Detail label="Timing" value={s.timing} />
        <Detail label="Scoring" value={s.scoring} />
        <Detail label="Items in bank" value={`${s.question_count}`} />
      </dl>
      {s.tips.length > 0 && (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted">
          {s.tips.slice(0, 3).map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button size="sm" onClick={() => onJump(s.code as Tab)}>
          Practice {s.code} →
        </Button>
        {s.references.slice(0, 2).map((r) =>
          r.url ? (
            <a
              key={r.url}
              href={r.url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-muted underline underline-offset-2 hover:text-ink"
            >
              {r.title}
            </a>
          ) : null,
        )}
      </div>
    </Card>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="uppercase tracking-wide text-subtle">{label}</dt>
      <dd className="mt-0.5 text-muted">{value}</dd>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Logical Reasoning panel — single isolated question at a time
// ---------------------------------------------------------------------------

function LrPanel({ onAttempt }: { onAttempt: (correct: boolean) => void }) {
  const [difficulty, setDifficulty] = useState<LsatDifficulty | 'any'>('any')
  const questionsQ = useLsatQuestions({
    limit: 1,
    section: 'LR',
    difficulty: difficulty === 'any' ? undefined : difficulty,
  })
  const question = questionsQ.data?.questions[0] ?? null

  return (
    <section className="flex flex-col gap-4">
      <Toolbar
        difficulty={difficulty}
        onDifficulty={setDifficulty}
        rightLabel="Section: Logical Reasoning"
      />
      {questionsQ.isLoading && <SkeletonQuestion />}
      {questionsQ.isError && (
        <ErrorState
          message={(questionsQ.error as Error)?.message ?? 'Failed to load'}
          onRetry={() => void questionsQ.refetch()}
        />
      )}
      {!questionsQ.isLoading && !questionsQ.isError && question && (
        <QuestionCard
          key={question.id}
          question={question}
          onResolved={(r) => onAttempt(r.correct)}
          onNext={() => void questionsQ.refetch()}
        />
      )}
      {!questionsQ.isLoading && !questionsQ.isError && !question && (
        <EmptyState message="No Logical Reasoning questions match this filter." />
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
  onAttempt: (correct: boolean) => void
}) {
  const [activeId, setActiveId] = useState<string | null>(null)
  const passagesQ = useLsatPassages(section)
  const passages = useMemo(
    () => passagesQ.data?.passages ?? [],
    [passagesQ.data],
  )
  // Derive the active passage so we never set state in an effect: fall back to
  // the first passage until the learner explicitly picks one.
  const effectiveId = activeId ?? passages[0]?.id ?? null
  const detailQ = useLsatPassage(effectiveId)
  const activePassage = detailQ.data?.passage ?? null
  const questions = detailQ.data?.questions ?? []

  const headline = section === 'RC' ? 'Reading Comprehension' : 'Logic Games'
  const error = passagesQ.error ?? detailQ.error

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface/60 px-4 py-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-subtle">
          Section: {headline}
        </div>
        {passages.length > 0 && (
          <div className="flex items-center gap-2">
            <label
              htmlFor="passage-select"
              className="text-xs font-medium text-muted"
            >
              {section === 'LG' ? 'Game' : 'Passage'}
            </label>
            <div className="w-56">
              <Select
                id="passage-select"
                value={effectiveId ?? ''}
                onChange={(e) => setActiveId(e.target.value)}
                className="h-8 py-1"
              >
                {passages.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                  </option>
                ))}
              </Select>
            </div>
          </div>
        )}
      </div>

      {passagesQ.isLoading && <SkeletonGrid />}
      {error && (
        <ErrorState message={(error as Error)?.message ?? 'Failed to load'} />
      )}
      {!passagesQ.isLoading && passages.length === 0 && (
        <EmptyState
          message={`No ${headline.toLowerCase()} passages have been authored yet.`}
        />
      )}

      {activePassage && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <PassageReader passage={activePassage} />
          <div className="flex flex-col gap-4">
            {detailQ.isLoading && <SkeletonQuestion />}
            {!detailQ.isLoading &&
              questions.map((q) => (
                <QuestionCard
                  key={q.id}
                  question={q}
                  onResolved={(r) => onAttempt(r.correct)}
                  compact
                />
              ))}
            {!detailQ.isLoading && questions.length === 0 && (
              <EmptyState
                message={`No questions linked to this ${section === 'LG' ? 'game' : 'passage'}.`}
              />
            )}
          </div>
        </div>
      )}
    </section>
  )
}

function PassageReader({ passage }: { passage: LsatPassage }) {
  return (
    <Card className="sticky top-4 max-h-[80vh] overflow-y-auto p-5">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-brand">
        {passage.section === 'LG' ? 'Game setup' : 'Reading passage'}
      </div>
      <h3 className="mt-1 text-base font-semibold text-ink">{passage.title}</h3>
      {passage.summary && (
        <p className="mt-1 text-xs italic text-subtle">{passage.summary}</p>
      )}
      {passage.passage && (
        <p className="mt-4 whitespace-pre-line text-sm leading-relaxed text-ink">
          {passage.passage}
        </p>
      )}
      {passage.setup && (
        <p className="mt-4 whitespace-pre-line text-sm leading-relaxed text-ink">
          {passage.setup}
        </p>
      )}
      {passage.rules.length > 0 && (
        <div className="mt-4 rounded-lg border border-border bg-canvas-soft p-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-subtle">
            Rules
          </div>
          <ul className="mt-2 list-inside list-decimal space-y-1 text-sm text-ink">
            {passage.rules.map((r) => (
              <li key={r}>{r.replace(/^\d+\.\s*/, '')}</li>
            ))}
          </ul>
        </div>
      )}
    </Card>
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
}: {
  question: LsatQuestion
  onResolved: (r: LsatGradeResponse) => void
  onNext?: () => void
  compact?: boolean
}) {
  const [selected, setSelected] = useState<LsatChoiceLabel | null>(null)
  const [result, setResult] = useState<LsatGradeResponse | null>(null)
  const [showTutor, setShowTutor] = useState(false)
  const grade = useGradeLsat()

  const submit = () => {
    if (!selected || grade.isPending) return
    grade.mutate(
      { questionId: question.id, choice: selected },
      {
        onSuccess: (r) => {
          setResult(r)
          onResolved(r)
        },
      },
    )
  }

  return (
    <Card className={compact ? 'p-4' : 'p-6'}>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wide text-subtle">
        <span className="font-mono text-muted">{question.id}</span>
        <span className="text-border-strong">·</span>
        <span>{question.section}</span>
        <span className="text-border-strong">·</span>
        <Badge tone={DIFF_TONE[question.difficulty]} uppercase>
          {question.difficulty === 'med'
            ? 'Medium'
            : question.difficulty[0].toUpperCase() + question.difficulty.slice(1)}
        </Badge>
        {question.concepts && question.concepts.length > 0 && (
          <>
            <span className="text-border-strong">·</span>
            <span className="normal-case text-muted">
              {question.concepts.slice(0, 3).join(' · ')}
            </span>
          </>
        )}
      </div>

      <p className="whitespace-pre-line text-base leading-relaxed text-ink">
        {question.stem}
      </p>

      <ul className="mt-5 space-y-2" role="radiogroup">
        {question.choices.map((c) => {
          const isSelected = selected === c.label
          const showResult = result !== null
          const isCorrect = showResult && c.label === result.correct_choice
          const isWrongPick =
            showResult && isSelected && c.label !== result.correct_choice
          let cls =
            'group flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left text-sm transition '
          if (showResult) {
            if (isCorrect) cls += 'border-success/50 bg-success/10 text-ink'
            else if (isWrongPick) cls += 'border-danger/50 bg-danger/10 text-ink'
            else cls += 'border-border bg-canvas-soft text-muted'
          } else if (isSelected) {
            cls += 'border-brand/60 bg-brand/10 text-ink'
          } else {
            cls +=
              'border-border bg-canvas-soft text-ink hover:border-border-strong hover:bg-surface-2'
          }
          return (
            <li key={c.label}>
              <button
                type="button"
                role="radio"
                aria-checked={isSelected}
                disabled={showResult}
                onClick={() => setSelected(c.label)}
                className={cls}
              >
                <span
                  className={
                    'mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ' +
                    (isSelected || isCorrect
                      ? 'border-current'
                      : 'border-border-strong text-muted group-hover:border-brand/50')
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

      {grade.isError && (
        <p className="mt-3 text-sm text-danger" role="alert">
          {(grade.error as Error)?.message ?? 'Grade failed'}
        </p>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-3">
        {!result && (
          <Button onClick={submit} disabled={!selected} loading={grade.isPending}>
            {grade.isPending ? 'Grading…' : 'Submit'}
          </Button>
        )}
        {result && (
          <>
            <Badge tone={result.correct ? 'success' : 'danger'} dot>
              {result.correct
                ? 'Correct'
                : `Incorrect — answer was ${result.correct_choice}`}
            </Badge>
            <Button
              variant="secondary"
              size="sm"
              icon={<Sparkles className="h-3.5 w-3.5" aria-hidden />}
              onClick={() => setShowTutor((v) => !v)}
            >
              {showTutor ? 'Hide AI Tutor' : 'Ask AI Tutor'}
            </Button>
            {onNext && (
              <Button variant="ghost" size="sm" onClick={onNext}>
                Next →
              </Button>
            )}
          </>
        )}
      </div>

      {result && (
        <div className="mt-4 rounded-lg border border-border bg-canvas-soft p-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-subtle">
            Author rationale
          </div>
          <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-muted">
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
                    className="text-xs text-muted underline underline-offset-2 hover:text-ink"
                  >
                    ↗ {r.title}
                  </a>
                ) : (
                  <span key={r.title} className="text-xs italic text-subtle">
                    {r.note ?? r.title}
                  </span>
                ),
              )}
            </div>
          )}
        </div>
      )}

      {showTutor && result && (
        <TutorPane questionId={question.id} userChoice={selected} />
      )}
    </Card>
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
  const tutor = useAskTutor()
  const response = tutor.data ?? null

  const ask = useCallback(
    (overrideQuestion?: string) => {
      tutor.mutate({
        question_id: questionId,
        user_choice: userChoice,
        user_question: overrideQuestion ?? followUp ?? null,
      })
    },
    [questionId, userChoice, followUp, tutor],
  )

  // Auto-fire the first call when the pane opens so the learner sees coaching
  // immediately. Fires exactly once on mount (the pane only mounts when the
  // learner clicks "Ask AI Tutor").
  useEffect(() => {
    ask('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="mt-4 rounded-lg border border-brand/30 bg-brand-soft p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-brand">
          AI Tutor
        </div>
        {response && (
          <div className="text-[10px] uppercase tracking-wide text-subtle">
            {response.used_llm ? response.model : 'offline fallback'} ·{' '}
            {Math.round(response.confidence * 100)}% conf ·{' '}
            {Math.round(response.latency_ms)}ms
          </div>
        )}
      </div>

      {tutor.isPending && <SkeletonLines rows={3} className="mt-3" />}

      {tutor.isError && !tutor.isPending && (
        <p className="mt-2 text-sm text-danger" role="alert">
          {(tutor.error as Error)?.message ?? 'Tutor failed'}
          <button
            onClick={() => ask()}
            className="ml-2 underline underline-offset-2 hover:text-ink"
          >
            Retry
          </button>
        </p>
      )}

      {response && !tutor.isPending && (
        <>
          <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-ink">
            {response.coaching}
          </p>
          {response.next_steps.length > 0 && (
            <div className="mt-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-subtle">
                Next steps
              </div>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-muted">
                {response.next_steps.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          )}
          {response.concepts.length > 0 && (
            <div className="mt-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-subtle">
                Concepts in play
              </div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {response.concepts.map((c) => (
                  <Badge key={c.id} tone="neutral" title={c.summary}>
                    {c.name}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={followUp}
          onChange={(e) => setFollowUp(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              ask()
            }
          }}
          placeholder="Ask a follow-up — e.g. 'Why is C wrong?'"
          className="h-9 min-w-[260px] flex-1 rounded-lg border border-border bg-canvas-soft px-3 text-sm text-ink placeholder:text-subtle focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30"
        />
        <Button size="sm" onClick={() => ask()} loading={tutor.isPending}>
          {tutor.isPending ? 'Thinking…' : 'Ask'}
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Concepts panel
// ---------------------------------------------------------------------------

function ConceptsPanel() {
  const [section, setSection] = useState<LsatSection | 'any'>('any')
  const [openId, setOpenId] = useState<string | null>(null)
  const conceptsQ = useLsatConcepts(section === 'any' ? undefined : section)
  const concepts = conceptsQ.data?.concepts ?? null

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
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface/60 px-4 py-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-brand">
            Concept catalog
          </div>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            The reasoning patterns the LSAT recycles. Each concept ships a short
            summary, worked examples, and links to deeper material.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label
            htmlFor="concepts-section"
            className="text-xs font-medium text-muted"
          >
            Filter
          </label>
          <div className="w-44">
            <Select
              id="concepts-section"
              value={section}
              onChange={(e) => setSection(e.target.value as LsatSection | 'any')}
              className="h-8 py-1"
            >
              <option value="any">All sections</option>
              <option value="LR">Logical Reasoning</option>
              <option value="RC">Reading Comprehension</option>
              <option value="LG">Logic Games</option>
            </Select>
          </div>
        </div>
      </div>

      {conceptsQ.isError && (
        <ErrorState
          message={(conceptsQ.error as Error)?.message ?? 'Failed to load'}
          onRetry={() => void conceptsQ.refetch()}
        />
      )}
      {!concepts && !conceptsQ.isError && <SkeletonGrid />}
      {concepts && grouped.length === 0 && (
        <EmptyState message="No concepts match this filter." />
      )}
      {concepts &&
        grouped.map(([sec, items]) => (
          <div key={sec} className="flex flex-col gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-subtle">
              {sec}
            </h3>
            <div className="grid gap-3 md:grid-cols-2">
              {items.map((c) => {
                const open = openId === c.id
                return (
                  <Card key={c.id} interactive className="p-4">
                    <button
                      onClick={() => setOpenId(open ? null : c.id)}
                      className="flex w-full items-start justify-between gap-2 text-left"
                    >
                      <div>
                        <h4 className="text-sm font-semibold text-ink">{c.name}</h4>
                        <p className="mt-1 text-xs text-muted">{c.summary}</p>
                      </div>
                      <span className="text-subtle">{open ? '−' : '+'}</span>
                    </button>
                    {open && (
                      <div className="mt-3 flex flex-col gap-2 border-t border-border pt-3 text-sm">
                        {c.detail && (
                          <p className="leading-relaxed text-muted">{c.detail}</p>
                        )}
                        {c.examples.length > 0 && (
                          <div>
                            <div className="text-[11px] font-semibold uppercase tracking-wide text-subtle">
                              Example
                            </div>
                            <p className="mt-1 italic text-muted">{c.examples[0]}</p>
                          </div>
                        )}
                        {c.see_also.length > 0 && (
                          <div className="text-xs text-muted">
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
                                  className="text-xs text-muted underline underline-offset-2 hover:text-ink"
                                >
                                  ↗ {r.title}
                                </a>
                              ) : null,
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </Card>
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
  const bySection = stats?.by_section
    ? Object.entries(stats.by_section).map(([section, b]) => ({ section, ...b }))
    : []

  const columns: Column<{
    section: string
    attempts: number
    correct: number
    accuracy: number
  }>[] = [
    { key: 'section', header: 'Section', cell: (r) => <span className="font-mono">{r.section}</span> },
    { key: 'attempts', header: 'Attempts', align: 'right', cell: (r) => <span className="tabular-nums">{r.attempts}</span> },
    { key: 'correct', header: 'Correct', align: 'right', cell: (r) => <span className="tabular-nums">{r.correct}</span> },
    {
      key: 'accuracy',
      header: 'Accuracy',
      align: 'right',
      cell: (r) => <span className="tabular-nums">{Math.round(r.accuracy * 100)}%</span>,
    },
  ]

  return (
    <section className="flex flex-col gap-4">
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
      {bySection.length > 0 && (
        <Panel title="By section">
          <Table columns={columns} rows={bySection} rowKey={(r) => r.section} />
        </Panel>
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
    <Card className="p-5">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-subtle">
        {title}
      </div>
      <div className="mt-2 text-3xl font-semibold tabular-nums text-ink">
        {correct}
        <span className="text-subtle"> / {attempts}</span>
      </div>
      <div className="mt-1 text-sm text-muted">{pct}% accuracy</div>
    </Card>
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
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface/60 px-4 py-3">
      <div className="flex items-center gap-2">
        <label htmlFor="lsat-diff" className="text-xs font-medium text-muted">
          Difficulty
        </label>
        <div className="w-32">
          <Select
            id="lsat-diff"
            value={difficulty}
            onChange={(e) => onDifficulty(e.target.value as LsatDifficulty | 'any')}
            className="h-8 py-1"
          >
            {DIFFICULTIES.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </Select>
        </div>
      </div>
      <div className="text-xs font-semibold uppercase tracking-wide text-subtle">
        {rightLabel}
      </div>
    </div>
  )
}

function SkeletonQuestion() {
  return (
    <Card className="p-6">
      <SkeletonLines rows={4} />
      <div className="mt-3 space-y-2">
        {[0, 1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="h-12 w-full animate-pulse rounded-lg bg-surface-3/60"
            style={{ animationDelay: `${i * 80}ms` }}
          />
        ))}
      </div>
    </Card>
  )
}

function SkeletonGrid() {
  return (
    <div className="grid animate-pulse gap-3 md:grid-cols-2">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="h-40 rounded-xl border border-border bg-surface/60" />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Authoring panel — HITL queue for AI-drafted questions (spec 019 FR-12)
// ---------------------------------------------------------------------------

function AuthoringPanel() {
  const [section, setSection] = useState<LsatSection>('LR')
  const [difficulty, setDifficulty] = useState<LsatDifficulty>('med')
  const [count, setCount] = useState(1)
  const [busyId, setBusyId] = useState<string | null>(null)

  const proposalsQ = useLsatProposals('pending', 50)
  const gapsQ = useLsatGaps(10)
  const generate = useGenerateProposals()
  const review = useReviewProposal()

  const pending = proposalsQ.data?.proposals ?? []
  const gaps = gapsQ.data?.gaps ?? []

  const onGenerate = () => {
    generate.mutate({ section, difficulty, count })
  }

  const onReview = (id: string, action: 'approve' | 'reject') => {
    setBusyId(id)
    review.mutate({ id, action }, { onSettled: () => setBusyId(null) })
  }

  const error = generate.error ?? review.error ?? proposalsQ.error

  return (
    <section className="flex flex-col gap-5">
      <Card className="p-6">
        <div className="text-xs font-semibold uppercase tracking-wide text-brand">
          Human-in-the-loop
        </div>
        <h2 className="mt-1.5 text-xl font-semibold text-ink">Authoring queue</h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          The <code className="text-ink">LSATContentAuthor</code> agent drafts new
          questions targeting the concepts where learners score lowest. Every
          draft lands here for human review before it joins the live question
          bank.
        </p>
      </Card>

      <Panel title="Generate new draft">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-muted">
            Section
            <div className="w-48">
              <Select
                value={section}
                onChange={(e) => setSection(e.target.value as LsatSection)}
                className="h-9"
              >
                <option value="LR">Logical Reasoning</option>
                <option value="RC">Reading Comprehension</option>
                <option value="LG">Logic Games</option>
              </Select>
            </div>
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            Difficulty
            <div className="w-36">
              <Select
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value as LsatDifficulty)}
                className="h-9"
              >
                <option value="easy">Easy</option>
                <option value="med">Medium</option>
                <option value="hard">Hard</option>
              </Select>
            </div>
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            Count
            <input
              type="number"
              min={1}
              max={10}
              value={count}
              onChange={(e) =>
                setCount(Math.max(1, Math.min(10, Number(e.target.value) || 1)))
              }
              className="h-9 w-24 rounded-lg border border-border bg-canvas-soft px-3 text-sm text-ink focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/30"
            />
          </label>
          <Button onClick={onGenerate} loading={generate.isPending}>
            {generate.isPending ? 'Drafting…' : 'Draft questions'}
          </Button>
        </div>
      </Panel>

      {gaps.length > 0 && (
        <Panel
          title="Weakest measured concepts"
          subtitle="Tomorrow's autonomy cycle will target the top row."
        >
          <Table
            columns={gapColumns}
            rows={gaps}
            rowKey={(g, i) => `${g.section}-${g.concept}-${i}`}
          />
        </Panel>
      )}

      {error && (
        <ErrorState
          message={(error as Error)?.message ?? 'Authoring request failed'}
          onRetry={() => void proposalsQ.refetch()}
        />
      )}

      <Panel
        title={`Pending review (${pending.length})`}
        actions={
          <button
            onClick={() => void proposalsQ.refetch()}
            className="text-xs font-medium text-brand hover:underline"
          >
            Refresh
          </button>
        }
        loading={proposalsQ.isLoading}
      >
        {pending.length === 0 ? (
          <EmptyState message="No drafts waiting for review." />
        ) : (
          <div className="flex flex-col gap-4">
            {pending.map((p) => (
              <ProposalCard
                key={p.id}
                proposal={p}
                busy={busyId === p.id}
                onApprove={() => onReview(p.id, 'approve')}
                onReject={() => onReview(p.id, 'reject')}
              />
            ))}
          </div>
        )}
      </Panel>
    </section>
  )
}

const gapColumns: Column<LsatGapRow>[] = [
  { key: 'section', header: 'Section', cell: (g) => <span className="font-mono">{g.section}</span> },
  { key: 'concept', header: 'Concept', cell: (g) => g.concept },
  { key: 'attempts', header: 'Attempts', align: 'right', cell: (g) => <span className="tabular-nums">{g.attempts}</span> },
  {
    key: 'accuracy',
    header: 'Accuracy',
    align: 'right',
    cell: (g) => <span className="tabular-nums">{Math.round(g.accuracy * 100)}%</span>,
  },
]

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
    <article className="rounded-xl border border-border bg-canvas-soft p-4">
      <header className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone="neutral" className="font-mono">
          {d.section}
        </Badge>
        <Badge tone="neutral">{d.difficulty}</Badge>
        <span className="text-subtle">
          confidence {(proposal.confidence * 100).toFixed(0)}%
        </span>
        <span className="text-border-strong">·</span>
        <span className="text-subtle">{proposal.model}</span>
        <span className="ml-auto font-mono text-subtle">{proposal.id}</span>
      </header>
      <div className="mt-3 whitespace-pre-wrap text-sm text-ink">{d.stem}</div>
      <ol className="mt-3 space-y-1 text-sm">
        {d.choices.map((c) => (
          <li
            key={c.label}
            className={c.label === d.correct ? 'text-success' : 'text-muted'}
          >
            <span className="font-mono">{c.label}.</span> {c.text}
            {c.label === d.correct && (
              <span className="ml-2 text-xs uppercase tracking-wide">correct</span>
            )}
          </li>
        ))}
      </ol>
      <details className="mt-3 text-sm text-muted">
        <summary className="cursor-pointer text-ink">Explanation</summary>
        <p className="mt-2 whitespace-pre-wrap">{d.explanation}</p>
      </details>
      <footer className="mt-4 flex items-center justify-end gap-2">
        <Button variant="danger" size="sm" onClick={onReject} loading={busy}>
          Reject
        </Button>
        <Button
          size="sm"
          className="bg-success text-white hover:bg-success/90"
          onClick={onApprove}
          loading={busy}
        >
          {busy ? 'Working…' : 'Approve & promote'}
        </Button>
      </footer>
    </article>
  )
}
