/**
 * The way progress gets off a device (BL-20260702-10).
 *
 * `lib/backup.test.ts` covers the format. This covers the affordance: that the
 * export is offered at all (including to a reader whose device is empty — the
 * one most likely to have a file to restore), that a restore updates what is
 * on screen, and that a bad file says so instead of silently doing nothing.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Stats from '@/components/Stats'
import { exportSnapshot, SNAPSHOT_SCHEMA } from '@/lib/backup'
import { recordAttempt } from '@/lib/progress'
import { writingDraftKey, writingSubmittedKey } from '@/lib/deviceState'

vi.mock('@/lib/data', async () => {
  const f = await import('./fixtures')
  return {
    // Deliberately NOT the real three: the table is not what the writing
    // figure is read from, and pinning that here is what proves it.
    SECTIONS: ['LR'],
    sectionMeta: (code: string) => (code === 'WS' ? f.SECTION_WS : f.SECTION_LR),
    // Two prompts, so "1 of 2" can only have come from the writing state.
    writingPrompts: [f.PROMPT, f.PROMPT_B],
  }
})

/** Captures what the page tried to hand the reader. */
let downloads: { href: string; name: string }[] = []

function file(body: string): File {
  return new File([body], 'progress.json', { type: 'application/json' })
}

function upload(body: string): void {
  fireEvent.change(screen.getByLabelText('Progress export file'), {
    target: { files: [file(body)] },
  })
}

describe('Stats transfer', () => {
  beforeEach(() => {
    downloads = []
    window.localStorage.clear()
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: () => 'blob:snapshot',
      revokeObjectURL: () => {},
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloads.push({ href: this.href, name: this.download })
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('offers the export even when this device has no attempts', () => {
    // Precisely the reader who needs it: an empty device is where a restore
    // starts.
    render(<Stats />)
    expect(screen.getByText('No attempts yet — start a drill to build your stats.'))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Export progress (JSON)' }))
      .toBeInTheDocument()
  })

  it('hands over a dated file and says what went into it', () => {
    recordAttempt({ qid: 'lr-001', section: 'LR', choice: 'C', correct: true, ts: 1 })
    render(<Stats />)
    fireEvent.click(screen.getByRole('button', { name: 'Export progress (JSON)' }))
    expect(downloads).toHaveLength(1)
    expect(downloads[0].name).toMatch(/^lsat-practice-\d{4}-\d{2}-\d{2}\.json$/)
    expect(screen.getByRole('status')).toHaveTextContent('Exported 1 attempts')
  })

  it('restores a file and updates the numbers on screen', async () => {
    render(<Stats />)
    const snapshot = {
      schema: SNAPSHOT_SCHEMA,
      exported_at: '2026-09-05T00:00:00.000Z',
      attempts: [
        { qid: 'lr-001', section: 'LR', choice: 'C', correct: true, ts: 1 },
        { qid: 'lr-002', section: 'LR', choice: 'A', correct: false, ts: 2 },
      ],
      library_read: ['lib-orientation'],
      writing: { drafts: {}, submitted: [] },
    }
    fireEvent.click(screen.getByRole('button', { name: 'Import and merge' }))
    upload(JSON.stringify(snapshot))

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('Restored: 2 attempts'),
    )
    // The table is rebuilt from the restored history, not left stale — the
    // hero and the LR row both read 50%.
    expect(screen.getByText('1 / 2 questions correct')).toBeInTheDocument()
    expect(screen.getAllByText('50%')).toHaveLength(2)
  })

  it('asks before replacing, and does nothing if the answer is no', () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const clicked = vi.spyOn(HTMLInputElement.prototype, 'click')
    render(<Stats />)
    fireEvent.click(screen.getByRole('button', { name: 'Import and replace' }))
    expect(confirm).toHaveBeenCalledOnce()
    expect(clicked).not.toHaveBeenCalled()
  })

  it('refuses a damaged file, and says nothing was changed', async () => {
    recordAttempt({ qid: 'lr-001', section: 'LR', choice: 'C', correct: true, ts: 1 })
    render(<Stats />)
    const before = exportSnapshot()

    fireEvent.click(screen.getByRole('button', { name: 'Import and merge' }))
    upload('{ not json')

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Nothing on this device was changed.')
    expect(exportSnapshot().attempts).toEqual(before.attempts)
    // And the stats on screen are the ones this device already had.
    expect(screen.getByText('1 / 1 questions correct')).toBeInTheDocument()
  })
})

