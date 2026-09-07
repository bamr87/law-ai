/**
 * SolveAssist on the platform (spec 041 T-008/T-012, AC-4).
 *
 * The reveal discipline itself — one step per hint, no re-reveal when walking
 * back, the spoiler lock, the dots — is the shared contract this product runs
 * against the published static site's copy (BL-20260831-22). What is left here
 * is what only the platform does: the AI-tutor fallback for a question with no
 * guide, the `hints_used` count the lab reports, and the diagrams the API
 * returns inside a slide.
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SolveAssist, {
  resetSolveAssistSession,
} from '@/components/lsat/SolveAssist'
import { http, HttpResponse } from 'msw'

import {
  lsatGuideFixture,
  lsatHintReveals,
  resetLsatHintReveals,
  server,
} from '@/mocks/server'
import { describeSolveAssistContract } from '../../contracts/solveAssist.contract'

describeSolveAssistContract({
  product: 'platform',
  steps: lsatGuideFixture.steps.map((s) => ({ title: s.title, text: s.text })),
  reset: resetSolveAssistSession,
  // The locked step's text never reached the browser, so unlocking it is a
  // refetch behind an explicit affordance.
  unlockNeedsButton: true,
  mount(graded) {
    cleanup()
    const view = render(<SolveAssist questionId="lg-001" graded={graded} />)
    return {
      setGraded: (next) =>
        view.rerender(<SolveAssist questionId="lg-001" graded={next} />),
    }
  },
})

describe('SolveAssist (platform only)', () => {
  beforeEach(() => {
    resetSolveAssistSession()
    resetLsatHintReveals()
  })

  // BL-20260830-13: only grade-time `hints_used` was recorded, so a one-hint
  // nudge and a five-hint walkthrough looked identical and hints on a question
  // that was never submitted left no trace at all.
  describe('per-reveal audit events', () => {
    it('reports each reveal, with its running depth', async () => {
      render(<SolveAssist questionId="lg-001" graded={false} />)
      fireEvent.click(screen.getByRole('button', { name: /hint/i }))
      await waitFor(() => expect(lsatHintReveals).toHaveLength(1))
      expect(lsatHintReveals[0]).toMatchObject({
        questionId: 'lg-001',
        step_index: 0,
        revealed_count: 1,
        spoiler: false,
      })

      fireEvent.click(screen.getByRole('button', { name: /next hint/i }))
      await waitFor(() => expect(lsatHintReveals).toHaveLength(2))
      expect(lsatHintReveals[1]).toMatchObject({ step_index: 1, revealed_count: 2 })
    })

    it('does not report walking back and forth through revealed steps', async () => {
      render(<SolveAssist questionId="lg-001" graded={false} />)
      fireEvent.click(screen.getByRole('button', { name: /hint/i }))
      await waitFor(() => expect(lsatHintReveals).toHaveLength(1))
      fireEvent.click(screen.getByRole('button', { name: /next hint/i }))
      await waitFor(() => expect(lsatHintReveals).toHaveLength(2))

      fireEvent.click(screen.getByRole('button', { name: 'Previous step' }))
      fireEvent.keyDown(document.body, { key: 'k' })
      // Re-reading a hint is not taking one.
      expect(lsatHintReveals).toHaveLength(2)
    })

    it('marks the spoiler unlock', async () => {
      const view = render(<SolveAssist questionId="lg-001" graded={false} />)
      fireEvent.click(screen.getByRole('button', { name: /hint/i }))
      await waitFor(() => expect(lsatHintReveals).toHaveLength(1))
      view.rerender(<SolveAssist questionId="lg-001" graded />)
      fireEvent.keyDown(document.body, { key: 'h' })
      fireEvent.keyDown(document.body, { key: 'h' })
      await waitFor(() =>
        expect(screen.getByText(/locked — submit an answer/i)).toBeInTheDocument(),
      )
      fireEvent.click(screen.getByRole('button', { name: /Show final step/ }))
      await waitFor(() =>
        expect(lsatHintReveals.some((r) => r.spoiler)).toBe(true),
      )
    })

    it('keeps revealing when the analytics endpoint is unreachable', async () => {
      server.use(
        http.post(
          'http://localhost:8000/api/lsat/questions/:questionId/hint',
          () => HttpResponse.error(),
        ),
      )
      render(<SolveAssist questionId="lg-001" graded={false} />)
      fireEvent.click(screen.getByRole('button', { name: /hint/i }))
      expect(
        await screen.findByText(lsatGuideFixture.steps[0].text!),
      ).toBeInTheDocument()
    })
  })

  it('reports hints used, not counting locked stubs', async () => {
    const onHintsUsedChange = vi.fn()
    render(
      <SolveAssist
        questionId="lg-001"
        graded={false}
        onHintsUsedChange={onHintsUsedChange}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /hint/i }))
    await waitFor(() => expect(onHintsUsedChange).toHaveBeenLastCalledWith(1))
    fireEvent.click(screen.getByRole('button', { name: /next hint/i }))
    await waitFor(() => expect(onHintsUsedChange).toHaveBeenLastCalledWith(2))
    // The third (locked) slide is not help.
    fireEvent.click(screen.getByRole('button', { name: /next hint/i }))
    await waitFor(() =>
      expect(screen.getByText(/locked — submit an answer/i)).toBeInTheDocument(),
    )
    expect(onHintsUsedChange).toHaveBeenLastCalledWith(2)
  })

  it('offers the AI tutor when the question has no guide', async () => {
    const onAskTutor = vi.fn()
    render(
      <SolveAssist questionId="lr-042" graded={false} onAskTutor={onAskTutor} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /hint/i }))
    const cta = await screen.findByRole('button', {
      name: /ask the ai tutor for a walkthrough/i,
    })
    fireEvent.click(cta)
    expect(onAskTutor).toHaveBeenCalledTimes(1)
  })

  it('renders diagram representations inside the active slide', async () => {
    render(<SolveAssist questionId="lg-001" graded={false} />)
    fireEvent.click(screen.getByRole('button', { name: /hint/i }))
    const board = await screen.findByRole('img')
    expect(board.getAttribute('aria-label')).toContain('Slot 4: J')
  })

  // BL-20260901-06: the static site's hint keys, ported. Until this the
  // carousel was mouse- or Tab-only on the platform while `lsat-static`
  // advertised H/J/K/R for the same widget.
  describe('hint keys', () => {
    const [first, second] = lsatGuideFixture.steps

    it('opens the guide with H and walks it forward', async () => {
      render(<SolveAssist questionId="lg-001" graded={false} />)
      fireEvent.keyDown(document.body, { key: 'h' })
      expect(await screen.findByText(first.text!)).toBeInTheDocument()
      fireEvent.keyDown(document.body, { key: 'h' })
      expect(await screen.findByText(second.text!)).toBeInTheDocument()
    })

    it('moves back with J and forward again with K, revealing nothing new', async () => {
      const onHintsUsedChange = vi.fn()
      render(
        <SolveAssist
          questionId="lg-001"
          graded={false}
          onHintsUsedChange={onHintsUsedChange}
        />,
      )
      fireEvent.keyDown(document.body, { key: 'h' })
      await screen.findByText(first.text!)
      fireEvent.keyDown(document.body, { key: 'h' })
      await screen.findByText(second.text!)
      await waitFor(() => expect(onHintsUsedChange).toHaveBeenLastCalledWith(2))

      fireEvent.keyDown(document.body, { key: 'j' })
      expect(await screen.findByText(first.text!)).toBeInTheDocument()
      fireEvent.keyDown(document.body, { key: 'k' })
      expect(await screen.findByText(second.text!)).toBeInTheDocument()
      // Walking the carousel is not a reveal.
      expect(onHintsUsedChange).toHaveBeenLastCalledWith(2)
    })

    it('unlocks the final step with R only once the question is graded', async () => {
      const view = render(<SolveAssist questionId="lg-001" graded={false} />)
      // One press per step, each awaited: a reveal is a fetch, and the guard
      // that stops two in flight would swallow a burst.
      fireEvent.keyDown(document.body, { key: 'h' })
      await screen.findByText(first.text!)
      fireEvent.keyDown(document.body, { key: 'h' })
      await screen.findByText(second.text!)
      fireEvent.keyDown(document.body, { key: 'h' })
      expect(
        await screen.findByText(/locked — submit an answer/i),
      ).toBeInTheDocument()

      fireEvent.keyDown(document.body, { key: 'r' })
      expect(screen.getByText(/locked — submit an answer/i)).toBeInTheDocument()

      view.rerender(<SolveAssist questionId="lg-001" graded />)
      fireEvent.keyDown(document.body, { key: 'r' })
      await waitFor(() =>
        expect(
          screen.queryByText(/locked — submit an answer/i),
        ).not.toBeInTheDocument(),
      )
    })

    it('leaves the keys alone while the tutor input has focus', async () => {
      render(
        <>
          <input aria-label="follow-up" />
          <SolveAssist questionId="lg-001" graded={false} />
        </>,
      )
      fireEvent.keyDown(screen.getByLabelText('follow-up'), { key: 'h' })
      await waitFor(() =>
        expect(screen.queryByText(first.text!)).not.toBeInTheDocument(),
      )
    })
  })
})
