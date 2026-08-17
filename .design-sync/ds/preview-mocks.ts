// Preview-only API mocks.
//
// The frontend/ screens are page-level components that fetch their own data on
// mount through `frontend/lib/api.ts`, which funnels every call through one
// `fetch(`${API_BASE}${path}`)` wrapper. With no backend running, the cards
// render their error/offline states — honest, but useless as design reference.
//
// `installApiMock` swaps in a `fetch` that answers by path prefix, so a preview
// can show the screen as it looks with real data. Call it at MODULE scope in
// the preview: module bodies run before React mounts, so the component's
// effects see the mock.
//
// Fixture values mirror the real response shapes in frontend/lib/api.ts.
// Nothing here ships to designs — preview files are never part of the bundle.

type Json = unknown;
export type Routes = Record<string, Json | ((url: URL) => Json)>;

/**
 * Install a path-prefix-matching `fetch`. Longer prefixes are tried first, so
 * `/api/agents/backlog` wins over `/api/agents`. Unmatched paths 404 rather
 * than hitting the network.
 */
export function installApiMock(routes: Routes): void {
  const entries = Object.entries(routes).sort((a, b) => b[0].length - a[0].length);
  const json = (body: Json, status = 200) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    });

  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const raw =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.href
          : (input as Request).url;
    const url = new URL(raw, 'http://localhost:8000');
    for (const [prefix, value] of entries) {
      if (url.pathname === prefix || url.pathname.startsWith(prefix + '/') || url.pathname.startsWith(prefix + '?')) {
        return json(typeof value === 'function' ? (value as (u: URL) => Json)(url) : value);
      }
    }
    return json({ detail: `no preview fixture for ${url.pathname}` }, 404);
  }) as typeof fetch;
}

// ── fixtures ────────────────────────────────────────────────────────────────

export const AGENTS = {
  count: 6,
  agents: [
    { name: 'LegalAnalyst', module: 'law_ai.agents_runtime.crews.legal_analyst' },
    { name: 'PrecedentHunter', module: 'law_ai.agents_runtime.crews.precedent_hunter' },
    { name: 'CitationResolver', module: 'law_ai.agents_runtime.crews.citation_resolver' },
    { name: 'LsatTutor', module: 'law_ai.agents_runtime.crews.lsat_tutor' },
    { name: 'LsatAuthor', module: 'law_ai.agents_runtime.crews.lsat_author' },
    { name: 'IngestionTriage', module: 'law_ai.ingestionapp.agents.triage' },
  ],
};

export const BACKLOG = {
  counts: { open: 34, claimed: 5, done: 212, total: 251 },
  open: [
    { id: 'BL-20260812-03', kind: 'feature', severity: 'high', title: 'Jurisdiction filter on GraphRAG retrieval' },
    { id: 'BL-20260812-07', kind: 'bug', severity: 'medium', title: 'Citation resolver drops parallel reporter cites' },
    { id: 'BL-20260814-01', kind: 'chore', severity: 'low', title: 'Pin LegalBench harness to Ollama in CI' },
    { id: 'BL-20260815-02', kind: 'feature', severity: 'medium', title: 'Provenance export for audit review' },
  ],
  claimed: [
    { id: 'BL-20260811-04', kind: 'feature', severity: 'high', title: 'HITL approval gate for high-stakes analysis' },
  ],
  done: [
    { id: 'BL-20260810-07', kind: 'bug', severity: 'high', title: 'UPL disclaimer missing from analysis output' },
  ],
};

export const SPECS = {
  count: 38,
  specs: [
    { id: '006-knowledge-graph', status: 'shipped' },
    { id: '007-analysis-studio', status: 'shipped' },
    { id: '008-agent-api', status: 'shipped' },
    { id: '025-lsat-static-site', status: 'shipped' },
    { id: '031-provenance-export', status: 'in-progress' },
    { id: '032-jurisdiction-filter', status: 'draft' },
  ],
};

