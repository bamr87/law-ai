'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { WritingPrompt } from '@/lib/types'
import { rubricFor, sectionMeta, writingPrompts } from '@/lib/data'
import { useShortcuts } from '@/lib/keyboard'

/**
 * Argumentative Writing practice (spec 047 FR-3).
 *
 * Three states: pick a prompt, draft against a 35-minute clock, then review.
 * Review is gated behind submitting — the rubric's band notes and the
 * annotated model response are in the bundle from the first byte, but reading
 * the model answer before drafting destroys the exercise, so they stay locked
 * exactly the way `SolveAssist` locks spoiler steps until a question is
 * graded.
 *
 * Everything here works with no network and no model call: the whole feedback
 * loop is the rubric plus the worked example (NFR-OFFLINE-1).
 */

type Phase = 'list' | 'draft' | 'review'

const DRAFT_KEY = (id: string) => `lsat-writing:draft:${id}`
const DONE_KEY = (id: string) => `lsat-writing:submitted:${id}`

function readLocal(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    // Private browsing and blocked site-data both throw here; a lost draft is
    // a worse outcome than a lost feature, but neither should break the page.
    return null
  }
}

function writeLocal(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* storage unavailable — drafting still works for this session */
  }
}

function countWords(text: string): number {
  const trimmed = text.trim()
  return trimmed ? trimmed.split(/\s+/).length : 0
}

