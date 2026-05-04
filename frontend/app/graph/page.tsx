import KnowledgeGraph from '@/components/KnowledgeGraph'

export const metadata = {
  title: 'Knowledge Graph · LexGraph AI',
  description:
    'Interactive Cytoscape view of cases, citations, and CITES edges in the LexGraph AI knowledge graph.',
}

export default function GraphPage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-8">
      <header className="mb-8">
        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-emerald-400/80">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />
          Graph
        </div>
        <h1 className="mt-2 text-4xl font-bold tracking-tight text-slate-100">
          Knowledge Graph
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-400">
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
        </p>
      </header>
      <KnowledgeGraph />
    </main>
  )
}
