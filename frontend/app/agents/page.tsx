import { Suspense } from 'react'
import AgentDashboard from '@/components/AgentDashboard'

export const metadata = {
  title: 'Agent Operations · LawGraph AI',
}

export default function AgentsPage() {
  // AgentDashboard reads ?run=/?session= via useSearchParams, which Next
  // requires to sit under a Suspense boundary.
  return (
    <Suspense>
      <AgentDashboard />
    </Suspense>
  )
}
