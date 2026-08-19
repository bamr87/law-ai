import { HomeStats } from 'law-ai-ui';
import { installApiMock, ALL_ROUTES } from '../ds/preview-mocks';

// HomeStats polls /api/agents, /api/agents/backlog and /api/agents/specs on
// mount. Without a backend it renders the "Offline" state with em-dashes, so
// the mock is what makes the loaded view — the one worth designing against —
// visible. Installed at module scope: it must be in place before the effect runs.
installApiMock(ALL_ROUTES);

/**
 * The home banner once the backend has answered: connection pill plus agent,
 * backlog and spec counts, each with its own accent dot.
 */
export function Connected() {
  return <HomeStats />;
}
