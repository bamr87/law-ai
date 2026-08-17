import { LsatLab } from 'law-ai-ui';
import { installApiMock, ALL_ROUTES } from '../ds/preview-mocks';

// The lab's tab shell is static, but its Overview tab loads the section
// roadmap from /api/lsat/sections and its header polls /api/lsat/stats.
// Without the mock the card renders a "failed to fetch" bar over an empty
// roadmap.
installApiMock(ALL_ROUTES);

/**
 * The LSAT Lab on its Overview tab: the seven-tab shell (drills, concepts,
 * stats and the HITL authoring queue) above the four-section roadmap.
 */
export function SectionRoadmap() {
  return <LsatLab />;
}
