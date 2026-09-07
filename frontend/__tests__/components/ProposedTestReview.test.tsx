/**
 * BL-20260511-17 — the autonomy loop's review queue.
 *
 * The point of the component is that a human can see what was drafted; the
 * point of these tests is that it stays *read-only* (constitution I1/I5), so
 * the absence of any promote/un-skip control is asserted, not assumed.
 */
import ProposedTestReview from '@/components/ProposedTestReview'
import { server } from '@/mocks/server'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'

const URL = 'http://localhost:8000/api/agents/proposed-tests'

describe('ProposedTestReview', () => {
  it('lists each pending proposal with its module, path and badge', async () => {
    render(<ProposedTestReview />)
    const rows = await screen.findAllByTestId('proposed-test-row')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveTextContent(
      'law_ai_eval_scoring__autonomy.proposed.py',
    )
    expect(rows[0]).toHaveTextContent('backend/tests/autonomy/proposed/')
    expect(rows[0]).toHaveTextContent('skip-marked')
  })

  it('flags a proposal that lost its skip decorator', async () => {
    server.use(
      http.get(URL, () =>
        HttpResponse.json({
          count: 1,
          available: true,
          files: [
            {
              name: 'law_ai_core_llm__autonomy.proposed.py',
              path: 'backend/tests/autonomy/proposed/law_ai_core_llm__autonomy.proposed.py',
              module: 'law_ai_core_llm',
              size: 200,
              mtime: '2026-09-05T12:00:00Z',
              skip_marked: false,
            },
          ],
        }),
      ),
    )
    render(<ProposedTestReview />)
    expect(await screen.findByText('not skipped')).toBeInTheDocument()
  })

  it('shows the empty state when nothing is pending', async () => {
    server.use(
      http.get(URL, () =>
        HttpResponse.json({ count: 0, available: true, files: [] }),
      ),
    )
    render(<ProposedTestReview />)
    expect(
      await screen.findByText('No proposed tests pending review.'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('proposed-test-row')).toBeNull()
  })

  it('says so when the checkout has no proposals directory', async () => {
    server.use(
      http.get(URL, () =>
        HttpResponse.json({ count: 0, available: false, files: [] }),
      ),
    )
    render(<ProposedTestReview />)
    expect(
      await screen.findByText(/No proposals directory in this checkout/),
    ).toBeInTheDocument()
  })

  it('reports a failed request instead of rendering an empty queue', async () => {
    server.use(
      http.get(URL, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    render(<ProposedTestReview />)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      /Failed to load proposed tests/,
    )
  })

  it('offers no way to promote or un-skip a proposal (I1/I5)', async () => {
    const { container } = render(<ProposedTestReview />)
    await waitFor(() =>
      expect(screen.getAllByTestId('proposed-test-row')).toHaveLength(1),
    )
    expect(container.querySelectorAll('button')).toHaveLength(0)
    expect(container.querySelectorAll('form')).toHaveLength(0)
  })
})