function mmss(totalSeconds: number): string {
  const s = Math.max(0, totalSeconds)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export default function Writing({ onAnnounce }: { onAnnounce?: (m: string) => void }) {
  const meta = sectionMeta('WS')
  const [phase, setPhase] = useState<Phase>('list')
  const [promptId, setPromptId] = useState<string | null>(null)

  const prompt = useMemo(
    () => writingPrompts.find((p) => p.id === promptId),
    [promptId],
  )

  const open = useCallback((p: WritingPrompt) => {
    setPromptId(p.id)
    setPhase(readLocal(DONE_KEY(p.id)) === '1' ? 'review' : 'draft')
  }, [])

  // From the list, O opens the first prompt so the section is enterable
  // without reaching for a card — and then puts the caret in the editor,
  // because "open the writing task" and "be able to write" are the same
  // intention. Opening it left focus on <body> six Tab stops from the
  // textarea, which made the one shortcut into the section useless on its own.
  //
  // From the workspace the same key is the way back *in* after Escape blurs
  // the field, so the pair is symmetric: Escape leaves the editor, O returns.
  // It is one binding rather than two because a mouse-opened prompt must not
  // yank focus into the textarea — the click already put the reader where
  // they meant to be, and scrolling the prompt off screen would undo that.
  const [focusEditorAt, setFocusEditorAt] = useState(0)

  useShortcuts({
    o: () => {
      if (phase === 'list' && writingPrompts.length > 0) open(writingPrompts[0])
      setFocusEditorAt((n) => n + 1)
    },
  })

  // Runs after the workspace has committed, so the textarea exists whether O
  // opened the prompt just now or it was already open.
  useEffect(() => {
    if (focusEditorAt === 0) return
    document.getElementById('writing-draft')?.focus()
  }, [focusEditorAt])

  if (writingPrompts.length === 0) {
    return <p className="empty">No writing prompts in this bundle yet.</p>
  }

  return (
    <section aria-label="Argumentative Writing">
      <div className="drill-head">
        <div>
          <h2>{meta?.name ?? 'Argumentative Writing'}</h2>
          {meta?.timing && <p className="drill-timing">{meta.timing}</p>}
        </div>
      </div>

      {phase === 'list' || !prompt ? (
        <PromptList onOpen={open} />
      ) : (
        <PromptWorkspace
          key={prompt.id}
          prompt={prompt}
          phase={phase === 'review' ? 'review' : 'draft'}
          onSubmit={() => {
            writeLocal(DONE_KEY(prompt.id), '1')
            setPhase('review')
            onAnnounce?.('Draft submitted. Rubric and model response unlocked.')
          }}
          onBack={() => {
            setPhase('list')
            setPromptId(null)
          }}
        />
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------

function PromptList({ onOpen }: { onOpen: (p: WritingPrompt) => void }) {
  const meta = sectionMeta('WS')
  return (
    <>
      {meta?.description && <p className="intro">{meta.description}</p>}
      <ul className="cards">
        {writingPrompts.map((p) => (
          <li key={p.id} className="card">
            <div className="card-head">
              <h3>{p.title}</h3>
              <span className="pill">{p.difficulty}</span>
            </div>
            <p className="card-desc">{p.issue}</p>
            <p className="card-facts">
              {p.positions.length} positions · {p.perspectives.length} perspectives ·{' '}
              {p.time_limit_minutes} min
            </p>
            <button type="button" className="btn btn-primary" onClick={() => onOpen(p)}>
              Open prompt
            </button>
          </li>
        ))}
      </ul>
    </>
  )
}

// ---------------------------------------------------------------------------

function PromptWorkspace({
  prompt,
  phase,
  onSubmit,
  onBack,
}: {
  prompt: WritingPrompt
  phase: 'draft' | 'review'
  onSubmit: () => void
  onBack: () => void
}) {
  const [draft, setDraft] = useState('')
  const [hydrated, setHydrated] = useState(false)

  // Restore after mount, never during render: the static export prerenders
  // this component on the server, where localStorage does not exist.
  useEffect(() => {
    setDraft(readLocal(DRAFT_KEY(prompt.id)) ?? '')
    setHydrated(true)
  }, [prompt.id])

  useEffect(() => {
    if (hydrated) writeLocal(DRAFT_KEY(prompt.id), draft)
  }, [draft, hydrated, prompt.id])

  const words = countWords(draft)

  // Escape is two-stage on purpose. A single Escape that jumped straight back
  // to the list would discard the editor from under someone who only wanted
  // out of the text field to reach a shortcut — so the first press blurs, and
  // only a second one leaves.
  useShortcuts(
    {
      Escape: () => {
        const active = document.activeElement
        if (active instanceof HTMLElement && active.id === 'writing-draft') {
          active.blur()
          return
        }
        onBack()
      },
    },
    // Escape has to reach us from inside the editor — leaving the field is
    // the whole point of the first press.
    { allowWhileTyping: ['Escape'] },
  )

  return (
    <>
      <nav className="drill-nav" aria-label="Writing navigation">
        <button type="button" className="btn" aria-keyshortcuts="Escape" onClick={onBack}>
          ← All prompts
        </button>
        <span className="drill-progress">{prompt.title}</span>
      </nav>

      <article className="passage">
        <h3 className="passage-title">{prompt.issue}</h3>
        <p className="passage-body">{prompt.context}</p>

        <h4 className="passage-subhead">Positions</h4>
        <ul className="passage-rules">
          {prompt.positions.map((p) => (
            <li key={p.id}>
              <strong>{p.name}</strong> — {p.summary}
            </li>
          ))}
        </ul>

        <h4 className="passage-subhead">Perspectives</h4>
        <ul className="passage-rules">
          {prompt.perspectives.map((p) => (
            <li key={p.id}>{p.text}</li>
          ))}
        </ul>

        <h4 className="passage-subhead">Your task</h4>
        <p className="passage-summary">{prompt.task}</p>
      </article>

      {phase === 'draft' ? (
        <DraftPanel
          prompt={prompt}
          draft={draft}
          words={words}
          onChange={setDraft}
          onSubmit={onSubmit}
        />
      ) : (
        <ReviewPanel prompt={prompt} draft={draft} words={words} />
      )}
    </>
  )
}

// ---------------------------------------------------------------------------

function DraftPanel({
  prompt,
  draft,
  words,
  onChange,
  onSubmit,
}: {
  prompt: WritingPrompt
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
  const canSubmit = words >= 50

  // `mod+Enter` is the one binding that fires from inside the textarea — the
  // universal "submit this composition" gesture, and the only safe shape here
  // because a bare key would be swallowed by the essay. `t` needs the field
  // blurred first (Escape does that).
  useShortcuts({
    t: () => {
      if (!expired) setRunning((r) => !r)
    },
    'mod+Enter': () => {
      if (canSubmit) onSubmit()
    },
  })

  return (
    <section className="solve" aria-label="Drafting">
      <div className="section-timer">
        <span className="section-timer-label">Writing time</span>
        <span
          className={
            'section-timer-clock' +
            (expired ? ' section-timer-expired' : urgent ? ' section-timer-urgent' : '')
          }
          role="timer"
          aria-live="off"
        >
          {mmss(remaining)}
        </span>
        <div className="section-timer-controls">
          <button
            type="button"
            className="btn"
            aria-keyshortcuts="T"
            onClick={() => setRunning((r) => !r)}
            disabled={expired}
          >
            {running ? 'Pause' : 'Start'}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setRunning(false)
              setRemaining(total)
            }}
          >
            Reset
          </button>
        </div>
        <span className="section-timer-pace">
          Take the pre-writing period ({prompt.prewriting_minutes} min on the real
          exam) before you start the clock.
        </span>
      </div>

      <label className="search" htmlFor="writing-draft">
        <span className="sr-only">Your response</span>
      </label>
      <textarea
        id="writing-draft"
        className="writing-draft"
        rows={18}
        value={draft}
        placeholder="Write your response here. Your draft is saved in this browser only."
        onChange={(e) => onChange(e.target.value)}
        aria-describedby="writing-draft-meta"
      />
      <p id="writing-draft-meta" className="drill-timing">
        {words} words · saved in this browser only · <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+
        <kbd>Enter</kbd> submits and unlocks the rubric and the model response
      </p>

      <div className="solve-controls">
        <button
          type="button"
          className="btn btn-primary"
          aria-keyshortcuts="Control+Enter Meta+Enter"
          onClick={onSubmit}
          disabled={!canSubmit}
        >
          Submit and unlock feedback
        </button>
        {!canSubmit && (
          <span className="drill-timing">Write at least 50 words to submit.</span>
        )}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------

function ReviewPanel({
  prompt,
  draft,
  words,
}: {
  prompt: WritingPrompt
  draft: string
  words: number
}) {
  const rubric = rubricFor(prompt)
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [showModel, setShowModel] = useState(false)

  const modelPosition = prompt.positions.find(
    (p) => p.id === prompt.model_response.position_id,
  )
  const annotations = new Map(
    prompt.model_response.annotations.map((a) => [a.criterion_id, a.note]),
  )

  useShortcuts({ m: () => setShowModel((v) => !v) })

  return (
    <section className="solve" aria-label="Review">
      <p className="drill-timing">
        Your draft: {words} words. Score it yourself against the rubric before you read
        the model response — a worked example read first becomes a template rather than
        a comparison.
      </p>

      <h3 className="passage-subhead">Self-check</h3>
      <ul className="self-check">
        {prompt.self_check.map((item) => {
          const criterion = rubric?.criteria.find((c) => c.id === item.criterion_id)
          const id = `check-${item.criterion_id}`
          return (
            <li key={item.criterion_id} className="self-check-item">
              <label htmlFor={id}>
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
                />
                <span>
                  <strong>{criterion?.name ?? item.criterion_id}</strong>
                  <span className="self-check-prompt"> {item.prompt}</span>
                </span>
              </label>
              {criterion && (
                <details className="self-check-bands">
                  <summary>Band descriptions</summary>
                  <ul>
                    {rubric?.bands.map((b) => (
                      <li key={b.level}>
                        <strong>
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

      {rubric && <p className="drill-timing">{rubric.summary}</p>}

      <div className="solve-controls">
        <button
          type="button"
          className="btn btn-reveal"
          aria-keyshortcuts="M"
          onClick={() => setShowModel((v) => !v)}
          aria-expanded={showModel}
        >
          {showModel ? 'Hide model response' : 'Show the annotated model response'}
        </button>
      </div>

      {showModel && (
        <article className="model-response">
          <p className="drill-timing">
            One defensible response, arguing for{' '}
            <strong>{modelPosition?.name ?? prompt.model_response.position_id}</strong>.
            The opposite position can reach the same band — this is an example, not a
            key.
          </p>
          <p className="model-thesis">{prompt.model_response.thesis}</p>
          {prompt.model_response.essay.split('\n\n').map((para, i) => (
            <p key={i} className="passage-body">
              {para}
            </p>
          ))}

          <h4 className="passage-subhead">Where it earns each criterion</h4>
          <ul className="concept-examples">
            {(rubric?.criteria ?? []).map((c) => (
              <li key={c.id}>
                <strong>{c.name}</strong> — {annotations.get(c.id) ?? '—'}
              </li>
            ))}
          </ul>
        </article>
      )}

      {draft.trim() && (
        <details className="model-response">
          <summary>Your submitted draft</summary>
          <p className="passage-body">{draft}</p>
        </details>
      )}
    </section>
  )
}