/**
 * Argumentative Writing on the progress screen (#121).
 *
 * Writing is the one section a learner can practise on the published site
 * that produced no trace here at all: `Stats` rendered `SECTIONS` (LR/RC/LG
 * by design — writing has no keyed questions) over `getAttempts()`
 * (multiple-choice only), and never imported `@/lib/deviceState`. A
 * 35-minute essay left the screen unchanged, and a learner who had practised
 * ONLY writing was told "No attempts yet".
 *
 * The figure is read from `readWritingState()`, the same call `exportSnapshot`
 * already makes — so these cases set the storage keys `Writing.tsx` writes
 * rather than mocking the reader, and none of them depends on the `SECTIONS`
 * stub above.
 */
describe('Stats writing figure', () => {
  const FIRST = 'ws-fixture-01'
  const SECOND = 'ws-fixture-02'

  beforeEach(() => {
    window.localStorage.clear()
  })

  /** What `Writing.tsx:112` writes on submit. */
  function submit(id: string): void {
    window.localStorage.setItem(writingSubmittedKey(id), '1')
  }

  function draft(id: string, text = 'A first pass at the argument.'): void {
    window.localStorage.setItem(writingDraftKey(id), text)
  }

  function figure(): HTMLElement {
    return screen.getByText(/prompts? submitted/)
  }

  it('reports a submitted prompt, outside the section table', () => {
    submit(FIRST)
    recordAttempt({ qid: 'lr-001', section: 'LR', choice: 'C', correct: true, ts: 1 })
    render(<Stats />)

    expect(figure()).toHaveTextContent('1 of 2 prompts submitted')
    expect(screen.getByRole('heading', { name: 'Argumentative Writing' }))
      .toBeInTheDocument()

    // Not a row of `SECTIONS.map()`: the table's columns are correct /
    // attempted / accuracy, and writing has none of them.
    expect(
      within(screen.getByRole('table')).queryByText(/Argumentative Writing/),
    ).toBeNull()
  })

  it('shows a writing-only learner their work instead of the drill empty state', () => {
    submit(FIRST)
    render(<Stats />)

    expect(
      screen.queryByText('No attempts yet — start a drill to build your stats.'),
    ).toBeNull()
    expect(figure()).toHaveTextContent('1 of 2 prompts submitted')
    // They still have not drilled, and the screen still says so — it just no
    // longer claims nothing has happened.
    expect(screen.getByText(/No drill attempts yet/)).toBeInTheDocument()
  })

  it('counts a draft in progress, but never a submitted one twice', () => {
    submit(FIRST)
    draft(FIRST) // the draft that was submitted — already counted above
    draft(SECOND) // genuinely still in progress
    render(<Stats />)

    expect(figure()).toHaveTextContent(
      '1 of 2 prompts submitted · 1 draft in progress',
    )
  })

  it('stays silent, and keeps the old empty state, when nothing has been written', () => {
    render(<Stats />)
    expect(screen.queryByText(/prompts? submitted/)).toBeNull()
    expect(
      screen.getByText('No attempts yet — start a drill to build your stats.'),
    ).toBeInTheDocument()
  })

  it('updates on an import and merge, without a reload', async () => {
    render(<Stats />)
    expect(screen.queryByText(/prompts? submitted/)).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Import and merge' }))
    upload(
      JSON.stringify({
        schema: SNAPSHOT_SCHEMA,
        exported_at: '2026-09-17T00:00:00.000Z',
        attempts: [],
        library_read: [],
        writing: { drafts: { [SECOND]: 'Half an essay.' }, submitted: [FIRST] },
      }),
    )

    await waitFor(() =>
      expect(figure()).toHaveTextContent(
        '1 of 2 prompts submitted · 1 draft in progress',
      ),
    )
  })
})
