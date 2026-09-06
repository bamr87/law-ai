/**
 * Progress export and restore (BL-20260702-10).
 *
 * Everything this site remembers lives in `localStorage`, which is device-bound
 * and discarded without warning in private browsing. There is no account to
 * sync to, so a file the reader owns is the only way off a device — and a
 * backup format is only worth having if it round-trips exactly, merges without
 * duplicating, and refuses a damaged file without half-applying it.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  exportSnapshot,
  importSnapshot,
  mergeAttempts,
  parseSnapshot,
  snapshotFilename,
  SNAPSHOT_SCHEMA,
  SnapshotError,
  type Snapshot,
} from '@/lib/backup'
import { getAttempts, recordAttempt } from '@/lib/progress'
import {
  readLibraryRead,
  readWritingState,
  writeLibraryRead,
  writeWritingState,
} from '@/lib/deviceState'
import type { Attempt } from '@/lib/progress'

function attempt(qid: string, ts: number, correct = true): Attempt {
  return { qid, section: 'LR', choice: 'C', correct, ts }
}

/** A device with one attempt, one read article, one draft and one submission. */
function seed(): void {
  recordAttempt(attempt('lr-001', 1_000))
  writeLibraryRead(new Set(['lib-orientation']))
  writeWritingState({
    drafts: { 'ws-001': 'A first pass.' },
    submitted: ['ws-001'],
  })
}

describe('exportSnapshot', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('takes everything the site remembers, not just the attempts', () => {
    seed()
    const snapshot = exportSnapshot()
    expect(snapshot.schema).toBe(SNAPSHOT_SCHEMA)
    expect(snapshot.attempts).toEqual([attempt('lr-001', 1_000)])
    expect(snapshot.library_read).toEqual(['lib-orientation'])
    expect(snapshot.writing).toEqual({
      drafts: { 'ws-001': 'A first pass.' },
      submitted: ['ws-001'],
    })
    expect(Date.parse(snapshot.exported_at)).not.toBeNaN()
  })

  it('exports an empty device without complaint', () => {
    const snapshot = exportSnapshot()
    expect(snapshot.attempts).toEqual([])
    expect(snapshot.library_read).toEqual([])
    expect(snapshot.writing).toEqual({ drafts: {}, submitted: [] })
  })

  it('names the file by the day it was taken', () => {
    expect(snapshotFilename(new Date('2026-09-05T11:00:00Z'))).toBe(
      'lsat-practice-2026-09-05.json',
    )
  })
})

describe('importSnapshot', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('round-trips a device exactly', () => {
    seed()
    const file = JSON.stringify(exportSnapshot())
    window.localStorage.clear()

    importSnapshot(file, 'replace')
    expect(getAttempts()).toEqual([attempt('lr-001', 1_000)])
    expect([...readLibraryRead()]).toEqual(['lib-orientation'])
    expect(readWritingState()).toEqual({
      drafts: { 'ws-001': 'A first pass.' },
      submitted: ['ws-001'],
    })
  })

  it('merges into a device that has its own history', () => {
    seed()
    const file = JSON.stringify(exportSnapshot())
    // Meanwhile, this device did some work of its own.
    window.localStorage.clear()
    recordAttempt(attempt('lr-002', 2_000, false))
    writeLibraryRead(new Set(['lib-diagramming']))
    writeWritingState({ drafts: { 'ws-002': 'Local notes.' }, submitted: [] })

    const result = importSnapshot(file, 'merge')
    expect(getAttempts().map((a) => a.qid)).toEqual(['lr-001', 'lr-002'])
    expect([...readLibraryRead()].sort()).toEqual([
      'lib-diagramming',
      'lib-orientation',
    ])
    expect(readWritingState().drafts).toEqual({
      'ws-001': 'A first pass.',
      'ws-002': 'Local notes.',
    })
    expect(result.attempts).toBe(2)
  })

  it('does not duplicate an attempt restored twice', () => {
    seed()
    const file = JSON.stringify(exportSnapshot())
    importSnapshot(file, 'merge')
    importSnapshot(file, 'merge')
    expect(getAttempts()).toHaveLength(1)
  })

  it('replace makes the device look exactly like the file', () => {
    recordAttempt(attempt('lr-999', 9_000))
    writeLibraryRead(new Set(['lib-gone']))
    writeWritingState({ drafts: { 'ws-gone': 'Old.' }, submitted: ['ws-gone'] })

    const file: Snapshot = {
      schema: SNAPSHOT_SCHEMA,
      exported_at: '2026-09-05T00:00:00.000Z',
      attempts: [attempt('lr-001', 1_000)],
      library_read: ['lib-orientation'],
      writing: { drafts: { 'ws-001': 'Kept.' }, submitted: [] },
    }
    importSnapshot(JSON.stringify(file), 'replace')

    expect(getAttempts().map((a) => a.qid)).toEqual(['lr-001'])
    expect([...readLibraryRead()]).toEqual(['lib-orientation'])
    // The stale draft and its submitted flag are gone, not merely shadowed.
    expect(readWritingState()).toEqual({ drafts: { 'ws-001': 'Kept.' }, submitted: [] })
  })

  it('keeps the drafts and submissions that only exist on this device', () => {
    writeWritingState({ drafts: { 'ws-002': 'Mine.' }, submitted: ['ws-002'] })
    const file: Snapshot = {
      schema: SNAPSHOT_SCHEMA,
      exported_at: '',
      attempts: [],
      library_read: [],
      writing: { drafts: { 'ws-001': 'Theirs.' }, submitted: [] },
    }
    importSnapshot(JSON.stringify(file), 'merge')
    expect(readWritingState().submitted).toEqual(['ws-002'])
    expect(readWritingState().drafts).toEqual({
      'ws-001': 'Theirs.',
      'ws-002': 'Mine.',
    })
  })
})

