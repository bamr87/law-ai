import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import StatsPanel from '@/components/lsat/StatsPanel'

describe('StatsPanel', () => {
  it('shows the session beside the all-time totals', () => {
    render(
      <StatsPanel
        session={{ attempts: 4, correct: 3, assisted: 1 }}
        stats={{ attempts: 50, correct: 30, accuracy: 0.6 }}
      />,
    )
    expect(screen.getByText('This session')).toBeInTheDocument()
    expect(screen.getByText('All-time (audit log)')).toBeInTheDocument()
    // Distinct fixtures per card, so each percentage proves which card rendered it.
    expect(screen.getByText('75% accuracy')).toBeInTheDocument()
    expect(screen.getByText('60% accuracy')).toBeInTheDocument()
    expect(screen.queryByText('By section')).not.toBeInTheDocument()
  })

  it('breaks the audit totals down by section when the API has them', () => {
    render(
      <StatsPanel
        session={{ attempts: 0, correct: 0, assisted: 0 }}
        stats={{
          attempts: 10,
          correct: 5,
          accuracy: 0.5,
          by_section: {
            LR: { attempts: 6, correct: 3, accuracy: 0.5 },
            RC: { attempts: 4, correct: 2, accuracy: 0.5 },
          },
        }}
      />,
    )
    expect(screen.getByText('By section')).toBeInTheDocument()
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('LR')).toBeInTheDocument()
    expect(screen.getByText('RC')).toBeInTheDocument()
    expect(screen.getAllByText('50%')).toHaveLength(2)
  })

  // BL-20260503-05: a signed-in learner's own history and review schedule.
  it('names the card for the learner when the stats are theirs', () => {
    render(
      <StatsPanel
        session={{ attempts: 0, correct: 0, assisted: 0 }}
        stats={{ attempts: 8, correct: 4, accuracy: 0.5, scope: 'user' }}
      />,
    )
    expect(screen.getByText('Your history')).toBeInTheDocument()
    expect(screen.queryByText('All-time (audit log)')).not.toBeInTheDocument()
  })

  it('lists due questions with a drill link into the right section', () => {
    render(
      <StatsPanel
        session={{ attempts: 0, correct: 0, assisted: 0 }}
        stats={{
          attempts: 3,
          correct: 1,
          accuracy: 0.33,
          scope: 'user',
          review_queue: [
            {
              question_id: 'lr-007',
              section: 'LR',
              concepts: ['assumption'],
              streak: 0,
              box: 0,
              attempts: 2,
              last_attempt_at: '2026-09-01T00:00:00+00:00',
              due_at: '2026-09-01T00:00:00+00:00',
              overdue_days: 4,
              reason: 'missed',
            },
            {
              question_id: 'rc-002',
              section: 'RC',
              concepts: [],
              streak: 2,
              box: 2,
              attempts: 3,
              last_attempt_at: '2026-09-02T00:00:00+00:00',
              due_at: '2026-09-04T00:00:00+00:00',
              overdue_days: 1,
              reason: 'spaced-review',
            },
          ],
        }}
      />,
    )
    expect(screen.getByText('Due for review')).toBeInTheDocument()
    expect(screen.getByText('lr-007')).toBeInTheDocument()
    expect(screen.getByText('missed last time')).toBeInTheDocument()
    expect(screen.getByText('box 2')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Drill LR' })).toHaveAttribute(
      'href',
      '/lsat?tab=LR&concept=assumption',
    )
    expect(screen.getByRole('link', { name: 'Drill RC' })).toHaveAttribute(
      'href',
      '/lsat?tab=RC',
    )
  })

  it('hides the review section entirely when nothing is due', () => {
    render(
      <StatsPanel
        session={{ attempts: 0, correct: 0, assisted: 0 }}
        stats={{ attempts: 1, correct: 1, accuracy: 1, review_queue: [] }}
      />,
    )
    expect(screen.queryByText('Due for review')).not.toBeInTheDocument()
  })

  it('renders zeros rather than crashing before stats arrive', () => {
    render(
      <StatsPanel session={{ attempts: 0, correct: 0, assisted: 0 }} stats={null} />,
    )
    expect(screen.getAllByText('0% accuracy')).toHaveLength(2)
  })

  // BL-20260903-05: reading was per-browser localStorage, so the library half
  // of the loop had nowhere to show up next to drill accuracy.
  it('shows library reading beside accuracy, per section too', () => {
    render(
      <StatsPanel
        session={{ attempts: 0, correct: 0, assisted: 0 }}
        stats={{
          attempts: 4,
          correct: 3,
          accuracy: 0.75,
          articles_read: 5,
          articles_total: 12,
          by_section: {
            LR: { attempts: 4, correct: 3, accuracy: 0.75, articles_read: 2 },
          },
        }}
      />,
    )
    expect(screen.getByText('Library')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('/ 12')).toBeInTheDocument()
    expect(screen.getByText(/articles read/)).toBeInTheDocument()
    expect(
      screen.getByRole('columnheader', { name: 'Read' }),
    ).toBeInTheDocument()
  })

  it('leaves the reading card out when the API does not report it', () => {
    render(
      <StatsPanel
        session={{ attempts: 0, correct: 0, assisted: 0 }}
        stats={{ attempts: 1, correct: 1, accuracy: 1 }}
      />,
    )
    expect(screen.queryByText('Library')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('columnheader', { name: 'Read' }),
    ).not.toBeInTheDocument()
  })

  // BL-20260831-27: evaluations were persisted from the day the evaluator
  // shipped and read back by nothing, so writing progress across attempts was
  // invisible next to drill accuracy.
  it('shows writing progress as a trend, labelled machine-derived', () => {
    render(
      <StatsPanel
        session={{ attempts: 0, correct: 0, assisted: 0 }}
        stats={{
          attempts: 0,
          correct: 0,
          accuracy: 0,
          writing: {
            attempts: 3,
            by_prompt: { 'ws-001': 2, 'ws-002': 1 },
            latest_band: 3.0,
            best_band: 3.5,
            band_trend: [2, 3.5, 3],
            degraded: 1,
            model: 'claude_code/claude-opus-5',
            prompt_version: 'lsat_writing_evaluator.v1',
          },
        }}
      />,
    )
    expect(screen.getByText('Argumentative Writing')).toBeInTheDocument()
    expect(screen.getByText('3.00')).toBeInTheDocument()
    expect(screen.getByText('3.50')).toBeInTheDocument()
    expect(
      screen.getByText(/bands are machine-derived \(claude_code\/claude-opus-5/),
    ).toBeInTheDocument()
    expect(screen.getByText(/1 from the degraded fallback/)).toBeInTheDocument()
    // The direction is the point, so every attempt is on the trend.
    const trend = screen.getByRole('list', {
      name: /Weighted band by attempt/,
    })
    expect(trend.children).toHaveLength(3)
    expect(screen.getByText(/ws-001 ×2 · ws-002 ×1/)).toBeInTheDocument()
  })

  it('renders nothing for writing until there is an evaluation', () => {
    render(
      <StatsPanel
        session={{ attempts: 0, correct: 0, assisted: 0 }}
        stats={{
          attempts: 0,
          correct: 0,
          accuracy: 0,
          writing: {
            attempts: 0,
            by_prompt: {},
            latest_band: null,
            best_band: null,
            band_trend: [],
            degraded: 0,
            model: null,
            prompt_version: null,
          },
        }}
      />,
    )
    expect(screen.queryByText('Argumentative Writing')).not.toBeInTheDocument()
  })
})

