'use client'

import { useEffect, useRef, useState } from 'react'
import { SECTIONS, sectionMeta, writingPrompts } from '@/lib/data'
import {
  type Attempt,
  clearAttempts,
  getAttempts,
  overallAccuracy,
  sectionAccuracy,
} from '@/lib/progress'
import {
  exportSnapshot,
  importSnapshot,
  snapshotFilename,
  SnapshotError,
  type ImportMode,
} from '@/lib/backup'
import { readWritingState, type WritingState } from '@/lib/deviceState'

const NO_WRITING: WritingState = { drafts: {}, submitted: [] }

/**
 * All-time + per-section accuracy from localStorage, with a guarded reset —
 * and the way off this device (BL-20260702-10).
 *
 * `localStorage` is device-bound and thrown away without warning in private
 * browsing, and this site has no account to sync to. A file the reader owns is
 * the only honest answer: export takes everything (attempts, read marks,
 * writing drafts and submissions), and import either merges it into what is
 * here or replaces it outright.
 *
 * Argumentative Writing is reported separately from the section table, and has
 * to be (#121). `SECTIONS` is `['LR','RC','LG']` on purpose — writing has no
 * keyed questions, so `lib/data.ts` excludes `'WS'` and the backend's
 * `MCQ_SECTIONS` mirrors that — and `getAttempts()` only ever holds
 * multiple-choice answers. So a writing figure cannot come from either; it
 * comes from the same `readWritingState()` the export already reads, and is
 * rendered as its own block. There is no accuracy to report either way: the
 * whole writing loop is self-assessment against a rubric.
 */
