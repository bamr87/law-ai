/**
 * Export and restore everything this site remembers about you (BL-20260702-10).
 *
 * All of it lives in `localStorage`, which is device-bound and, in private
 * browsing, thrown away without warning: a month of drilling, the articles you
 * marked read, and a 35-minute essay can all disappear because a phone was
 * replaced or a window was private. There is no account to sync to and there
 * is not going to be one — the site has no server — so the honest answer is a
 * file the reader owns.
 *
 * Three properties the format has to have:
 *
 *  - **Versioned.** `schema` is checked on the way in, so a snapshot taken
 *    today can be migrated rather than silently half-read when the attempt
 *    shape changes.
 *  - **Mergeable.** Restoring on a device that has its own history must not be
 *    a choice between the two. `merge` dedupes attempts on
 *    `(qid, ts)` — the same attempt exported twice is one attempt.
 *  - **Suspicious of its input.** The file came off a disk and may have been
 *    edited, truncated, or be something else entirely. Every field is checked
 *    before anything is written, and a bad file changes nothing at all.
 */
import type { Attempt } from './progress'
import { getAttempts, writeAttempts } from './progress'
import {
  readLibraryRead,
  writeLibraryRead,
  readWritingState,
  writeWritingState,
  type WritingState,
} from './deviceState'

/** Bumped when the shape below changes in a way an old file cannot satisfy. */
export const SNAPSHOT_SCHEMA = 1

export interface Snapshot {
  schema: number
  exported_at: string
  attempts: Attempt[]
  /** Article ids marked read in the knowledge library. */
  library_read: string[]
  /** Writing drafts and submissions, keyed by prompt id. */
  writing: WritingState
}

export type ImportMode = 'merge' | 'replace'

export class SnapshotError extends Error {}

/** Everything this device is holding, as one plain object. */
export function exportSnapshot(): Snapshot {
  return {
    schema: SNAPSHOT_SCHEMA,
    exported_at: new Date().toISOString(),
    attempts: getAttempts(),
    library_read: [...readLibraryRead()].sort(),
    writing: readWritingState(),
  }
}

/** A filename that sorts by date and says what it is. */
export function snapshotFilename(now = new Date()): string {
  return `lsat-practice-${now.toISOString().slice(0, 10)}.json`
}

function isRecordOfStrings(value: unknown): value is Record<string, string> {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    Object.values(value).every((v) => typeof v === 'string')
  )
}

function parseAttempt(value: unknown): Attempt | null {
  if (typeof value !== 'object' || value === null) return null
  const a = value as Record<string, unknown>
  if (typeof a.qid !== 'string' || !a.qid) return null
  if (typeof a.section !== 'string') return null
  if (typeof a.choice !== 'string') return null
  if (typeof a.correct !== 'boolean') return null
  if (typeof a.ts !== 'number' || !Number.isFinite(a.ts)) return null
  return {
    qid: a.qid,
    section: a.section as Attempt['section'],
    choice: a.choice,
    correct: a.correct,
    ts: a.ts,
  }
}

/**
 * Validate a snapshot without touching storage.
 *
 * Split out so the import path can reject a file before it has changed
 * anything: a half-applied restore is worse than a refused one.
 */
export function parseSnapshot(json: string): Snapshot {
  let raw: unknown
  try {
    raw = JSON.parse(json)
  } catch {
    throw new SnapshotError('That file is not JSON.')
  }
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new SnapshotError('That file is not a progress export.')
  }
  const body = raw as Record<string, unknown>
  if (body.schema !== SNAPSHOT_SCHEMA) {
    throw new SnapshotError(
      `Unsupported export version ${String(body.schema)} — this site reads version ${SNAPSHOT_SCHEMA}.`,
    )
  }
  if (!Array.isArray(body.attempts)) {
    throw new SnapshotError('That file is missing its attempt history.')
  }
  const attempts: Attempt[] = []
  for (const row of body.attempts) {
    const attempt = parseAttempt(row)
    // One bad row means the file is not what it claims to be. Importing the
    // rest would quietly lose history the reader believes they restored.
    if (!attempt) throw new SnapshotError('That file has a damaged attempt in it.')
    attempts.push(attempt)
  }
  const libraryRead = body.library_read
  if (libraryRead !== undefined && !Array.isArray(libraryRead)) {
    throw new SnapshotError('That file has a damaged reading list in it.')
  }
  const writing = (body.writing ?? {}) as Record<string, unknown>
  const drafts = writing.drafts ?? {}
  const submitted = writing.submitted ?? []
  if (!isRecordOfStrings(drafts)) {
    throw new SnapshotError('That file has damaged writing drafts in it.')
  }
  if (!Array.isArray(submitted) || submitted.some((id) => typeof id !== 'string')) {
    throw new SnapshotError('That file has damaged writing submissions in it.')
  }
  return {
    schema: SNAPSHOT_SCHEMA,
    exported_at: typeof body.exported_at === 'string' ? body.exported_at : '',
    attempts,
    library_read: (libraryRead ?? []).filter(
      (id): id is string => typeof id === 'string',
    ),
    writing: { drafts, submitted: submitted as string[] },
  }
}

/** Summary of what a restore actually changed, for the reader to see. */
export interface ImportResult {
  attempts: number
  library_read: number
  writing: number
}

/**
 * Apply a snapshot.
 *
 * `merge` adds what this device does not already have; `replace` makes the
 * device look exactly like the file. Nothing is written until the whole file
 * has parsed.
 */
export function importSnapshot(json: string, mode: ImportMode): ImportResult {
  const snapshot = parseSnapshot(json)

  const attempts =
    mode === 'replace' ? snapshot.attempts : mergeAttempts(getAttempts(), snapshot.attempts)
  writeAttempts(attempts)

  const read =
    mode === 'replace'
      ? new Set(snapshot.library_read)
      : new Set([...readLibraryRead(), ...snapshot.library_read])
  writeLibraryRead(read)

  const current = readWritingState()
  const writing: WritingState =
    mode === 'replace'
      ? snapshot.writing
      : {
          // The file wins on a conflict: it is the thing the reader just chose
          // to restore, and a draft they kept is the one they exported.
          drafts: { ...current.drafts, ...snapshot.writing.drafts },
          submitted: [
            ...new Set([...current.submitted, ...snapshot.writing.submitted]),
          ],
        }
  writeWritingState(writing, mode === 'replace')

  return {
    attempts: attempts.length,
    library_read: read.size,
    writing: Object.keys(writing.drafts).length,
  }
}

/** Union of two attempt lists, deduped on `(qid, ts)` and in time order. */
export function mergeAttempts(mine: Attempt[], theirs: Attempt[]): Attempt[] {
  const byKey = new Map<string, Attempt>()
  for (const a of [...mine, ...theirs]) byKey.set(`${a.qid}@${a.ts}`, a)
  return [...byKey.values()].sort((a, b) => a.ts - b.ts)
}
