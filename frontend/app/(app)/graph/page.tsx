import KnowledgeGraph from '@/components/KnowledgeGraph'
import PageLayout from '@/components/shell/PageLayout'

export const metadata = {
  title: 'Knowledge Graph · Law AI',
  description:
    'Interactive Cytoscape view of cases, citations, and CITES edges in the Law AI knowledge graph.',
}

export default function GraphPage() {
  return (
    <PageLayout
      eyebrow="Graph"
      title="Knowledge Graph"
      accent="emerald"
      width="wide"
      description={
        <>
          Cases, citations, and{' '}
          <code className="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-300">
            CITES
          </code>{' '}
          edges from Neo4j. Pick a case on the left to render its 1-hop
          neighborhood. Backed by{' '}
          <code className="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-300">
            /api/graph/*
          </code>
          .
        </>
      }
    >
      <KnowledgeGraph />
    </PageLayout>
  )
}