export const RUNS = {
  count: 5,
  runs: [
    { trace_id: 'tr-9f2a41', timestamp: '2026-08-17T09:14:22Z', agent: 'LegalAnalyst', type: 'llm_call', model: 'claude-opus-4', latency_ms: 4120, confidence: 0.87, sources_count: 7 },
    { trace_id: 'tr-9f2a3d', timestamp: '2026-08-17T09:11:05Z', agent: 'PrecedentHunter', type: 'retrieval', model: 'claude-opus-4', latency_ms: 1880, confidence: 0.79, sources_count: 24 },
    { trace_id: 'tr-9f29c8', timestamp: '2026-08-17T08:58:40Z', agent: 'CitationResolver', type: 'tool_use', model: 'llama3.1:8b', latency_ms: 640, confidence: 0.94, sources_count: 12 },
    { trace_id: 'tr-9f2988', timestamp: '2026-08-17T08:41:17Z', agent: 'LsatTutor', type: 'llm_call', model: 'claude-opus-4', latency_ms: 2310, confidence: 0.91, sources_count: 3 },
    { trace_id: 'tr-9f2911', timestamp: '2026-08-17T08:22:03Z', agent: 'LegalAnalyst', type: 'llm_call', model: 'claude-opus-4', latency_ms: 5230, confidence: 0.42, sources_count: 2 },
  ],
};

export const METRICS = {
  window_size: 500,
  errors_total: 3,
  agents: [
    { agent: 'LegalAnalyst', count: 184, error_count: 2, latency_p50_ms: 3980, latency_p95_ms: 7420, avg_confidence: 0.81, success_rate: 0.989, last_seen: '2026-08-17T09:14:22Z', last_trace_id: 'tr-9f2a41', last_model: 'claude-opus-4' },
    { agent: 'PrecedentHunter', count: 143, error_count: 1, latency_p50_ms: 1760, latency_p95_ms: 3110, avg_confidence: 0.77, success_rate: 0.993, last_seen: '2026-08-17T09:11:05Z', last_trace_id: 'tr-9f2a3d', last_model: 'claude-opus-4' },
    { agent: 'CitationResolver', count: 121, error_count: 0, latency_p50_ms: 610, latency_p95_ms: 980, avg_confidence: 0.93, success_rate: 1, last_seen: '2026-08-17T08:58:40Z', last_trace_id: 'tr-9f29c8', last_model: 'llama3.1:8b' },
    { agent: 'LsatTutor', count: 52, error_count: 0, latency_p50_ms: 2240, latency_p95_ms: 3860, avg_confidence: 0.9, success_rate: 1, last_seen: '2026-08-17T08:41:17Z', last_trace_id: 'tr-9f2988', last_model: 'claude-opus-4' },
  ],
};

// Shape must match LocalAIHealth in frontend/lib/api.ts exactly: the health
// panel dereferences health.ollama / .checkpointer / .phoenix unguarded, so a
// wrong-but-200 fixture crashes the whole dashboard (a failed fetch is caught
// and merely hides the panel — a bad shape is worse than no mock).
export const LOCAL_AI_HEALTH = {
  llm_chain: [
    { provider: 'claude-oauth', position: 1, configured: true, reachable: true, model: 'claude-opus-4' },
    { provider: 'claude-api-key', position: 2, configured: false, reason: 'ANTHROPIC_API_KEY not set' },
    { provider: 'ollama', position: 3, configured: true, reachable: true, model: 'llama3.1:8b' },
  ],
  ollama: { reachable: true, models: ['llama3.1:8b', 'nomic-embed-text', 'qwen2.5:14b'] },
  checkpointer: { kind: 'postgres', reachable: true },
  phoenix: { reachable: true, ui_url: 'http://localhost:6006', enabled: true },
};

export const GRAPH_STATS = { available: true, cases: 1_284, citations: 9_517, cites_edges: 6_233 };