describe('question-type recognition (spec 053 FR-7)', () => {
  it('renders type/strategy accuracy, confusions and weakest types with playbook links', () => {
    render(
      <StatsPanel
        session={{ attempts: 0, correct: 0, assisted: 0 }}
        stats={{
          attempts: 0,
          correct: 0,
          accuracy: 0,
          scope: 'user',
          diagnosis: {
            attempts: 3,
            type_correct: 1,
            type_accuracy: 0.3333,
            family_correct: 3,
            family_accuracy: 1,
            strategy_attempts: 2,
            strategy_correct: 1,
            strategy_accuracy: 0.5,
            by_archetype: { 'lr-necessary-assumption': { attempts: 2, correct: 0, accuracy: 0 } },
            weakest: ['lr-necessary-assumption'],
            confusions: [{ chosen: 'lr-sufficient-assumption', actual: 'lr-necessary-assumption', count: 2 }],
          },
        }}
      />,
    )
    expect(screen.getByRole('heading', { name: /question-type recognition/i })).toBeInTheDocument()
    expect(screen.getByText(/33% · 100% right family/)).toBeInTheDocument()
    expect(screen.getByText(/“Sufficient assumption”/)).toBeInTheDocument()
    const link = screen.getAllByRole('link', { name: 'Necessary assumption' })[0]
    expect(link).toHaveAttribute('href', '/lsat/playbooks#lr-necessary-assumption')
  })

  it('renders nothing for the card when no diagnosis has been made', () => {
    render(
      <StatsPanel
        session={{ attempts: 0, correct: 0, assisted: 0 }}
        stats={{ attempts: 0, correct: 0, accuracy: 0, diagnosis: { attempts: 0, type_correct: 0, type_accuracy: 0, family_correct: 0, family_accuracy: 0, strategy_attempts: 0, strategy_correct: 0, strategy_accuracy: 0, by_archetype: {}, weakest: [], confusions: [] } }}
      />,
    )
    expect(screen.queryByRole('heading', { name: /question-type recognition/i })).not.toBeInTheDocument()
  })
})
