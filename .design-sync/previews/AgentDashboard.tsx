import { AgentDashboard } from 'law-ai-ui';
import { installApiMock, ALL_ROUTES } from '../ds/preview-mocks';

// Agent Ops fetches the run feed, per-agent metrics and run details on mount.
// The mock supplies a realistic window of provenance events so the card shows
// the populated console rather than its "failed to load" tiles.
installApiMock(ALL_ROUTES);

/**
 * The Agent Ops console with a live window of runs: per-agent latency and
 * confidence metrics, the recent-run feed, and the registry/backlog/spec tiles.
 */
export function OpsConsole() {
  return <AgentDashboard />;
}