export const GRAPH_CASES = {
  available: true,
  count: 5,
  cases: [
    { id: 'us-1803-marbury', title: 'Marbury v. Madison', court: 'U.S. Supreme Court', decided_at: '1803-02-24' },
    { id: 'ny-1928-palsgraf', title: 'Palsgraf v. Long Island R.R. Co.', court: 'N.Y. Court of Appeals', decided_at: '1928-05-29' },
    { id: 'cal-1968-dillon', title: 'Dillon v. Legg', court: 'California Supreme Court', decided_at: '1968-06-21' },
    { id: 'cal-1989-thing', title: 'Thing v. La Chusa', court: 'California Supreme Court', decided_at: '1989-04-27' },
    { id: 'cal-1968-rowland', title: 'Rowland v. Christian', court: 'California Supreme Court', decided_at: '1968-08-08' },
  ],
};

export const GRAPH_NEIGHBORHOOD = {
  available: true,
  nodes: [
    { data: { id: 'cal-1968-dillon', label: 'Dillon v. Legg', type: 'Case', court: 'Cal. Sup. Ct.' } },
    { data: { id: 'ny-1928-palsgraf', label: 'Palsgraf v. Long Island R.R.', type: 'Case', court: 'N.Y. Ct. App.' } },
    { data: { id: 'cal-1989-thing', label: 'Thing v. La Chusa', type: 'Case', court: 'Cal. Sup. Ct.' } },
    { data: { id: 'cal-1968-rowland', label: 'Rowland v. Christian', type: 'Case', court: 'Cal. Sup. Ct.' } },
    { data: { id: 'cite-68-cal2d-728', label: '68 Cal.2d 728', type: 'Citation' } },
    { data: { id: 'cite-48-cal3d-644', label: '48 Cal.3d 644', type: 'Citation' } },
  ],
  edges: [
    { data: { id: 'e1', source: 'cal-1968-dillon', target: 'ny-1928-palsgraf', type: 'CITES' } },
    { data: { id: 'e2', source: 'cal-1989-thing', target: 'cal-1968-dillon', type: 'CITES' } },
    { data: { id: 'e3', source: 'cal-1968-rowland', target: 'ny-1928-palsgraf', type: 'CITES' } },
    { data: { id: 'e4', source: 'cal-1968-dillon', target: 'cite-68-cal2d-728', type: 'HAS_CITATION' } },
    { data: { id: 'e5', source: 'cal-1989-thing', target: 'cite-48-cal3d-644', type: 'HAS_CITATION' } },
  ],
};

