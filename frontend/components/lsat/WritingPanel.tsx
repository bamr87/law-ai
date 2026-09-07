'use client'

/**
 * Argumentative Writing in the platform lab (BL-20260901-09).
 *
 * A port of `lsat-static/components/Writing.tsx`, which spec 047 FR-3 built
 * for the published static site. Until this landed the lab had no Writing
 * surface at all: WS was a section the API served, the Overview card said
 * "no drill in the lab yet", and the only way to practise the one LSAT task
 * that produces prose was to leave for the static export.
 *
 * Three phases, same as the static site: pick a prompt, draft against the
 * clock, then review. Review is gated behind submitting — the rubric's band
 * notes and the annotated model response exist from the first byte, but
 * reading the worked example before drafting destroys the exercise, so they
 * stay locked exactly the way `SolveAssist` locks spoiler steps until a
 * question is graded. The server enforces the same thing: the prompt payload
 * is `PublicWritingPrompt` and the model response arrives only when it is
 * asked for by name.
 *
 * What the platform adds over the static port, because it has a backend the
 * static bundle does not: `POST /api/lsat/writing/evaluate` reads the draft
 * against the same rubric and returns criterion bands. It is offered *after*
 * the self-check, never instead of it, and every band it returns is labelled
 * with the model that produced it (NFR-PROV-1).
 *
 * static-parity: lsat-static/components/Writing.tsx
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  evaluateLsatWriting,
  fetchLsatWritingPrompt,
  fetchLsatWritingPrompts,
  type LsatWritingEvaluationResult,
  type LsatWritingModelResponse,
  type LsatWritingPrompt,
  type LsatWritingPromptDetail,
  type LsatWritingRubric,
} from '@/lib/api'
import {
  ErrorBanner,
  DiffBadge,
  SkeletonGrid,
  SkeletonQuestion,
} from '@/components/lsat/LabPrimitives'
import { usePageShortcuts } from '@/components/shell/PageShortcuts'
import { LSAT_WRITING_SHORTCUTS } from '@/components/lsat/drillShortcuts'
import { useShortcuts } from '@/lib/lsat/keyboard'
import {
  loadWritingDraft,
  loadWritingSubmitted,
  saveWritingDraft,
  saveWritingSubmitted,
} from '@/lib/lsat/writingDrafts'

/** Words the draft needs before it can be submitted, matching the static site. */
const MIN_WORDS = 50

function countWords(text: string): number {
  const trimmed = text.trim()
  return trimmed ? trimmed.split(/\s+/).length : 0
}

