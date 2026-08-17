import { GraphViewer } from 'law-ai-ui';

// Node types drive the visual language: 'Case' renders as a blue circle,
// 'Citation' as an amber diamond. Edges: 'CITES' is a solid blue arrow,
// 'HAS_CITATION' a dashed grey link.
const CITATION_NETWORK = {
  nodes: [
    { data: { id: 'c1', label: 'Palsgraf v. Long Island R.R.', type: 'Case', court: 'N.Y. Ct. App.' } },
    { data: { id: 'c2', label: 'Wagon Mound (No. 1)', type: 'Case', court: 'Privy Council' } },
    { data: { id: 'c3', label: 'Dillon v. Legg', type: 'Case', court: 'Cal. Sup. Ct.' } },
    { data: { id: 'c4', label: 'Thing v. La Chusa', type: 'Case', court: 'Cal. Sup. Ct.' } },
    { data: { id: 'c5', label: 'Rowland v. Christian', type: 'Case', court: 'Cal. Sup. Ct.' } },
    { data: { id: 'r1', label: '162 N.E. 99', type: 'Citation' } },
    { data: { id: 'r2', label: '68 Cal.2d 728', type: 'Citation' } },
    { data: { id: 'r3', label: '48 Cal.3d 644', type: 'Citation' } },
  ],
  edges: [
    { data: { id: 'e1', source: 'c3', target: 'c1', type: 'CITES' } },
    { data: { id: 'e2', source: 'c3', target: 'c2', type: 'CITES' } },
    { data: { id: 'e3', source: 'c4', target: 'c3', type: 'CITES' } },
    { data: { id: 'e4', source: 'c5', target: 'c1', type: 'CITES' } },
    { data: { id: 'e5', source: 'c4', target: 'c5', type: 'CITES' } },
    { data: { id: 'e6', source: 'c1', target: 'r1', type: 'HAS_CITATION' } },
    { data: { id: 'e7', source: 'c3', target: 'r2', type: 'HAS_CITATION' } },
    { data: { id: 'e8', source: 'c4', target: 'r3', type: 'HAS_CITATION' } },
  ],
};

/** The canonical view: a citation network with both node kinds and both edge kinds. */
export function CitationNetwork() {
  return <GraphViewer elements={CITATION_NETWORK} height={420} />;
}

/**
 * The neighborhood view after a single case lookup — one focal case, the
 * authorities it cites, and its reporter citations. Keep at least five or six
 * nodes: the cose layout fits-to-viewport, so a two- or three-node graph zooms
 * in far enough to blow the labels up out of scale.
 */
export function CaseNeighborhood() {
  return (
    <GraphViewer
      height={340}
      elements={{
        nodes: [
          { data: { id: 'c1', label: 'Marbury v. Madison', type: 'Case', court: 'U.S. Sup. Ct.' } },
          { data: { id: 'c2', label: 'Cohens v. Virginia', type: 'Case', court: 'U.S. Sup. Ct.' } },
          { data: { id: 'c3', label: 'Martin v. Hunter’s Lessee', type: 'Case', court: 'U.S. Sup. Ct.' } },
          { data: { id: 'c4', label: 'Cooper v. Aaron', type: 'Case', court: 'U.S. Sup. Ct.' } },
          { data: { id: 'r1', label: '5 U.S. 137', type: 'Citation' } },
          { data: { id: 'r2', label: '19 U.S. 264', type: 'Citation' } },
          { data: { id: 'r3', label: '358 U.S. 1', type: 'Citation' } },
        ],
        edges: [
          { data: { id: 'e1', source: 'c2', target: 'c1', type: 'CITES' } },
          { data: { id: 'e2', source: 'c3', target: 'c1', type: 'CITES' } },
          { data: { id: 'e3', source: 'c4', target: 'c1', type: 'CITES' } },
          { data: { id: 'e4', source: 'c1', target: 'r1', type: 'HAS_CITATION' } },
          { data: { id: 'e5', source: 'c2', target: 'r2', type: 'HAS_CITATION' } },
          { data: { id: 'e6', source: 'c4', target: 'r3', type: 'HAS_CITATION' } },
        ],
      }}
    />
  );
}
