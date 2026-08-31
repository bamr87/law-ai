import AgentDashboard from '@/components/AgentDashboard'
import PageLayout from '@/components/shell/PageLayout'

export const metadata = {
  title: 'Agent Operations · Law AI',
}

export default function AgentsPage() {
  return (
    <PageLayout
      eyebrow="Operations"
      title="Agent Operations"
      accent="blue"
      width="wide"
      description={
        <>
          Live view of registered agents, recent runs, the BACKLOG, and active
          specs. Backed by{' '}
          <code className="rounded bg-slate-800 px-1 py-0.5 font-mono text-xs">
            /api/agents/*
          </code>
          .
        </>
      }
    >
      <AgentDashboard />
    </PageLayout>
  )
}
