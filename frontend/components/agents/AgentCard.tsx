'use client'

import type { AgentInfo } from '@/lib/api'

// ---------------------------------------------------------------------------
// AgentCard — enhanced registry card with launch button
// ---------------------------------------------------------------------------

export const AGENT_DESCRIPTIONS: Record<string, string> = {
  LegalAnalyst: 'IRAC-style analysis of legal issues with precedent retrieval.',
  PrecedentHunter: 'Searches the knowledge graph for relevant case precedents.',
  IngestionScout:
    'Discovers and queues new legal opinions from public sources.',
}

export function AgentCard({
  agent,
  onLaunch,
}: {
  agent: AgentInfo
  onLaunch: () => void
}) {
  const desc = AGENT_DESCRIPTIONS[agent.name] ?? 'Agent ready.'
  return (
    <li
      className="group rounded-lg border border-slate-800 bg-slate-900/40 p-3 transition hover:border-blue-500/40 hover:bg-slate-900/80"
      data-testid="registry-card"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-emerald-400" />
          <span className="font-medium text-slate-100">{agent.name}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-slate-400">
            ready
          </span>
          {(agent.name === 'LegalAnalyst' ||
            agent.name === 'PrecedentHunter') && (
            <button
              type="button"
              onClick={onLaunch}
              className="rounded border border-blue-600/40 bg-blue-600/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-blue-300 transition hover:border-blue-500 hover:bg-blue-600/20"
            >
              Run
            </button>
          )}
        </div>
      </div>
      <div className="mt-1 text-xs text-slate-400">{desc}</div>
      <div className="mt-1 truncate font-mono text-[10px] text-slate-600">
        {agent.module}
      </div>
    </li>
  )
}

export default AgentCard
