'use client'

/**
 * Diagnose step — name the question type and the strategy before the answer
 * choices appear (spec 053 FR-10, FR-11).
 *
 * The exam signals type through stem phrasing, and a solver who reads that
 * signal first knows the task, the method and the traps before seeing a single
 * choice. Nothing in the lab practised that read: the solve guide's "orient"
 * step *told* the learner the type. This asks them to commit to one, marks it,
 * and then hands over the playbook — the cue that gave it away, the task, the
 * method, and the traps this type is built around — as the feedback.
 *
 * Mounted by `QuestionCard` in place of the choice list while a diagnosis is
 * pending; the card owns when it appears and what happens after "Continue".
 *
 * static-parity: none — the exercise needs the diagnose endpoints, which the build-time bundle has no server for; the static mirror is BL-20260907-16.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import {
  fetchLsatDiagnosis,
  submitLsatDiagnosis,
  type LsatDiagnosisOption,
  type LsatDiagnosisPrompt,
  type LsatDiagnosisResult,
  type LsatSection,
} from '@/lib/api'

export default function DiagnoseStep({
  questionId,
  section,
  onComplete,
}: {
  questionId: string
  section: LsatSection
  /**
   * Called when the learner moves on to the choices — with the graded
   * diagnosis, or `null` when they skipped it.
   */
  onComplete: (result: LsatDiagnosisResult | null) => void
}) {
  const [prompt, setPrompt] = useState<LsatDiagnosisPrompt | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [type, setType] = useState<string | null>(null)
  const [strategy, setStrategy] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<LsatDiagnosisResult | null>(null)

  // Mounted with `key={questionId}` by the card, so a new question is a fresh
  // instance and nothing here needs resetting — only fetching.
  useEffect(() => {
    let live = true
    fetchLsatDiagnosis(questionId)
      .then((p) => {
        if (live) setPrompt(p)
      })
      .catch((e: unknown) => {
        if (live)
          setLoadError(e instanceof Error ? e.message : 'Could not load')
      })
    return () => {
      live = false
    }
  }, [questionId])

  const submit = async () => {
    if (!type || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      setResult(await submitLsatDiagnosis(questionId, type, strategy))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Diagnosis failed')
    } finally {
      setSubmitting(false)
    }
  }

  const sectionWord = section === 'LG' ? 'game question' : 'question'

  return (
    <section
      aria-label="Diagnose the question"
      className="mt-5 rounded-xl border border-violet-500/30 bg-violet-500/5 p-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-violet-300">
          Diagnose first
        </h3>
        {!result && (
          <button
            type="button"
            onClick={() => onComplete(null)}
            className="text-[11px] text-slate-400 underline underline-offset-2 hover:text-slate-200"
          >
            Skip and show the choices
          </button>
        )}
      </div>
      <p className="mt-1 text-xs text-slate-400">
        Read the stem, not the choices. What kind of {sectionWord} is this, and
        what would you do first?
      </p>

      {loadError && (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {loadError}{' '}
          <button
            type="button"
            onClick={() => onComplete(null)}
            className="underline underline-offset-2"
          >
            Show the choices instead
          </button>
        </p>
      )}

      {!prompt && !loadError && (
        <p className="mt-3 text-sm text-slate-400" role="status">
          Dealing the options…
        </p>
      )}

      {prompt && !result && (
        <>
          <OptionGroup
            label="1. What type of question is this?"
            options={prompt.type_options}
            value={type}
            onChange={setType}
          />
          <OptionGroup
            label="2. Which strategy applies?"
            options={prompt.strategy_options}
            value={strategy}
            onChange={setStrategy}
            optional
          />
          {error && (
            <p className="mt-3 text-sm text-red-300" role="alert">
              {error}
            </p>
          )}
          <div className="mt-4">
            <button
              type="button"
              onClick={() => void submit()}
              disabled={!type || submitting}
              className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-500/20 transition hover:shadow-violet-500/40 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
            >
              {submitting ? 'Checking…' : 'Check my read'}
            </button>
          </div>
        </>
      )}

      {result && (
        <Feedback result={result} onContinue={() => onComplete(result)} />
      )}
    </section>
  )
}