export default function Stats() {
  const [attempts, setAttempts] = useState<Attempt[]>([])
  const [writing, setWriting] = useState<WritingState>(NO_WRITING)
  const [status, setStatus] = useState('')
  const [problem, setProblem] = useState('')
  const fileRef = useRef<HTMLInputElement | null>(null)
  const modeRef = useRef<ImportMode>('merge')

  // After mount, never during render: the static export prerenders this
  // component on the server, where `localStorage` does not exist.
  useEffect(() => {
    setAttempts(getAttempts())
    setWriting(readWritingState())
  }, [])

  function download() {
    const snapshot = exportSnapshot()
    const blob = new Blob([JSON.stringify(snapshot, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = snapshotFilename()
    link.click()
    // Revoking immediately is safe: the click has already handed the blob to
    // the download, and leaving it alive leaks the whole snapshot for the life
    // of the page.
    URL.revokeObjectURL(url)
    setProblem('')
    setStatus(
      `Exported ${snapshot.attempts.length} attempts, ` +
        `${snapshot.library_read.length} read articles and ` +
        `${Object.keys(snapshot.writing.drafts).length} drafts.`,
    )
  }

  function pickFile(mode: ImportMode) {
    if (
      mode === 'replace' &&
      !window.confirm(
        'Replace everything saved on this device with the contents of that file? This cannot be undone.',
      )
    ) {
      return
    }
    modeRef.current = mode
    fileRef.current?.click()
  }

  async function onFile(file: File | undefined) {
    if (!file) return
    setStatus('')
    setProblem('')
    try {
      const result = importSnapshot(await file.text(), modeRef.current)
      setAttempts(getAttempts())
      // A restored file carries writing state too, so the figure below has to
      // be re-read for the same reason the table is (#121).
      setWriting(readWritingState())
      setStatus(
        `Restored: ${result.attempts} attempts, ${result.library_read} read articles, ` +
          `${result.writing} drafts.`,
      )
    } catch (err) {
      // A rejected file changed nothing — say so, so the reader does not go
      // looking for half-restored history.
      setProblem(
        err instanceof SnapshotError
          ? `${err.message} Nothing on this device was changed.`
          : 'That file could not be read. Nothing on this device was changed.',
      )
    } finally {
      // Same file twice in a row must still fire a change event.
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const overall = overallAccuracy(attempts)
  const hasDrills = overall.attempted > 0

  // Counted against the prompts this bundle actually ships: a restored file
  // can carry submissions for prompts that have since left the bank, and
  // "5 of 4 prompts submitted" is worse than not saying it.
  const promptIds = new Set(writingPrompts.map((p) => p.id))
  const submittedCount = writing.submitted.filter((id) => promptIds.has(id)).length
  // A prompt that has been submitted is not also "in progress".
  const draftCount = Object.keys(writing.drafts).filter(
    (id) => promptIds.has(id) && !writing.submitted.includes(id),
  ).length
  const hasWriting = submittedCount > 0 || draftCount > 0

  function reset() {
    if (!window.confirm('Erase all saved practice history on this device? This cannot be undone.')) {
      return
    }
    clearAttempts()
    setAttempts([])
    setStatus('Practice history erased.')
    setProblem('')
  }

  // Rendered whatever the attempt count is: a reader with no attempts on THIS
  // device is exactly the reader who has a file to restore.
  const transfer = (
    <div className="stat-transfer">
      <h3>Move your progress</h3>
      <p className="drill-timing">
        Everything is stored in this browser only, so it does not follow you to
        another device and private browsing discards it. Export a file to keep
        it.
      </p>
      <div className="stat-transfer-actions">
        <button type="button" className="btn" onClick={download}>
          Export progress (JSON)
        </button>
        <button type="button" className="btn" onClick={() => pickFile('merge')}>
          Import and merge
        </button>
        <button type="button" className="btn" onClick={() => pickFile('replace')}>
          Import and replace
        </button>
      </div>
      <input
        ref={fileRef}
        type="file"
        accept="application/json,.json"
        className="sr-only"
        aria-label="Progress export file"
        onChange={(e) => void onFile(e.target.files?.[0])}
      />
      <p role="status" aria-live="polite" className="drill-timing">
        {status}
      </p>
      {problem && (
        <p role="alert" className="stat-transfer-problem">
          {problem}
        </p>
      )}
    </div>
  )

  return (
    <section aria-label="Statistics">
      <div className="drill-head">
        <h2>Your progress</h2>
        <p className="drill-timing">Stored only in this browser</p>
      </div>

      {!hasDrills && !hasWriting ? (
        <p className="empty">No attempts yet — start a drill to build your stats.</p>
      ) : (
        <>
          {hasDrills ? (
            <>
              <div className="stat-hero">
                <div className="stat-num">{overall.pct}%</div>
                <div className="stat-sub">
                  {overall.correct} / {overall.attempted} questions correct
                </div>
              </div>

              <table className="stat-table">
                <thead>
                  <tr>
                    <th scope="col">Section</th>
                    <th scope="col">Correct</th>
                    <th scope="col">Attempted</th>
                    <th scope="col">Accuracy</th>
                  </tr>
                </thead>
                <tbody>
                  {SECTIONS.map((code) => {
                    const a = sectionAccuracy(attempts, code)
                    return (
                      <tr key={code}>
                        <th scope="row">{sectionMeta(code)?.name ?? code}</th>
                        <td>{a.correct}</td>
                        <td>{a.attempted}</td>
                        <td>{a.attempted ? `${a.pct}%` : '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </>
          ) : (
            // Reached only by a writing-only learner: their work IS on this
            // screen, just below, so the blanket "no attempts yet" would be
            // the wrong thing to say.
            <p className="empty">
              No drill attempts yet — the section table fills in once you answer
              questions in LR, RC or LG.
            </p>
          )}

          {hasWriting && (
            <div className="stat-writing">
              <h3>{sectionMeta('WS')?.name ?? 'Argumentative Writing'}</h3>
              <p className="stat-writing-figure">
                <strong>{submittedCount}</strong> of {writingPrompts.length}{' '}
                {writingPrompts.length === 1 ? 'prompt' : 'prompts'} submitted
                {draftCount > 0 && (
                  <span className="stat-writing-drafts">
                    {' '}
                    · {draftCount} {draftCount === 1 ? 'draft' : 'drafts'} in
                    progress
                  </span>
                )}
              </p>
              <p className="drill-timing">
                Writing is scored against the rubric by you, not by the site, so
                there is no accuracy to report here — only whether the work is
                done.
              </p>
            </div>
          )}

          {hasDrills && (
            <button type="button" className="btn btn-danger" onClick={reset}>
              Reset progress
            </button>
          )}
        </>
      )}

      {transfer}
    </section>
  )
}
