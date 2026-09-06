/**
 * Smoke tests for the pieces split out of `AgentDashboard.tsx`
 * (BL-20260830-02). They are deliberately shallow: the dashboard's own suite
 * still covers behaviour, and these exist so a broken extraction fails in the
 * file that broke rather than somewhere downstream.
 */
import {
  EmptyState,
  KindBadge,
  Panel,
  Pill,
  SeverityBadge,
  SkeletonLines,
  SpecStatusBadge,
  TypeIcon,
  relativeTime,
} from '@/components/agents/primitives'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

describe('agents/primitives', () => {
  it('renders a panel with its title, subtitle and children', () => {
    render(
      <Panel title="Registry" subtitle="Agents" loading={false} error={null}>
        <p>body</p>
      </Panel>,
    )
    expect(screen.getByText('Registry')).toBeInTheDocument()
    expect(screen.getByText('Agents')).toBeInTheDocument()
    expect(screen.getByText('body')).toBeInTheDocument()
  })

  it('shows an error as an alert instead of the children', () => {
    render(
      <Panel title="Runs" loading={false} error="boom">
        <p>body</p>
      </Panel>,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/Failed to load/)
    expect(screen.queryByText('body')).toBeNull()
  })

  it('renders the small labels and states', () => {
    const { container } = render(
      <>
        <SkeletonLines />
        <EmptyState message="Nothing yet." />
        <Pill tone="blue">Open: 3</Pill>
        <SeverityBadge severity="high" />
        <KindBadge kind="feature" />
        <SpecStatusBadge status="shipped" />
        <TypeIcon type="agent_call" />
      </>,
    )
    expect(screen.getByText('Nothing yet.')).toBeInTheDocument()
    expect(screen.getByText('Open: 3')).toBeInTheDocument()
    expect(screen.getByText('high')).toBeInTheDocument()
    expect(screen.getByText('feature')).toBeInTheDocument()
    expect(screen.getByText('shipped')).toBeInTheDocument()
    expect(container.textContent).toBeTruthy()
  })

  it('formats relative times', () => {
    expect(relativeTime(new Date(Date.now() - 5_000))).toMatch(
      /s ago|just now/i,
    )
    expect(relativeTime(new Date(Date.now() - 120_000))).toMatch(/m ago/)
  })
})
