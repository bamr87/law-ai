import { AgentTrace } from 'law-ai-ui';

const RETRIEVAL_TRACE = [
  'Parsed fact pattern into issue candidates: duty of care, foreseeability, proximate cause',
  'GraphRAG lexical retrieval over Neo4j fulltext index — 24 candidate cases',
  'Expanded 2 hops along CITES edges — 11 additional authorities surfaced',
  'Filtered to jurisdiction: California appellate and above (1968-2024)',
  'Resolved 7 citations against the graph; 1 unresolved and flagged',
  'Drafted IRAC with per-element source attribution',
];

/** The canonical trace: a full retrieval-to-IRAC run with high confidence. */
export function LegalAnalysisTrace() {
  return <AgentTrace steps={RETRIEVAL_TRACE} confidence={0.87} />;
}

/** Low confidence — the score a reviewer uses to decide the run needs a human. */
export function LowConfidence() {
  return (
    <AgentTrace
      steps={[
        'Parsed fact pattern — issue classification ambiguous between contract and quasi-contract',
        'GraphRAG retrieval returned 3 candidates below the relevance floor',
        'No controlling authority found in the requested jurisdiction',
        'Escalated to human review per HITL gate',
      ]}
      confidence={0.31}
    />
  );
}

/** Confidence omitted — the badge is dropped entirely rather than showing zero. */
export function WithoutConfidence() {
  return (
    <AgentTrace
      steps={[
        'Loaded cached analysis from provenance store',
        'Verified all 5 citations still resolve against the current graph',
        'No re-run required',
      ]}
    />
  );
}

/** A single-step trace — the shortest render the component supports. */
export function SingleStep() {
  return <AgentTrace steps={['Cache hit — returned stored IRAC unchanged']} confidence={1} />;
}
