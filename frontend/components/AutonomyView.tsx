'use client'

/**
 * Autonomy mission-control — the deep-linkable detail view for the autonomous
 * evolve loop (constitution §11/§12). Surfaces the kill-switch state, the
 * allowed data sources, the recent-cycle history, and any policy violations.
 * Backed by /api/agents/autonomy via the shared React Query hook.
 */

import {
  Badge,
  EmptyState,
  ErrorState,
  Page,
  Panel,
  SkeletonLines,
  StatGrid,
  Table,
  type Column,
  type StatItem,
  type Tone,
} from '@/components/ui'
import type { AutonomyCycle, AutonomyState } from '@/lib/api'
import { relativeTime } from '@/lib/format'
import { useAutonomy } from '@/lib/queries'
import { ShieldCheck, ShieldOff } from 'lucide-react'

const statusTone = (status: string | null): Tone =>
  status === 'ok' ? 'success' : status === 'error' ? 'danger' : 'neutral'

export default function AutonomyView() {
  const q = useAutonomy()
  const data = q.data ?? null

  return (
    <Page
      eyebrow="Operations"
      title="Autonomy"
      tagline={
        <>
          Governance for the autonomous evolve loop — kill-switch state, allowed
          data sources, recent cycles, and policy violations. Backed by{' '}
          <code className="text-ink">/api/agents/autonomy</code>.
        </>
      }
      links={[{ href: '/agents', label: '← Back to Agent Ops' }]}
    >
      {q.isError && (
        <ErrorState
          message={(q.error as Error)?.message ?? 'Failed to load autonomy state'}
          onRetry={() => void q.refetch()}
        />
      )}
      {q.isLoading && (
        <Panel title="Autonomy">
          <SkeletonLines rows={5} />
        </Panel>
      )}
      {data && <AutonomyDetail data={data} />}
    </Page>
  )
}

function AutonomyDetail({ data }: { data: AutonomyState }) {
  const { enabled, allowed_sources, last_cycle, recent_cycles, recent_violations } =
    data

  const stats: StatItem[] = [
    {
      label: 'Kill-switch',
      value: enabled ? 'ENABLED' : 'OFF',
      hint: enabled ? 'loop may run' : 'loop is halted',
    },
    {
      label: 'Allowed sources',
      value: allowed_sources.length,
      hint: allowed_sources.length > 0 ? allowed_sources.join(', ') : 'none',
    },
    { label: 'Recent cycles', value: recent_cycles.length, hint: 'last tracked' },
    {
      label: 'Violations',
      value: recent_violations.length,
      hint: recent_violations.length > 0 ? 'review below' : 'none recorded',
    },
  ]

  const cycleColumns: Column<AutonomyCycle>[] = [
    {
      key: 'type',
      header: 'Cycle',
      cell: (c) => <span className="font-mono">{c.cycle_type ?? 'cycle'}</span>,
    },
    {
      key: 'status',
      header: 'Status',
      cell: (c) => (
        <Badge tone={statusTone(c.status)} dot>
          {c.status ?? '—'}
        </Badge>
      ),
    },
    {
      key: 'duration',
      header: 'Duration',
      align: 'right',
      cell: (c) => (
        <span className="tabular-nums">
          {c.duration_ms != null ? `${Math.round(c.duration_ms)} ms` : '—'}
        </span>
      ),
    },
    {
      key: 'completed',
      header: 'Completed',
      align: 'right',
      cell: (c) => <span className="text-subtle">{relativeTime(new Date(c.completed_at))}</span>,
    },
    {
      key: 'id',
      header: 'Cycle ID',
      cell: (c) => <span className="font-mono text-subtle">{c.cycle_id ?? '—'}</span>,
    },
  ]

  return (
    <>
      {/* Prominent kill-switch banner */}
      <div
        className={
          'flex items-start gap-3 rounded-xl border p-4 ' +
          (enabled
            ? 'border-success/40 bg-success/10'
            : 'border-warning/40 bg-warning/10')
        }
        role={enabled ? undefined : 'status'}
      >
        {enabled ? (
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden />
        ) : (
          <ShieldOff className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden />
        )}
        <div className="min-w-0">
          <div className="font-semibold text-ink">
            {enabled ? 'Autonomy enabled' : 'Kill-switch engaged (OFF)'}
          </div>
          <p className="mt-0.5 text-sm text-muted">
            {enabled
              ? 'The autonomous evolve loop is permitted to run cycles against the allowed sources. Every cycle is audited and ends in a draft PR — never an auto-merge (§12 I1).'
              : 'The autonomous evolve loop is halted. No cycles will run until AUTONOMY_ENABLED is set and a source is allow-listed (§12 I3).'}
          </p>
        </div>
      </div>

      <StatGrid items={stats} min={150} />

      <Panel
        title="Recent cycles"
        subtitle={
          last_cycle
            ? `Last: ${last_cycle.cycle_type ?? 'cycle'} · ${last_cycle.status ?? '—'}`
            : undefined
        }
      >
        <Table
          columns={cycleColumns}
          rows={recent_cycles}
          rowKey={(c, i) => c.cycle_id ?? String(i)}
          empty="No autonomy cycles recorded yet."
        />
      </Panel>

      <Panel title="Allowed sources">
        {allowed_sources.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {allowed_sources.map((s) => (
              <Badge key={s} tone="info">
                {s}
              </Badge>
            ))}
          </div>
        ) : (
          <EmptyState message="No sources are allow-listed — the loop cannot ingest." />
        )}
      </Panel>

      <Panel
        title="Policy violations"
        subtitle="Autonomy-loop invariant breaches (§12)"
      >
        {recent_violations.length === 0 ? (
          <EmptyState message="No policy violations recorded. 🎉" />
        ) : (
          <ol className="flex flex-col gap-2">
            {recent_violations.map((v, i) => (
              <li
                key={i}
                className="rounded-lg border border-danger/30 bg-danger/5 p-3 text-xs"
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <Badge tone="danger" dot>
                    violation
                  </Badge>
                  <span className="text-subtle">
                    {relativeTime(new Date(v.timestamp))}
                  </span>
                </div>
                <pre className="max-h-40 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-muted">
                  {JSON.stringify(v.payload, null, 2)}
                </pre>
              </li>
            ))}
          </ol>
        )}
      </Panel>
    </>
  )
}