function mmss(totalSeconds: number): string {
  const s = Math.max(0, totalSeconds)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export default function WritingPanel({
  onEvaluated,
}: {
  /**
   * Fired once a rubric evaluation comes back (BL-20260905-42). The writing
   * bands land in `/api/lsat/stats`, and the lab only refreshed those from a
   * graded MCQ — so an essay read in this tab left the Stats tab's
   * Argumentative Writing card quoting the previous run until the learner went
   * back and answered a question. This is the writing half of `onAttempt`.
   */
  onEvaluated?: () => void
} = {}) {
  // Publish this surface's keys to the shell's `?` sheet, so O/T/M/mod+Enter
  // are discoverable somewhere other than the hint line under the textarea.
  usePageShortcuts(LSAT_WRITING_SHORTCUTS)
  const [prompts, setPrompts] = useState<LsatWritingPrompt[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  // Bumped by the `O` shortcut only. Opening a prompt with the mouse must not
  // yank focus into the textarea — the click already put the reader where they
  // meant to be — but the key that means "start writing" has to land the caret.
  const [focusEditorAt, setFocusEditorAt] = useState(0)

  const load = useCallback(async () => {
    setError(null)
    try {
      const body = await fetchLsatWritingPrompts()
      setPrompts(body.prompts)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load writing prompts')
      setPrompts([])
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  // `O` opens the first prompt from the list and puts the caret in the editor,
  // then afterwards is the way back *into* the editor — the static site's
  // binding, unchanged.
  useShortcuts({
    o: () => {
      if (!openId && prompts && prompts.length > 0) setOpenId(prompts[0].id)
      setFocusEditorAt((n) => n + 1)
    },
  })

  useEffect(() => {
    if (focusEditorAt === 0) return
    document.getElementById('writing-draft')?.focus()
  }, [focusEditorAt])

  const open = prompts?.find((p) => p.id === openId) ?? null

  return (
    <section className="space-y-4" aria-label="Argumentative Writing">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3 backdrop-blur">
        <div className="text-xs uppercase tracking-wider text-slate-400">
          Section: Argumentative Writing
        </div>
        <div className="text-xs text-slate-400">
          Unscored on the real exam — law schools read it. 35 minutes.
        </div>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}
      {prompts === null && <SkeletonGrid />}
      {prompts !== null && prompts.length === 0 && !error && (
        <p className="text-sm text-slate-400">
          No writing prompts have been authored yet.
        </p>
      )}

      {prompts !== null && prompts.length > 0 && !open && (
        <PromptList prompts={prompts} onOpen={setOpenId} />
      )}
      {open && (
        <PromptWorkspace
          key={open.id}
          prompt={open}
          onBack={() => setOpenId(null)}
          onEvaluated={onEvaluated}
        />
      )}
    </section>
  )
}

function PromptList({
  prompts,
  onOpen,
}: {
  prompts: LsatWritingPrompt[]
  onOpen: (id: string) => void
}) {
  return (
    <ul className="grid gap-3 md:grid-cols-2">
      {prompts.map((p) => (
        <li
          key={p.id}
          className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 backdrop-blur"
        >
          <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wider text-slate-400">
            <span className="font-mono text-slate-400">{p.id}</span>
            <span className="text-slate-700">·</span>
            <DiffBadge difficulty={p.difficulty} />
          </div>
          <h3 className="mt-2 text-base font-semibold text-slate-100">
            {p.title}
          </h3>
          <p className="mt-1 text-sm text-slate-300">{p.issue}</p>
          <p className="mt-2 text-xs text-slate-400">
            {p.positions.length} positions · {p.perspectives.length} perspectives
            · {p.time_limit_minutes} min
          </p>
          <button
            type="button"
            onClick={() => onOpen(p.id)}
            className="tap-target mt-3 inline-flex items-center gap-2 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-500/20 transition hover:shadow-blue-500/40"
          >
            Open prompt
          </button>
        </li>
      ))}
    </ul>
  )
}

function PromptWorkspace({
  prompt,
  onBack,
  onEvaluated,
}: {
  prompt: LsatWritingPrompt
  onBack: () => void
  onEvaluated?: () => void
}) {
  const [detail, setDetail] = useState<LsatWritingPromptDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [hydrated, setHydrated] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  // Restore after mount, never during render: this is a client component in a
  // server-rendered tree, where localStorage does not exist.
  useEffect(() => {
    setDraft(loadWritingDraft(prompt.id))
    setSubmitted(loadWritingSubmitted(prompt.id))
    setHydrated(true)
  }, [prompt.id])

  useEffect(() => {
    if (hydrated) saveWritingDraft(prompt.id, draft)
  }, [draft, hydrated, prompt.id])

  useEffect(() => {
    let live = true
    void (async () => {
      try {
        const body = await fetchLsatWritingPrompt(prompt.id)
        if (live) setDetail(body)
      } catch (e) {
        if (live) {
          setError(e instanceof Error ? e.message : 'Failed to load the prompt')
        }
      }
    })()
    return () => {
      live = false
    }
  }, [prompt.id])

  const words = countWords(draft)
  const submit = useCallback(() => {
    saveWritingSubmitted(prompt.id)
    setSubmitted(true)
  }, [prompt.id])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className="tap-target inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
        >
          ← All prompts
        </button>
        <span className="text-xs text-slate-400">{prompt.title}</span>
      </div>

      {error && <ErrorBanner message={error} />}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <PromptReader prompt={prompt} />
        <div className="space-y-4">
          {!submitted ? (
            <DraftPanel
              prompt={prompt}
              draft={draft}
              words={words}
              onChange={setDraft}
              onSubmit={submit}
            />
          ) : detail ? (
            <ReviewPanel
              prompt={prompt}
              rubric={detail.rubric}
              draft={draft}
              words={words}
              onEvaluated={onEvaluated}
            />
          ) : (
            <SkeletonQuestion />
          )}
        </div>
      </div>
    </div>
  )
}

function PromptReader({ prompt }: { prompt: LsatWritingPrompt }) {
  return (
    <article className="shell-sticky-aside shell-panel-scroll max-h-[calc(100dvh-var(--shell-masthead-h)-var(--shell-pageheader-h)-var(--shell-toolbar-h)-3rem)] rounded-2xl border border-slate-800 bg-slate-900/40 p-5 backdrop-blur">
      <div className="text-[11px] uppercase tracking-wider text-amber-400">
        Argumentative Writing
      </div>
      <h3 className="mt-1 text-lg font-semibold text-slate-100">
        {prompt.issue}
      </h3>
      <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-slate-200">
        {prompt.context}
      </p>

      <h4 className="mt-5 text-xs font-semibold uppercase tracking-wider text-slate-400">
        Positions
      </h4>
      <ul className="mt-2 space-y-1 text-sm text-slate-200">
        {prompt.positions.map((p) => (
          <li key={p.id}>
            <strong className="text-slate-100">{p.name}</strong> — {p.summary}
          </li>
        ))}
      </ul>

      <h4 className="mt-5 text-xs font-semibold uppercase tracking-wider text-slate-400">
        Perspectives
      </h4>
      <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-200">
        {prompt.perspectives.map((p) => (
          <li key={p.id}>{p.text}</li>
        ))}
      </ul>

      <h4 className="mt-5 text-xs font-semibold uppercase tracking-wider text-slate-400">
        Your task
      </h4>
      <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-slate-200">
        {prompt.task}
      </p>
    </article>
  )
}

function DraftPanel({
  prompt,
  draft,
  words,
  onChange,
  onSubmit,
}: {
  prompt: LsatWritingPrompt
  draft: string
  words: number
  onChange: (v: string) => void
  onSubmit: () => void
}) {
  const total = prompt.time_limit_minutes * 60
  const [remaining, setRemaining] = useState(total)
  const [running, setRunning] = useState(false)
  const tick = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!running) return
    tick.current = setInterval(() => {
      setRemaining((r) => (r <= 1 ? 0 : r - 1))
    }, 1000)
    return () => {
      if (tick.current) clearInterval(tick.current)
    }
  }, [running])

  useEffect(() => {
    if (remaining === 0) setRunning(false)
  }, [remaining])

  const urgent = remaining <= 300 && remaining > 0
  const expired = remaining === 0
  const canSubmit = words >= MIN_WORDS

  // `mod+Enter` is the one binding that fires from inside the textarea — the
  // universal "submit this composition" gesture, and the only safe shape here
  // because a bare key would be swallowed by the essay. `T` needs the field
  // blurred first, which is what Escape on the textarea does.
  useShortcuts({
    t: () => {
      if (!expired) setRunning((r) => !r)
    },
    'mod+Enter': () => {
      if (canSubmit) onSubmit()
    },
  })

  return (
    <section aria-label="Drafting" className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3 backdrop-blur">
        <span className="text-[11px] uppercase tracking-wider text-slate-400">
          Writing time
        </span>
        <span
          role="timer"
          aria-live="off"
          className={
            'font-mono text-lg tabular-nums ' +
            (expired
              ? 'text-red-300'
              : urgent
                ? 'text-amber-300'
                : 'text-slate-100')
          }
        >
          {mmss(remaining)}
        </span>
        <button
          type="button"
          aria-keyshortcuts="T"
          onClick={() => setRunning((r) => !r)}
          disabled={expired}
          className="tap-target rounded-md border border-slate-700 bg-slate-900/60 px-2.5 py-1 text-xs font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white disabled:opacity-30"
        >
          {running ? 'Pause' : 'Start'}
        </button>
        <button
          type="button"
          onClick={() => {
            setRunning(false)
            setRemaining(total)
          }}
          className="tap-target rounded-md border border-slate-700 bg-slate-900/60 px-2.5 py-1 text-xs font-semibold text-slate-200 transition hover:border-slate-500 hover:text-white"
        >
          Reset
        </button>
        <span className="text-[11px] text-slate-400">
          Take the pre-writing period ({prompt.prewriting_minutes} min on the
          real exam) before you start the clock.
        </span>
      </div>

      <label htmlFor="writing-draft" className="sr-only">
        Your response
      </label>
      <textarea
        id="writing-draft"
        rows={18}
        value={draft}
        placeholder="Write your response here. Your draft is saved in this browser only."
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          // Escape leaves the field so the bare-key shortcuts become reachable
          // again. It is handled here rather than in the shortcut module
          // because the shell owns Escape on every route, and a window binding
          // would be two listeners answering one key. Stopping propagation
          // keeps this press from also dismissing a shell drawer.
          if (e.key === 'Escape') {
            e.stopPropagation()
            e.currentTarget.blur()
          }
        }}
        aria-describedby="writing-draft-meta"
        className="w-full rounded-2xl border border-slate-800 bg-slate-950/60 p-4 text-sm leading-relaxed text-slate-100 focus:border-blue-500 focus-ring"
      />
      <p id="writing-draft-meta" className="text-[11px] text-slate-400">
        {words} words · saved in this browser only ·{' '}
        <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
          Ctrl
        </kbd>
        /
        <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
          ⌘
        </kbd>
        +
        <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
          Enter
        </kbd>{' '}
        submits and unlocks the rubric and the model response ·{' '}
        <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
          Esc
        </kbd>{' '}
        leaves the editor,{' '}
        <kbd className="rounded border border-slate-700 bg-slate-800/60 px-1 font-mono text-slate-300">
          O
        </kbd>{' '}
        returns
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          aria-keyshortcuts="Control+Enter Meta+Enter"
          onClick={onSubmit}
          disabled={!canSubmit}
          className="tap-target inline-flex items-center gap-2 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-500/20 transition hover:shadow-blue-500/40 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
        >
          Submit and unlock feedback
        </button>
        {!canSubmit && (
          <span className="text-xs text-slate-400">
            Write at least {MIN_WORDS} words to submit.
          </span>
        )}
      </div>
    </section>
  )
}