export const ANALYSIS_RESPONSE = {
  id: 'an-4c81d0',
  timestamp: '2026-08-17T09:14:26Z',
  latency_ms: 6420,
  confidence: 0.84,
  requires_human_review: false,
  irac: {
    issue:
      'Whether a bystander who witnesses a negligently-caused injury to a close relative may recover for negligent infliction of emotional distress under California law.',
    rule:
      'Under Thing v. La Chusa (1989) 48 Cal.3d 644, a bystander may recover only if they (1) are closely related to the victim, (2) are present at the scene and then aware that it is causing injury, and (3) suffer serious emotional distress beyond that of a disinterested witness.',
    application:
      'The claimant is the victim’s mother, satisfying the close-relative element. She arrived after the collision but before the victim was moved, and the record is unclear whether she contemporaneously perceived the injury-producing event — the second Thing element is therefore contested. Dillon v. Legg’s more flexible foreseeability approach was expressly narrowed by Thing, so the earlier standard does not control.',
    conclusion:
      'Recovery is available only if the claimant can establish contemporaneous awareness of the injury-producing event. On the current record this element is unresolved and should be developed before filing.',
    sources: [
      { title: 'Thing v. La Chusa, 48 Cal.3d 644 (1989)', url: 'https://law.justia.com/cases/california/supreme-court/3d/48/644.html', verified: true, resolved_case_id: 'cal-1989-thing' },
      { title: 'Dillon v. Legg, 68 Cal.2d 728 (1968)', url: 'https://law.justia.com/cases/california/supreme-court/2d/68/728.html', verified: true, resolved_case_id: 'cal-1968-dillon' },
      { title: 'Burgess v. Superior Court, 2 Cal.4th 1064 (1992)', url: '', verified: false, resolved_case_id: null },
    ],
  },
  precedents: {
    summary: 'Three controlling California authorities on bystander NIED, in narrowing order.',
    confidence: 0.84,
    trace_id: 'tr-9f2a3d',
    precedents: [
      { case_id: 'cal-1989-thing', title: 'Thing v. La Chusa', court: 'California Supreme Court', year: 1989, relevance_score: 0.96, distinguishing_factors: ['Sets the current three-element test', 'Expressly narrows Dillon'], url: 'https://law.justia.com/cases/california/supreme-court/3d/48/644.html' },
      { case_id: 'cal-1968-dillon', title: 'Dillon v. Legg', court: 'California Supreme Court', year: 1968, relevance_score: 0.88, distinguishing_factors: ['Foreseeability-based, later narrowed'], url: 'https://law.justia.com/cases/california/supreme-court/2d/68/728.html' },
      { case_id: 'ny-1928-palsgraf', title: 'Palsgraf v. Long Island R.R. Co.', court: 'N.Y. Court of Appeals', year: 1928, relevance_score: 0.61, distinguishing_factors: ['Out-of-jurisdiction', 'Duty/foreseeability framing only'], url: 'https://law.justia.com/cases/new-york/court-of-appeals/1928/248-n-y-339-0.html' },
    ],
  },
  agent_trace: [
    { agent: 'PrecedentHunter', trace_id: 'tr-9f2a3d', latency_ms: 1880, confidence: 0.79 },
    { agent: 'CitationResolver', trace_id: 'tr-9f29c8', latency_ms: 640, confidence: 0.94 },
    { agent: 'LegalAnalyst', trace_id: 'tr-9f2a41', latency_ms: 3900, confidence: 0.87 },
  ],
  retrieval: {
    queries: ['bystander emotional distress California', 'Thing v. La Chusa elements'],
    result_count: 24,
    lexical_count: 18,
    expanded_count: 6,
    jurisdiction_requested: 'CA',
    jurisdictions_present: ['CA', 'NY'],
    jurisdiction_absent: false,
    coverage_note: 'Corpus covers CA appellate and above from 1950; earlier authority may be missing.',
  },
};

export const LSAT_SECTIONS = {
  count: 3,
  sections: [
    {
      code: 'LR', name: 'Logical Reasoning', question_count: 70,
      description: 'Two scored sections on the LSAT (~24-26 questions each, 35 minutes per section). Each question presents a short argument or set of facts followed by a single multiple-choice prompt.',
      format: '~25 standalone short-passage questions; 5 answer choices labeled A-E.',
      timing: '35 minutes per section (~1:25 per question).',
      scoring: 'Roughly half the scored items on the exam.',
      skills: ['Identify conclusions and premises', 'Spot reasoning flaws', 'Evaluate assumptions'],
      tips: ['Read the question stem first', 'Predict the answer before reading choices'],
      concepts: ['alternative-cause', 'necessary-vs-sufficient'], references: [],
    },
    {
      code: 'RC', name: 'Reading Comprehension', question_count: 37,
      description: 'One scored section: four passages (one is typically a comparative pair) drawn from law, humanities, social sciences, and natural sciences, followed by 5-8 questions each.',
      format: '~27 questions across 4 passage sets; 5 answer choices A-E.',
      timing: '35 minutes total (~8:30 per passage set).',
      scoring: 'About a quarter of the scored items.',
      skills: ['Structural mapping', 'Distinguish claim from report'],
      tips: ['Map paragraph function before answering'],
      concepts: ['main-point', 'authors-attitude'], references: [],
    },
    {
      code: 'LG', name: 'Analytical Reasoning (Logic Games)', question_count: 19,
      description: 'Historically four games per scored section (sequencing, grouping, matching, hybrid). LSAC announced a multi-year phase-out of the dedicated LG section beginning August 2024.',
      format: '4 games, 5-7 questions each.',
      timing: '35 minutes total (~8:45 per game).',
      scoring: 'Being phased out; diagramming skills still transfer to LR.',
      skills: ['Diagramming', 'Rule chaining'],
      tips: ['Draw the board before reading questions'],
      concepts: ['sequencing', 'elimination-grid'], references: [],
    },
  ],
};