describe('a file that is not a snapshot', () => {
  beforeEach(() => {
    window.localStorage.clear()
    seed()
  })

  const bad: [string, string][] = [
    ['not JSON at all', 'not JSON'],
    ['a JSON array', '[]'],
    ['a JSON scalar', '42'],
    ['no schema', JSON.stringify({ attempts: [] })],
    ['a newer schema', JSON.stringify({ schema: 99, attempts: [] })],
    ['no attempts', JSON.stringify({ schema: SNAPSHOT_SCHEMA })],
    [
      'a damaged attempt',
      JSON.stringify({ schema: SNAPSHOT_SCHEMA, attempts: [{ qid: 'x' }] }),
    ],
    [
      'a damaged reading list',
      JSON.stringify({ schema: SNAPSHOT_SCHEMA, attempts: [], library_read: 'nope' }),
    ],
    [
      'damaged drafts',
      JSON.stringify({
        schema: SNAPSHOT_SCHEMA,
        attempts: [],
        writing: { drafts: { 'ws-001': 7 } },
      }),
    ],
  ]

  it.each(bad)('refuses %s', (_label, json) => {
    expect(() => parseSnapshot(json)).toThrow(SnapshotError)
  })

  it('changes nothing at all when it refuses', () => {
    // A half-applied restore is worse than a refused one: the reader believes
    // they have their history back and has lost some of it.
    const before = exportSnapshot()
    expect(() =>
      importSnapshot(
        JSON.stringify({ schema: SNAPSHOT_SCHEMA, attempts: [{ qid: 'x' }] }),
        'replace',
      ),
    ).toThrow(SnapshotError)
    expect(exportSnapshot().attempts).toEqual(before.attempts)
    expect(exportSnapshot().writing).toEqual(before.writing)
  })

  it('says what is wrong in words a reader can act on', () => {
    expect(() => parseSnapshot('not JSON')).toThrow(/not JSON/)
    expect(() => parseSnapshot(JSON.stringify({ schema: 99, attempts: [] }))).toThrow(
      /Unsupported export version 99/,
    )
  })
})

describe('mergeAttempts', () => {
  it('dedupes on question and timestamp, and keeps time order', () => {
    const merged = mergeAttempts(
      [attempt('b', 2_000), attempt('a', 1_000)],
      [attempt('a', 1_000), attempt('a', 3_000)],
    )
    expect(merged.map((a) => `${a.qid}@${a.ts}`)).toEqual([
      'a@1000',
      'b@2000',
      'a@3000',
    ])
  })

  it('treats a retry of the same question as a separate attempt', () => {
    // Same question, different moment: that is a re-try, and the accuracy
    // tally scores a question by its most recent one.
    const merged = mergeAttempts([attempt('a', 1_000, false)], [attempt('a', 5_000)])
    expect(merged).toHaveLength(2)
  })
})

describe('storage that refuses to work', () => {
  it('exports an empty snapshot rather than throwing', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    try {
      expect(exportSnapshot().attempts).toEqual([])
    } finally {
      spy.mockRestore()
    }
  })
})