function OptionGroup({
  label,
  options,
  value,
  onChange,
  optional = false,
}: {
  label: string
  options: LsatDiagnosisOption[]
  value: string | null
  onChange: (id: string) => void
  optional?: boolean
}) {
  return (
    <div className="mt-4">
      <div className="text-xs font-medium text-slate-300">
        {label}
        {optional && (
          <span className="ml-1 font-normal text-slate-400">(optional)</span>
        )}
      </div>
      <ul role="radiogroup" aria-label={label} className="mt-2 flex flex-wrap gap-2">
        {options.map((o) => {
          const on = value === o.id
          return (
            <li key={o.id}>
              <button
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => onChange(o.id)}
                className={
                  'rounded-lg border px-3 py-1.5 text-sm transition focus-ring ' +
                  (on
                    ? 'border-violet-400/70 bg-violet-500/15 text-violet-100'
                    : 'border-slate-800 bg-slate-950/40 text-slate-200 hover:border-slate-600')
                }
              >
                {o.name}
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function Verdict({
  label,
  ok,
  detail,
}: {
  label: string
  ok: boolean | 'partial'
  detail: string
}) {
  const cls =
    ok === true
      ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/30'
      : ok === 'partial'
        ? 'bg-amber-500/15 text-amber-200 ring-amber-500/30'
        : 'bg-red-500/15 text-red-300 ring-red-500/30'
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span
        className={
          'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ' +
          cls
        }
      >
        {label}: {ok === true ? 'right' : ok === 'partial' ? 'close' : 'not quite'}
      </span>
      <span className="text-slate-300">{detail}</span>
    </div>
  )
}

function Feedback({
  result,
  onContinue,
}: {
  result: LsatDiagnosisResult
  onContinue: () => void
}) {
  const pb = result.playbook
  const typeDetail = result.archetype_correct
    ? `This is a ${result.archetype_name} question.`
    : result.family_correct
      ? `Right family — but this one is specifically ${result.archetype_name}${
          result.chosen_archetype_name ? `, not ${result.chosen_archetype_name}` : ''
        }.`
      : `This is a ${result.archetype_name} question${
          result.chosen_archetype_name ? `, not ${result.chosen_archetype_name}` : ''
        }.`
  const strategyDetail =
    result.strategy_correct === null
      ? `Start with: ${pb.strategies[0]?.name ?? '—'}.`
      : result.strategy_correct
        ? 'That is the move this type rewards.'
        : `Lead with ${pb.strategies[0]?.name ?? 'the playbook strategy'} instead.`

  return (
    <div className="mt-4 space-y-4" role="status" aria-live="polite">
      <div className="space-y-2">
        <Verdict
          label="Type"
          ok={result.archetype_correct ? true : result.family_correct ? 'partial' : false}
          detail={typeDetail}
        />
        {result.strategy_correct !== null && (
          <Verdict label="Strategy" ok={result.strategy_correct} detail={strategyDetail} />
        )}
        {result.strategy_correct === null && (
          <p className="text-sm text-slate-300">{strategyDetail}</p>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
          <div className="text-[11px] uppercase tracking-wider text-slate-400">
            How to spot it
          </div>
          {result.matched_cue && (
            <p className="mt-1 text-sm text-slate-200">
              The stem says{' '}
              <mark className="rounded bg-violet-500/20 px-1 text-violet-100">
                “{result.matched_cue}”
              </mark>
              .
            </p>
          )}
          <ul className="mt-2 space-y-1 text-xs text-slate-400">
            {pb.cues.map((c) => (
              <li key={c} className="italic">
                “{c}”
              </li>
            ))}
          </ul>
          <div className="mt-3 text-[11px] uppercase tracking-wider text-slate-400">
            The task
          </div>
          <p className="mt-1 text-sm text-slate-200">{pb.task}</p>
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
          <div className="text-[11px] uppercase tracking-wider text-slate-400">
            Method
          </div>
          <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm text-slate-200">
            {pb.method.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ol>
          <div className="mt-3 text-[11px] uppercase tracking-wider text-slate-400">
            Strategies
          </div>
          <ul className="mt-1 space-y-1 text-sm">
            {pb.strategies.map((s) => (
              <li key={s.id}>
                <span className="font-medium text-slate-100">{s.name}</span>
                <span className="text-slate-400"> — {s.summary}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
        <div className="text-[11px] uppercase tracking-wider text-amber-300">
          Traps to expect in the choices
        </div>
        <ul className="mt-1 space-y-1 text-sm">
          {pb.traps.map((t) => (
            <li key={t.id}>
              <span className="font-medium text-amber-100">{t.name}</span>
              <span className="text-slate-400"> — {t.summary}</span>
            </li>
          ))}
        </ul>
        {pb.confused_with.length > 0 && (
          <p className="mt-2 text-xs text-slate-400">
            Often mistaken for:{' '}
            {pb.confused_with.map((c) => c.name).join(' · ')}
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onContinue}
          className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-500/20 transition hover:shadow-blue-500/40"
        >
          Now answer it →
        </button>
        <Link
          href={`/lsat/playbooks#${pb.archetype_id}`}
          className="text-xs text-amber-300 underline underline-offset-2 hover:text-amber-200"
        >
          Open the {pb.name} playbook
        </Link>
      </div>
    </div>
  )
}
