import { NavBar } from 'law-ai-ui';

// NavBar highlights the current route via usePathname(). Outside a Next.js
// runtime the DS ships a shim that reads window.__LAWAI_PATHNAME, so a preview
// can choose which item renders active. Set at module scope, before mount.
window.__LAWAI_PATHNAME = '/analysis';

/**
 * The platform's top navigation on the Analysis Studio route — brand mark, the
 * five section links with the active item ringed, the backend status pill, and
 * the mobile menu trigger that appears below `md`.
 */
export function AnalysisRouteActive() {
  return <NavBar />;
}