export const LSAT_STATS = {
  attempts: 11, correct: 8, accuracy: 0.73,
  by_section: {
    LR: { attempts: 6, correct: 4, accuracy: 0.67 },
    RC: { attempts: 3, correct: 2, accuracy: 0.67 },
    LG: { attempts: 2, correct: 2, accuracy: 1 },
  },
};

export const LSAT_QUESTIONS = {
  count: 1,
  questions: [
    {
      id: 'lr-001', section: 'LR', type: 'LR', difficulty: 'easy',
      stem: 'Every senior partner at the firm has argued at least one case before the state supreme court. Maria is a senior partner at the firm. Therefore, Maria has argued at least one case before the state supreme court.\n\nThe argument above is most similar in its reasoning to which one of the following?',
      choices: [
        { label: 'A', text: 'All birds have feathers. A penguin is a bird. So a penguin has feathers.' },
        { label: 'B', text: 'Most lawyers own at least one suit. Therefore, the lawyer next door owns a suit.' },
        { label: 'C', text: 'Anyone who passed the bar studied. Tom studied, so Tom passed the bar.' },
        { label: 'D', text: 'If it rains, the picnic is canceled. The picnic was canceled, so it rained.' },
        { label: 'E', text: 'No senator is under 30. Lin is 28, so Lin might be a senator.' },
      ],
      concepts: ['universal-instantiation', 'parallel-reasoning'], references: [], passage_id: null,
    },
  ],
};

export const LSAT_CONCEPTS = {
  count: 3,
  concepts: [
    { id: 'alternative-cause', name: 'Alternative Cause', sections: ['LR'], summary: 'A confounding variable that explains the observed pattern equally well or better.', detail: 'Most LR weaken answers introduce an alternative cause. Strengthen answers usually rule one out.', examples: [], see_also: [], references: [] },
    { id: 'main-point', name: 'Main Point', sections: ['RC'], summary: 'The passage-level claim every paragraph serves.', detail: null, examples: [], see_also: [], references: [] },
    { id: 'sequencing', name: 'Sequencing', sections: ['LG'], summary: 'Ordering entities in slots subject to relative and fixed constraints.', detail: null, examples: [], see_also: [], references: [] },
  ],
};

/** Every route the frontend screens touch, wired to the fixtures above. */
export const ALL_ROUTES: Routes = {
  '/api/agents/backlog': BACKLOG,
  '/api/agents/specs': SPECS,
  '/api/agents/runs': RUNS,
  '/api/agents/metrics': METRICS,
  '/api/agents/health/local-ai': LOCAL_AI_HEALTH,
  '/api/agents': AGENTS,
  '/api/graph/stats': GRAPH_STATS,
  '/api/graph/cases': GRAPH_CASES,
  '/api/graph/neighborhood': GRAPH_NEIGHBORHOOD,
  '/api/analysis': ANALYSIS_RESPONSE,
  '/api/lsat/sections': LSAT_SECTIONS,
  '/api/lsat/stats': LSAT_STATS,
  '/api/lsat/questions': LSAT_QUESTIONS,
  '/api/lsat/concepts': LSAT_CONCEPTS,
};
