import AgentDashboard from '@/components/AgentDashboard'

export const metadata = {
  title: 'Agent Operations · LawGraph AI',
}

export default function AgentsPage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-8">
      <header className="mb-8">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-500">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-400" />
          Operations
        </div>
        <h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-100">
          Agent Operations
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-400">
          Live view of registered agents, recent runs, the BACKLOG, and active
          specs. Backed by{' '}
          <code className="rounded bg-slate-800 px-1 py-0.5 font-mono text-xs">
            /api/agents/*
          </code>
          .
        </p>
      </header>
      <AgentDashboard />
    </main>
  )
}
