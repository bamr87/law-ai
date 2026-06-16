import KnowledgeGraph from '@/components/KnowledgeGraph'

export const metadata = {
  title: 'Knowledge Graph · LawGraph AI',
  description:
    'Interactive Cytoscape view of cases, citations, and CITES edges in the LawGraph AI knowledge graph.',
}

export default function GraphPage() {
  return <KnowledgeGraph />
}
