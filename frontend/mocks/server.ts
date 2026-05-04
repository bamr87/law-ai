import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'

export const handlers = [
  // Mock analysis endpoint
  http.post('http://localhost:8000/api/analysis', async ({ request }) => {
    const body = await request.json() as any
    return HttpResponse.json({
      id: 'analysis-123',
      irac: {
        issue: 'Whether the right to privacy includes...',
        rule: 'The Constitution protects zones of privacy...',
        application: 'In this case, the statute...',
        conclusion: 'The law is unconstitutional.',
      },
      sources: [
        { id: 'case:roe', title: 'Roe v. Wade, 410 U.S. 113 (1973)', url: 'https://case.law/...' },
      ],
      confidence: 0.87,
      agent_trace: ['LegalAnalyst', 'PrecedentHunter'],
    })
  }),

  // Mock graph query
  http.get('http://localhost:8000/api/graph/:caseId', ({ params }) => {
    return HttpResponse.json({
      nodes: [
        { id: params.caseId, label: 'Case', type: 'Case' },
        { id: 'doctrine:privacy', label: 'Right to Privacy', type: 'LegalConcept' },
      ],
      edges: [{ source: params.caseId, target: 'doctrine:privacy', label: 'HAS_HOLDING' }],
    })
  }),
]

export const server = setupServer(...handlers)