import AutonomyDashboard from '@/components/AutonomyDashboard'
import PageLayout from '@/components/shell/PageLayout'

export const metadata = {
  title: 'Autonomy · Law AI',
}

export default function AutonomyPage() {
  return (
    <PageLayout
      eyebrow="Operations"
      title="Autonomy"
      accent="blue"
      width="wide"
      description={
        <>
          Read-only view of what the nightly loops measured: LegalBench
          accuracy over time, the thinnest-tested modules, and the documents
          still waiting on a human. Backed by{' '}
          <code className="rounded bg-slate-800 px-1 py-0.5 font-mono text-xs">
            /api/agents/autonomy/*
          </code>
          . Nothing on this page starts a cycle or approves anything.
        </>
      }
    >
      <AutonomyDashboard />
    </PageLayout>
  )
}
