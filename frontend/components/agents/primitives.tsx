'use client'

/**
 * The small, shared pieces of the agent-ops dashboard: the panel frame, its
 * loading and empty states, and the pills every panel labels rows with.
 *
 * Split out of `AgentDashboard.tsx` (BL-20260830-02), which had grown to
 * ~1,600 lines and hid these behind a scroll. Behaviour is unchanged — this
 * is a move, not a rewrite.
 */

export function Panel({
  title,
  subtitle,
  loading,
  error,
  actions,
  children,
}: {
  title: string
  subtitle?: string
  loading: boolean
  error: string | null
  actions?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 shadow-sm backdrop-blur">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-100">{title}</h2>
          {subtitle && (
            <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>
          )}
        </div>
        {actions}
      </header>
      {loading && <SkeletonLines />}
      {error && (
        <p
          className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-sm text-red-300"
          role="alert"
        >
          Failed to load: {error}
        </p>
      )}
      {!loading && !error && children}
    </section>
  )
}

export function SkeletonLines() {
  return (
    <div className="space-y-2">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="h-8 animate-pulse rounded-md bg-slate-800/60 motion-reduce:animate-none"
          style={{ animationDelay: `${i * 100}ms` }}
        />
      ))}
    </div>
  )
}

export function EmptyState({ message }: { message: string }) {
  return (
    <li className="rounded-md border border-dashed border-slate-800 p-3 text-center text-xs text-slate-400">
      {message}
    </li>
  )
}

export function Pill({
  children,
  tone,
}: {
  children: React.ReactNode
  tone: 'blue' | 'amber' | 'emerald' | 'slate' | 'red'
}) {
  const tones: Record<string, string> = {
    blue: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
    amber: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    emerald: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    slate: 'bg-slate-700/40 text-slate-300 border-slate-600/40',
    red: 'bg-red-500/15 text-red-300 border-red-500/30',
  }
  return (
    <span
      className={
        'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ' +
        tones[tone]
      }
    >
      {children}
    </span>
  )
}

export function SeverityBadge({ severity }: { severity: string }) {
  const tone: 'red' | 'amber' | 'slate' =
    severity === 'high' ? 'red' : severity === 'med' ? 'amber' : 'slate'
  return <Pill tone={tone}>{severity}</Pill>
}

export function KindBadge({ kind }: { kind: string }) {
  return <Pill tone="slate">{kind}</Pill>
}

export function SpecStatusBadge({ status }: { status: string }) {
  const tone: 'blue' | 'amber' | 'emerald' | 'slate' =
    status === 'shipped'
      ? 'emerald'
      : status === 'in-progress'
        ? 'amber'
        : status === 'planned' || status === 'clarified'
          ? 'blue'
          : 'slate'
  return <Pill tone={tone}>{status}</Pill>
}

export function TypeIcon({ type }: { type: string }) {
  const map: Record<string, { color: string; glyph: string }> = {
    http_request: { color: 'bg-sky-500/20 text-sky-300', glyph: '↦' },
    agent_call: { color: 'bg-violet-500/20 text-violet-300', glyph: '⚙' },
    graph_query: { color: 'bg-emerald-500/20 text-emerald-300', glyph: '◆' },
  }
  const { color, glyph } = map[type] ?? {
    color: 'bg-slate-700 text-slate-300',
    glyph: '·',
  }
  return (
    <span
      className={
        'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-xs ' +
        color
      }
      title={type || 'event'}
    >
      {glyph}
    </span>
  )
}

export function relativeTime(d: Date): string {
  const diff = (Date.now() - d.getTime()) / 1000
  if (diff < 5) return 'just now'
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}