function ReviewPanel({
  prompt,
  rubric,
  draft,
  words,
  onEvaluated,
}: {
  prompt: LsatWritingPrompt
  rubric: LsatWritingRubric
  draft: string
  words: number
  onEvaluated?: () => void
}) {
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [model, setModel] = useState<LsatWritingModelResponse | null>(null)
  const [showModel, setShowModel] = useState(false)
  const [modelError, setModelError] = useState<string | null>(null)

  // The model response is *not* in the payload the list served — the server
  // withholds it until it is asked for by name, so revealing it is a fetch.
  const revealModel = useCallback(async () => {
    if (model) {
      setShowModel((v) => !v)
      return
    }
    setModelError(null)
    try {
      const body = await fetchLsatWritingPrompt(prompt.id, {
        modelResponse: true,
      })
      setModel(body.model_response ?? null)
      setShowModel(true)
    } catch (e) {
      setModelError(
        e instanceof Error ? e.message : 'Failed to load the model response',
      )
    }
  }, [model, prompt.id])

  useShortcuts({ m: () => void revealModel() })

  const modelPosition = prompt.positions.find(
    (p) => p.id === model?.position_id,
  )
  const annotations = useMemo(
    () => new Map((model?.annotations ?? []).map((a) => [a.criterion_id, a.note])),
    [model],
  )

  return (
    <section aria-label="Review" className="space-y-4">
      <p className="text-xs text-slate-400">
        Your draft: {words} words. Score it yourself against the rubric before
        you read the model response — a worked example read first becomes a
        template rather than a comparison.
      </p>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 backdrop-blur">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Self-check
        </h3>
        <ul className="mt-3 space-y-3">
          {prompt.self_check.map((item) => {
            const criterion = rubric.criteria.find(
              (c) => c.id === item.criterion_id,
            )
            const id = `check-${item.criterion_id}`
            return (
              <li key={item.criterion_id}>
                <label htmlFor={id} className="flex items-start gap-2 text-sm">
                  <input
                    id={id}
                    type="checkbox"
                    checked={Boolean(checked[item.criterion_id])}
                    onChange={(e) =>
                      setChecked((prev) => ({
                        ...prev,
                        [item.criterion_id]: e.target.checked,
                      }))
                    }
                    className="mt-1"
                  />
                  <span className="text-slate-200">
                    <strong className="text-slate-100">
                      {criterion?.name ?? item.criterion_id}
                    </strong>{' '}
                    {item.prompt}
                  </span>
                </label>
                {criterion && (
                  <details className="ml-6 mt-1 text-xs text-slate-400">
                    <summary className="cursor-pointer">
                      Band descriptions
                    </summary>
                    <ul className="mt-1 space-y-1">
                      {rubric.bands.map((b) => (
                        <li key={b.level}>
                          <strong className="text-slate-300">
                            {b.level} · {b.label}
                          </strong>{' '}
                          {criterion.band_notes[String(b.level)] ?? b.descriptor}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </li>
            )
          })}
        </ul>
        <p className="mt-3 text-xs text-slate-400">{rubric.summary}</p>
      </div>

      <EvaluationCard
        promptId={prompt.id}
        rubric={rubric}
        draft={draft}
        onEvaluated={onEvaluated}
      />

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          aria-keyshortcuts="M"
          aria-expanded={showModel}
          onClick={() => void revealModel()}
          className="tap-target inline-flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-200 transition hover:bg-amber-500/20"
        >
          {showModel ? 'Hide model response' : 'Show the annotated model response'}
        </button>
      </div>
      {modelError && <ErrorBanner message={modelError} />}

      {showModel && model && (
        <article className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 backdrop-blur">
          <p className="text-xs text-slate-400">
            One defensible response, arguing for{' '}
            <strong className="text-slate-300">
              {modelPosition?.name ?? model.position_id}
            </strong>
            . The opposite position can reach the same band — this is an
            example, not a key.
          </p>
          <p className="mt-3 text-sm font-semibold text-slate-100">
            {model.thesis}
          </p>
          {model.essay.split('\n\n').map((para, i) => (
            <p key={i} className="mt-3 text-sm leading-relaxed text-slate-200">
              {para}
            </p>
          ))}
          <h4 className="mt-5 text-xs font-semibold uppercase tracking-wider text-slate-400">
            Where it earns each criterion
          </h4>
          <ul className="mt-2 space-y-1 text-sm text-slate-200">
            {rubric.criteria.map((c) => (
              <li key={c.id}>
                <strong className="text-slate-100">{c.name}</strong> —{' '}
                {annotations.get(c.id) ?? '—'}
              </li>
            ))}
          </ul>
        </article>
      )}

      {draft.trim() && (
        <details className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-200 backdrop-blur">
          <summary className="cursor-pointer text-xs uppercase tracking-wider text-slate-400">
            Your submitted draft
          </summary>
          <p className="mt-3 whitespace-pre-line leading-relaxed">{draft}</p>
        </details>
      )}
    </section>
  )
}

/**
 * The half the static bundle cannot have: the same rubric, read by a model.
 *
 * Opt-in rather than automatic. It costs a provider call, it arrives after the
 * learner has done the self-check that is the actual exercise, and every band
 * it produces is named as machine-derived at the point of display.
 */
function EvaluationCard({
  promptId,
  rubric,
  draft,
  onEvaluated,
}: {
  promptId: string
  rubric: LsatWritingRubric
  draft: string
  onEvaluated?: () => void
}) {
  const [result, setResult] = useState<LsatWritingEvaluationResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setLoading(true)
    setError(null)
    try {
      setResult(await evaluateLsatWriting(promptId, draft))
      // The band the server just recorded is now part of `/api/lsat/stats`.
      // Only on success: a failed call changed nothing to refresh.
      onEvaluated?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Evaluation failed')
    } finally {
      setLoading(false)
    }
  }

  if (!draft.trim()) return null

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Rubric feedback
        </h3>
        <button
          type="button"
          onClick={() => void run()}
          disabled={loading}
          className="tap-target inline-flex items-center gap-2 rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-200 transition hover:bg-sky-500/20 disabled:opacity-40"
        >
          {loading
            ? 'Reading your draft…'
            : result
              ? 'Read it again'
              : 'Read my draft against the rubric'}
        </button>
      </div>
      {error && (
        <p className="mt-2 text-sm text-red-300" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="mt-3 space-y-3">
          <p className="text-[11px] uppercase tracking-wider text-slate-400">
            Machine-derived · {result.model} · prompt {result.prompt_version}
            {result.degraded && ' · degraded fallback'}
          </p>
          <p className="text-sm text-slate-200">{result.evaluation.summary}</p>
          <p className="text-xs text-slate-400">
            Weighted band {result.evaluation.weighted_band.toFixed(2)} — a study
            instrument only; the LSAT writing section carries no score.
          </p>
          <ul className="space-y-2">
            {result.evaluation.criteria.map((c) => {
              const criterion = rubric.criteria.find(
                (r) => r.id === c.criterion_id,
              )
              return (
                <li
                  key={c.criterion_id}
                  className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm"
                >
                  <p className="text-xs uppercase tracking-wider text-slate-400">
                    {criterion?.name ?? c.criterion_id} · band {c.band}
                  </p>
                  <p className="mt-1 text-slate-200">{c.evidence}</p>
                  <p className="mt-1 text-slate-400">{c.improvement}</p>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
