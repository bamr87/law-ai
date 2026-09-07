/**
 * The way progress gets off a device (BL-20260702-10).
 *
 * `lib/backup.test.ts` covers the format. This covers the affordance: that the
 * export is offered at all (including to a reader whose device is empty — the
 * one most likely to have a file to restore), that a restore updates what is
 * on screen, and that a bad file says so instead of silently doing nothing.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Stats from '@/components/Stats'
import { exportSnapshot, SNAPSHOT_SCHEMA } from '@/lib/backup'
import { recordAttempt } from '@/lib/progress'

vi.mock('@/lib/data', async () => {
  const f = await import('./fixtures')
  return { SECTIONS: ['LR'], sectionMeta: () => f.SECTION_LR }
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
