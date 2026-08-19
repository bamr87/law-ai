import { KnowledgeGraph } from 'law-ai-ui';
import { installApiMock, ALL_ROUTES } from '../ds/preview-mocks';

// The graph explorer fetches corpus stats, the case list and a neighborhood on
// mount. The fixtures below are a real California bystander-NIED citation
// cluster, so the canvas shows a meaningful network instead of empty panels.
installApiMock(ALL_ROUTES);

/**
 * The knowledge-graph explorer: corpus counters, the searchable case list, and
 * the cytoscape neighborhood canvas for the selected authority.
 */
export function CorpusExplorer() {
  return <KnowledgeGraph />;
}
