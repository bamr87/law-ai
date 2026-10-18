import { setupServer } from 'msw/node'
import { http, HttpResponse } from 'msw'

// --- LSAT solve-guide fixtures (spec 045) ---

/** Full guide as the backend stores it; spoiler steps stripped per request. */
export const lsatGuideFixture = {
  question_id: 'lg-001',
  method: 'Rule-by-rule elimination on an ordering game',
  version: 1,
  source: 'original (CC0)',
  steps: [
    {
      kind: 'inventory',
      title: 'Write out the elements',
      text: 'List the roster and the board: F, G, H, J, K into slots 1-5.',
      spoiler: false,
      representation: {
        rep_type: 'sequence',
        slots: ['1', '2', '3', '4', '5'],
        entities: ['F', 'G', 'H', 'J', 'K'],
        placements: { '4': 'J' },
        exclusions: { '1': ['K'] },
        note: 'J is fixed; slot 1 bars K.',
      },
    },
    {
      kind: 'symbolize',
      title: 'Symbolize each rule',
      text: 'Turn every rule into notation.',
      spoiler: false,
      representation: {
        rep_type: 'notation',
        rules: [
          { rule_text: 'F argues immediately before H.', symbols: '[F H]', note: null },
        ],
      },
    },
    {
      kind: 'answer',
      title: 'One choice survives',
      text: 'Only D remains. D is correct.',
      spoiler: true,
      representation: null,
    },
  ],
}

function publicGuideView(spoilers: boolean) {
  const steps = lsatGuideFixture.steps.map((s) =>
    s.spoiler && !spoilers
      ? { kind: s.kind, title: s.title, spoiler: true, locked: true }
      : { ...s, locked: false },
  )
  return {
    question_id: lsatGuideFixture.question_id,
    method: lsatGuideFixture.method,
    version: lsatGuideFixture.version,
    source: lsatGuideFixture.source,
    step_count: lsatGuideFixture.steps.length,
    steps,
  }
}

/**
 * Concept catalog fixture (spec 045 FR-12): note the external reference — the
 * post-grade block must resolve concepts WITHOUT ever rendering that link.
 *
 * Three concepts, not one, because the catalog is now a browsable view of the
 * library: `main-conclusion` is tagged on a fixture article (so `taught_in`
 * has something to resolve), `necessary-assumption` is not, and the pair
 * cross-reference each other through `see_also`.
 */
export const lsatConceptsFixture = {
  count: 3,
  concepts: [
    {
      id: 'modus-tollens',
      name: 'Modus tollens',
      sections: ['LR'],
      summary: 'Deny the consequent to deny the antecedent.',
      detail: null,
      examples: ['If P then Q. Not Q. Therefore not P.'],
      see_also: [],
      references: [{ title: 'SEP — Logic', url: 'https://plato.stanford.edu/' }],
    },
    {
      id: 'main-conclusion',
      name: 'Main Conclusion',
      sections: ['LR'],
      summary: 'The claim the author wants you to accept.',
      detail: 'Everything else in the stimulus is there to support it.',
      examples: ['Therefore, X.'],
      see_also: ['necessary-assumption'],
      references: [],
    },
    {
      id: 'necessary-assumption',
      name: 'Necessary Assumption',
      sections: ['LR'],
      summary: 'A premise the argument cannot survive without.',
      detail: null,
      examples: [],
      see_also: ['main-conclusion', 'retired-concept'],
      references: [],
    },
  ],
}

/**
 * Default tutor reply (BL-20260905-35), served by the handler below for every
 * suite that reaches `/api/lsat/tutor` without installing its own. A real
 * model answered it — `used_llm` true, a named model, not cached — because
 * that is the case every consumer renders; the fallback and cache variants
 * stay opt-in through `server.use`.
 */
export const lsatTutorFixture = {
  question_id: 'lr-001',
  user_choice: 'A' as string | null,
  correct_choice: 'C',
  is_correct: false,
  explanation: 'The argument generalises from a sample that is too small.',
  coaching: 'Start with the conclusion, then ask what the evidence licenses.',
  next_steps: ['Review sampling bias'],
  concepts: [lsatConceptsFixture.concepts[1]],
  references: [],
  model: 'claude_code/claude-opus-5-5',
  used_llm: true,
  cached: false,
  confidence: 0.82,
  requires_human_review: false,
  latency_ms: 140,
}

/** Validation report fixture (spec 045 FR-15). */
export const lsatValidationFixture = {
  generated_at: '2026-08-31T00:00:00Z',
  section: null,
  question_count: 126,
  guide_count: 40,
  issue_count: 1,
  issues: [
    {
      question_id: 'lr-099',
      kind: 'unknown_concept',
      detail: "concept 'ghost-concept' is not in the catalog",
    },
  ],
  answer_distribution: {
    LR: { A: 14, B: 15, C: 14, D: 14, E: 13 },
    RC: { A: 8, B: 7, C: 8, D: 7, E: 7 },
    LG: { A: 4, B: 4, C: 4, D: 4, E: 3 },
  },
  cross_checks: {
    checked: 2,
    agreements: 1,
    disagreements: [
      {
        question_id: 'lr-007',
        bank_choice: 'A',
        model_choice: 'C',
        model: 'claude_code/claude-opus-5-5',
      },
    ],
  },
}

// --- LSAT knowledge library fixtures (spec 048) ---

const paragraph = (text: string) => ({
  block_type: 'paragraph' as const,
  spans: [{ kind: 'text' as const, text }],
})

const heading = (text: string, anchor: string, level = 2) => ({
  block_type: 'heading' as const,
  level,
  text,
  anchor,
})

const takeaways = [
  heading('Key takeaways', 'key-takeaways'),
  {
    block_type: 'list' as const,
    ordered: false,
    items: [[{ kind: 'text' as const, text: 'A takeaway.' }]],
  },
]

export const lsatLibraryIndexFixture = {
  articles: [
    {
      id: 'argument-anatomy',
      title: 'Argument Anatomy',
      kind: 'foundation',
      level: 'foundation',
      summary: 'Separating the conclusion from what supports it.',
      sections: ['LR'],
      concepts: ['main-conclusion'],
      prerequisites: [],
      related: ['lr-assumption-family'],
      tags: ['conclusion'],
      status: 'reviewed',
      last_reviewed: '2026-09-03',
      reading_minutes: 4,
      word_count: 700,
    },
    {
      id: 'lr-assumption-family',
      title: 'The Assumption Family',
      kind: 'question-type',
      level: 'core',
      summary: 'Necessary versus sufficient, and the negation test.',
      sections: ['LR'],
      concepts: ['necessary-assumption'],
      prerequisites: ['argument-anatomy'],
      related: [],
      tags: ['assumption', 'negation-test'],
      status: 'reviewed',
      last_reviewed: '2026-09-03',
      reading_minutes: 3,
      word_count: 690,
    },
  ],
  count: 2,
}

const articleBody = (title: string) => ({
  archetypes: [],
  revision: 1,
  source: 'original (CC0)',
  references: [{ title: 'LSAC — About the LSAT', url: 'https://www.lsac.org/lsat' }],
  outline: [
    { level: 2, text: 'How it works', anchor: 'how-it-works' },
    { level: 2, text: 'Key takeaways', anchor: 'key-takeaways' },
  ],
  blocks: [
    heading('How it works', 'how-it-works'),
    paragraph(`${title} explains the method.`),
    {
      block_type: 'callout' as const,
      variant: 'example' as const,
      title: 'A worked example',
      blocks: [paragraph('An instance of the pattern.')],
    },
    {
      block_type: 'table' as const,
      headers: [
        [{ kind: 'text' as const, text: 'Stem' }],
        [{ kind: 'text' as const, text: 'Job' }],
      ],
      rows: [
        [
          [{ kind: 'text' as const, text: 'depends on assuming' }],
          [{ kind: 'text' as const, text: 'supply the missing link' }],
        ],
      ],
    },
    {
      block_type: 'notation' as const,
      lines: ['A → B', '¬B → ¬A'],
      caption: 'contrapositive',
    },
    ...takeaways,
  ],
})

export const lsatLibraryDetailFixtures: Record<string, unknown> = {
  'argument-anatomy': {
    article: {
      ...lsatLibraryIndexFixture.articles[0],
      ...articleBody('Argument Anatomy'),
      blocks: [
        heading('How it works', 'how-it-works'),
        {
          block_type: 'paragraph' as const,
          spans: [
            { kind: 'text', text: 'Read on in ' },
            {
              kind: 'article',
              text: 'The Assumption Family',
              ref_id: 'lr-assumption-family',
            },
            { kind: 'text', text: ' and see ' },
            { kind: 'concept', text: 'main conclusion', ref_id: 'main-conclusion' },
            { kind: 'text', text: '.' },
          ],
        },
        {
          block_type: 'callout' as const,
          variant: 'example' as const,
          title: 'A worked example',
          blocks: [paragraph('An instance of the pattern.')],
        },
        ...takeaways,
      ],
    },
    concepts: [
      {
        id: 'main-conclusion',
        name: 'Main Conclusion',
        sections: ['LR'],
        summary: 'The claim the author wants you to accept.',
        examples: [],
        see_also: [],
        references: [],
      },
    ],
    prerequisites: [],
    related: [lsatLibraryIndexFixture.articles[1]],
    tracks: [{ id: 'start-here', name: 'Start Here' }],
    drill_question_ids: ['lr-001'],
    drill_question_count: 1,
  },
  'lr-assumption-family': {
    article: {
      ...lsatLibraryIndexFixture.articles[1],
      ...articleBody('The Assumption Family'),
    },
    concepts: [],
    prerequisites: [lsatLibraryIndexFixture.articles[0]],
    related: [],
    tracks: [],
    drill_question_ids: [],
    drill_question_count: 0,
  },
}

export const lsatLibraryTracksFixture = {
  tracks: [
    {
      id: 'start-here',
      name: 'Start Here',
      summary: 'Orientation first.',
      goal: 'Finish with an accurate model of the test.',
      article_ids: ['argument-anatomy', 'lr-assumption-family'],
      tags: ['orientation'],
      article_count: 2,
      estimated_minutes: 7,
    },
  ],
  count: 1,
}

export const lsatLibrarySearchFixture = {
  query: 'negation',
  results: [
    {
      id: 'lr-assumption-family',
      title: 'The Assumption Family',
      kind: 'question-type',
      sections: ['LR'],
      reading_minutes: 3,
      score: 12,
      matched_in: ['tag', 'body'],
      snippet: '…the negation test settles nearly every hard item…',
      anchor: null,
    },
  ],
  count: 1,
}

/** Autonomy dashboard fixtures (BL-20260511-03). */
export const autonomyHandlers = [
  http.get('http://localhost:8000/api/agents/autonomy/legalbench-history', () =>
    HttpResponse.json({
      available: true,
      count: 3,
      runs: [
        { run_id: 'r1', timestamp: '2026-05-01T00:00:00Z', model: 'mistral', accuracies: { abercrombie: 0.5 } },
        { run_id: 'r2', timestamp: '2026-05-02T00:00:00Z', model: 'mistral', accuracies: { abercrombie: 0.55 } },
        { run_id: 'r3', timestamp: '2026-05-03T00:00:00Z', model: 'mistral', accuracies: { abercrombie: 0.62 } },
      ],
      series: [
        {
          subset: 'abercrombie',
          points: [0.5, 0.55, 0.62],
          latest: 0.62,
          delta_pp: 12.0,
        },
      ],
    }),
  ),
  http.get('http://localhost:8000/api/agents/autonomy/lowest-coverage', () =>
    HttpResponse.json({
      available: true,
      count: 2,
      warn_threshold: 75.0,
      error_threshold: 65.0,
      modules: [
        { module: 'law_ai/core/xai.py', pct: 41.2, severity: 'high', missing_lines: [10, 11] },
        { module: 'law_ai/graph/urls.py', pct: 71.5, severity: 'med', missing_lines: [4] },
      ],
    }),
  ),
  http.get('http://localhost:8000/api/agents/autonomy/recent-quarantine', () =>
    HttpResponse.json({
      available: true,
      count: 1,
      documents: [
        {
          id: 'cl-9001',
          source: 'courtlistener',
          kind: 'case',
          confidence: 0.42,
          reason: 'citation resolver below threshold',
          created_at: '2026-05-11T09:00:00Z',
          reviewed: false,
          approved: null,
        },
      ],
    }),
  ),
  // BL-20260906-23: the fourth panel — audit.AutonomyRun as a cycle log.
  http.get('http://localhost:8000/api/agents/autonomy/runs', () =>
    HttpResponse.json({
      available: true,
      count: 2,
      kind: '',
      by_status: { ok: 1, error: 1 },
      runs: [
        {
          cycle_id: 'cid-digest-1',
          kind: 'digest',
          source: '',
          trace_id: 'trace-1',
          status: 'ok',
          started_at: '2026-09-06T03:00:00Z',
          ended_at: '2026-09-06T03:00:12Z',
          duration_ms: 12000,
          error: '',
          summary: { digest_path: 'var/autonomy/digest-2026-09-06.md' },
        },
        {
          cycle_id: 'cid-corpus-1',
          kind: 'corpus_growth',
          source: 'courtlistener',
          trace_id: 'trace-2',
          status: 'error',
          started_at: '2026-09-06T02:00:00Z',
          ended_at: '2026-09-06T02:00:00.450Z',
          duration_ms: 450,
          error: 'adapter timeout',
          summary: {},
        },
      ],
    }),
  ),
]

/**
 * Quarantine review queue fixtures (BL-20260811-01).
 *
 * Two rows on purpose: one plain pending case, and one that a human already
 * approved whose graph write failed — the state the UI exists to surface.
 */
export const reviewQueueRows = [
  {
    id: 'cl-9001',
    source: 'courtlistener',
    kind: 'case',
    confidence: 0.42,
    reason: 'low_confidence',
    created_at: '2026-09-01T09:00:00Z',
    reviewed_at: null,
    approved: null,
    reviewer: '',
    review_note: '',
    committed_at: null,
    commit_error: '',
  },
  {
    id: 'us-co/crs/18-3-102',
    source: 'colorado_statutes',
    kind: 'statute_section',
    confidence: 0.55,
    reason: 'low_confidence',
    created_at: '2026-09-02T09:00:00Z',
    reviewed_at: '2026-09-03T09:00:00Z',
    approved: true,
    reviewer: 'alice',
    review_note: 'checked against the printed volume',
    committed_at: null,
    commit_error: "ApprovalError: unsupported quarantine kind 'statute_section'",
  },
]

const reviewCounts = {
  pending: 1,
  approved: 1,
  rejected: 0,
  awaiting_commit: 1,
  committed: 0,
  failed: 1,
}

export const reviewQueueHandlers = [
  http.get('http://localhost:8000/api/ingestion/reviews', ({ request }) => {
    const status = new URL(request.url).searchParams.get('status') ?? 'pending'
    const reviews =
      status === 'failed'
        ? [reviewQueueRows[1]]
        : status === 'pending'
          ? [reviewQueueRows[0]]
          : []
    return HttpResponse.json({
      status,
      reviews,
      count: reviews.length,
      counts: reviewCounts,
    })
  }),
  http.get('http://localhost:8000/api/ingestion/reviews/detail', ({ request }) => {
    const id = new URL(request.url).searchParams.get('id')
    const row = reviewQueueRows.find((r) => r.id === id)
    if (!row) return new HttpResponse(null, { status: 404 })
    return HttpResponse.json({
      ...row,
      payload: { payload: { case_name: 'Doe v. Roe', plain_text: 'Affirmed.' } },
    })
  }),
  http.post('http://localhost:8000/api/ingestion/reviews/approve', () =>
    HttpResponse.json({
      review: { ...reviewQueueRows[0], approved: true, committed_at: '2026-09-04T09:00:00Z' },
      committed: true,
      edges: 2,
      commit_error: '',
    }),
  ),
  http.post('http://localhost:8000/api/ingestion/reviews/reject', () =>
    HttpResponse.json({
      review: { ...reviewQueueRows[0], approved: false, review_note: 'out of scope' },
      committed: false,
    }),
  ),
  // The third verb (BL-20260906-04): re-scores, never commits.
  http.post('http://localhost:8000/api/ingestion/reviews/re-extract', () =>
    HttpResponse.json({
      review: { ...reviewQueueRows[0], confidence: 0.81 },
      reextracted: true,
      previous_confidence: reviewQueueRows[0].confidence,
      confidence: 0.81,
      clears_threshold: true,
      n_citations: 3,
    }),
  ),
]

/**
 * Proposed-test review queue (BL-20260511-17). The default is one pending
 * file, because "the dashboard renders the queue" is the interesting case;
 * the empty and error states are set per test.
 */
export const proposedTestsFixture = {
  count: 1,
  available: true,
  files: [
    {
      name: 'law_ai_eval_scoring__autonomy.proposed.py',
      path: 'backend/tests/autonomy/proposed/law_ai_eval_scoring__autonomy.proposed.py',
      module: 'law_ai_eval_scoring',
      size: 512,
      mtime: '2026-09-05T12:00:00Z',
      skip_marked: true,
    },
  ],
}

/**
 * Argumentative Writing fixtures (BL-20260901-09).
 *
 * `lsatWritingPromptFixture` is a `PublicWritingPrompt` — no model response,
 * exactly as the API serves it before a draft exists. The worked example lives
 * separately and is attached only by the `?model_response=1` handler, so a
 * component that renders it without asking fails the way the real API would
 * make it fail.
 */
export const lsatWritingRubricFixture = {
  id: 'ws-rubric-standard',
  name: 'Argumentative writing rubric',
  version: 1,
  summary: 'Four weighted criteria, four bands.',
  bands: [
    { level: 1, label: 'Emerging', descriptor: 'Position is hard to locate.' },
    { level: 2, label: 'Developing', descriptor: 'Position stated, thin support.' },
    { level: 3, label: 'Proficient', descriptor: 'Position argued and defended.' },
    { level: 4, label: 'Strong', descriptor: 'Position argued against the best counter.' },
  ],
  criteria: [
    {
      id: 'position',
      name: 'Position',
      description: 'Takes one side and stays with it.',
      weight: 0.4,
      look_for: ['A thesis in the opening paragraph'],
      band_notes: { '4': 'The thesis names the position and the trade-off.' },
    },
    {
      id: 'counterargument',
      name: 'Counterargument',
      description: 'Engages the strongest opposing perspective.',
      weight: 0.6,
      look_for: ['Names an opposing perspective by its content'],
      band_notes: { '4': 'Answers the best version of the other side.' },
    },
  ],
  source: 'original (CC0)',
}

export const lsatWritingPromptFixture = {
  id: 'ws-001',
  title: 'Municipal broadband',
  rubric_id: 'ws-rubric-standard',
  difficulty: 'med',
  issue: 'Should the city build its own broadband network?',
  context: 'Two private carriers serve the city; a third of households are unserved.',
  positions: [
    { id: 'build', name: 'Build it', summary: 'The city funds and runs the network.' },
    { id: 'partner', name: 'Partner', summary: 'The city subsidises a private build-out.' },
  ],
  perspectives: [
    { id: 'p1', text: 'A public network is accountable to voters.' },
    { id: 'p2', text: 'Municipal projects have overrun their budgets here before.' },
    { id: 'p3', text: 'Unserved households are concentrated in two districts.' },
  ],
  task: 'Argue for one position and answer the strongest objection to it.',
  prewriting_minutes: 15,
  time_limit_minutes: 35,
  concepts: ['argument-construction'],
  self_check: [
    { criterion_id: 'position', prompt: 'Can a reader name your position from the first paragraph?' },
    { criterion_id: 'counterargument', prompt: 'Did you answer the strongest objection, not the weakest?' },
  ],
  references: [],
  has_model_response: true,
}

export const lsatWritingModelResponseFixture = {
  position_id: 'build',
  thesis: 'The city should build the network itself.',
  essay: 'First paragraph of the model essay.\n\nSecond paragraph of the model essay.',
  annotations: [
    { criterion_id: 'position', note: 'The thesis lands in sentence one.' },
    { criterion_id: 'counterargument', note: 'Paragraph three answers the overrun objection.' },
  ],
}

/**
 * Server-side read state for the library (BL-20260903-05). Mutable so a test
 * can arrange "this article was read on another device" — call
 * `resetLsatReadArticles()` in `beforeEach`.
 */
export const lsatReadArticles = new Set<string>()

export function resetLsatReadArticles(...ids: string[]): void {
  lsatReadArticles.clear()
  for (const id of ids) lsatReadArticles.add(id)
}

/**
 * Per-reveal hint events the page posted (BL-20260830-13). A test asserts
 * against this rather than a spy, because the point of the item is that the
 * *server* hears about every reveal.
 */
export const lsatHintReveals: {
  questionId: string
  step_index: number
  revealed_count: number
  spoiler: boolean
}[] = []

export function resetLsatHintReveals(): void {
  lsatHintReveals.length = 0
}

/** Factory status snapshot for the Authoring tab (BL-20260702-06). */
export const lsatFactoryStatusFixture = {
  bank_total: 42,
  bank_by_section: { LR: 30, RC: 8, LG: 4 },
  writing_prompts: 3,
  writing_by_difficulty: { med: 2, hard: 1 },
  coverage_cells: 60,
  cells_with_deficit: 11,
  top_deficits: [
    { archetype_id: 'weaken', difficulty: 'hard', have: 1, want: 5 },
    { archetype_id: 'parallel-flaw', difficulty: 'med', have: 0, want: 3 },
  ],
  pending_proposals: 7,
  pending_from_factory: 5,
  latest_manifest: '/var/lsat/factory/manifests/mfst-20260905.json',
  latest_manifest_summary: {
    manifest_id: 'mfst-20260905-abc123',
    created_at: '2026-09-05T12:00:00Z',
    jobs: 12,
    by_tier: { bulk: 8, standard: 4 },
    by_archetype: { weaken: 6, 'parallel-flaw': 6 },
  },
  pending_gates: {
    by_executor: { OllamaExecutor: 4, ClaudeCodeExecutor: 1 },
    by_tier: { bulk: 4, standard: 1 },
    answer_balance_flagged: 2,
  },
}

export const handlers = [
  // Argumentative Writing (spec 047 FR-1..FR-4, surfaced in BL-20260901-09).
  http.get('http://localhost:8000/api/lsat/writing/prompts', () =>
    HttpResponse.json({ prompts: [lsatWritingPromptFixture], count: 1 }),
  ),
  http.get(
    'http://localhost:8000/api/lsat/writing/prompts/:promptId',
    ({ request }) => {
      const url = new URL(request.url)
      const body: Record<string, unknown> = {
        prompt: lsatWritingPromptFixture,
        rubric: lsatWritingRubricFixture,
      }
      // The worked example is withheld until it is asked for by name — the
      // writing equivalent of stripping the answer key.
      if (['1', 'true'].includes(url.searchParams.get('model_response') ?? '')) {
        body.model_response = lsatWritingModelResponseFixture
      }
      return HttpResponse.json(body)
    },
  ),
  http.get('http://localhost:8000/api/lsat/writing/rubric', () =>
    HttpResponse.json({ rubric: lsatWritingRubricFixture }),
  ),
  http.post('http://localhost:8000/api/lsat/writing/evaluate', () =>
    HttpResponse.json({
      evaluation: {
        prompt_id: 'ws-001',
        rubric_id: 'ws-rubric-standard',
        position_taken: 'build',
        summary: 'A clear position, thin on the strongest objection.',
        criteria: [
          {
            criterion_id: 'position',
            band: 4,
            evidence: 'The opening names the position.',
            improvement: 'Say what it costs to hold it.',
          },
          {
            criterion_id: 'counterargument',
            band: 2,
            evidence: 'The overrun objection is mentioned once.',
            improvement: 'Answer it rather than noting it.',
          },
        ],
        strengths: ['Clear thesis'],
        priorities: ['Engage the overrun objection'],
        weighted_band: 2.8,
      },
      model: 'claude_code/claude-opus-5-5',
      prompt_version: 'lsat_writing_evaluator.v1',
      confidence: 0.7,
      latency_ms: 900,
      degraded: false,
      trace_id: 'tr-ws-1',
    }),
  ),

  ...autonomyHandlers,
  ...reviewQueueHandlers,
  http.get('http://localhost:8000/api/agents/proposed-tests', () =>
    HttpResponse.json(proposedTestsFixture),
  ),
  // The app's own ticket route (BL-20260430-07). `openAgentStream` asks for
  // one before every socket; with no key configured the answer is "none
  // needed", which is what the test environment models.
  http.get('/api/ws-ticket', () => HttpResponse.json({ ticket: null })),
  // Mock LSAT cross-check (spec 045 FR-14): lg-001 agrees with the key,
  // lr-001 disagrees, anything else is offline/unavailable.
  http.post(
    'http://localhost:8000/api/lsat/questions/:questionId/cross-check',
    ({ params }) => {
      const qid = String(params.questionId)
      if (qid === 'lg-001') {
        return HttpResponse.json({
          question_id: qid,
          bank_choice: 'D',
          model_choice: 'D',
          agree: true,
          rationale: 'Rules eliminate every other order.',
          model: 'claude_code/claude-opus-5-5',
          used_llm: true,
          cached: false,
          requires_human_review: false,
          latency_ms: 42,
        })
      }
      if (qid === 'lr-001') {
        return HttpResponse.json({
          question_id: qid,
          bank_choice: 'A',
          model_choice: 'C',
          agree: false,
          rationale: 'The form matches the third option.',
          model: 'claude_code/claude-opus-5-5',
          used_llm: true,
          cached: false,
          requires_human_review: true,
          latency_ms: 42,
        })
      }
      return HttpResponse.json({
        question_id: qid,
        bank_choice: 'A',
        model_choice: null,
        agree: null,
        rationale: 'No provider reachable — cross-check unavailable.',
        model: 'fallback/offline',
        used_llm: false,
        cached: false,
        requires_human_review: false,
        latency_ms: 1,
      })
    },
  ),

  // Mock LSAT validation report (spec 045 FR-15).
  http.get('http://localhost:8000/api/lsat/factory/status', () =>
    HttpResponse.json(lsatFactoryStatusFixture),
  ),

  http.get('http://localhost:8000/api/lsat/validation', () =>
    HttpResponse.json(lsatValidationFixture),
  ),

  // Mock LSAT concept catalog (spec 045 FR-12 references).
  http.get('http://localhost:8000/api/lsat/concepts', () =>
    HttpResponse.json(lsatConceptsFixture),
  ),

  // One concept plus both of its inverses. `taught_in` is derived from the
  // library index rather than hard-coded, so a fixture article gaining or
  // losing a concept tag stays consistent here for free.
  http.get(
    'http://localhost:8000/api/lsat/concepts/:conceptId',
    ({ params }) => {
      const id = params.conceptId as string
      const concept = lsatConceptsFixture.concepts.find((c) => c.id === id)
      if (!concept) {
        return HttpResponse.json({ detail: 'concept not found' }, { status: 404 })
      }
      const usedIn = id === 'main-conclusion' ? ['lr-001', 'lr-002'] : []
      return HttpResponse.json({
        concept,
        // The id list is capped at ten server-side; the count is the whole
        // truth, so the entry can name it exactly (BL-20260905-06).
        used_in_questions: usedIn.slice(0, 10),
        used_in_count: usedIn.length,
        taught_in: lsatLibraryIndexFixture.articles
          .filter((a) => (a.concepts as string[]).includes(id))
          .map((a) => a.id),
      })
    },
  ),

  // Default tutor reply (BL-20260905-35). Every suite that reaches the tutor
  // used to install its own handler; this one answers the common case — a real
  // model call, uncached — so only the tests that care about a specific reply
  // (fallback, cache, streaming) still need `server.use`. It echoes the posted
  // question and choice so the answer belongs to the question on screen.
  http.post('http://localhost:8000/api/lsat/tutor', async ({ request }) => {
    const body = (await request.json()) as {
      question_id?: string
      user_choice?: string | null
    }
    return HttpResponse.json({
      ...lsatTutorFixture,
      question_id: body.question_id ?? lsatTutorFixture.question_id,
      user_choice: body.user_choice ?? null,
    })
  }),

  // Spec 054: by default a question has no contrast siblings, so the panel
  // renders nothing; a test that wants a set installs its own handler.
  http.get(
    'http://localhost:8000/api/lsat/questions/:questionId/contrast',
    ({ params }) =>
      HttpResponse.json({
        root_id: params.questionId,
        question_id: params.questionId,
        count: 1,
        members: [],
        spoilers: false,
      }),
  ),

  http.post(
    'http://localhost:8000/api/lsat/questions/:questionId/hint',
    async ({ params, request }) => {
      if (params.questionId !== lsatGuideFixture.question_id) {
        return HttpResponse.json(
          { detail: 'no solve guide for this question', has_tutor: true },
          { status: 404 },
        )
      }
      const body = (await request.json()) as {
        step_index: number
        revealed_count: number
        spoiler?: boolean
      }
      lsatHintReveals.push({
        questionId: String(params.questionId),
        step_index: body.step_index,
        revealed_count: body.revealed_count,
        spoiler: Boolean(body.spoiler),
      })
      return HttpResponse.json({ recorded: true }, { status: 202 })
    },
  ),

  // Mock LSAT solve-guide endpoint (spec 045): lg-001 has a guide, every
  // other question 404s with the tutor fallback flag.
  http.get(
    'http://localhost:8000/api/lsat/questions/:questionId/guide',
    ({ params, request }) => {
      if (params.questionId !== lsatGuideFixture.question_id) {
        return HttpResponse.json(
          { detail: 'no solve guide for this question', has_tutor: true },
          { status: 404 },
        )
      }
      const spoilers = new URL(request.url).searchParams.get('spoilers') === '1'
      return HttpResponse.json(publicGuideView(spoilers))
    },
  ),

  // Mock LSAT knowledge library (spec 048). Two articles is enough to cover
  // the index, the detail view, cross-reference navigation and search.
  http.get('http://localhost:8000/api/lsat/library', ({ request }) => {
    const url = new URL(request.url)
    const section = url.searchParams.get('section')
    const rows = lsatLibraryIndexFixture.articles.filter(
      (a) => !section || a.sections.includes(section as never),
    )
    return HttpResponse.json({ articles: rows, count: rows.length })
  }),

  // Library reading progress (BL-20260903-05). The mock server starts with
  // nothing read and remembers what a test marks, so a hydrate assertion is a
  // real round trip rather than a constant.
  http.get('http://localhost:8000/api/lsat/library/read', () =>
    HttpResponse.json({
      read: [...lsatReadArticles],
      count: lsatReadArticles.size,
    }),
  ),
  http.post(
    'http://localhost:8000/api/lsat/library/read',
    async ({ request }) => {
      const body = (await request.json()) as { article_id: string; read?: boolean }
      if (body.read === false) lsatReadArticles.delete(body.article_id)
      else lsatReadArticles.add(body.article_id)
      return HttpResponse.json({
        read: [...lsatReadArticles],
        count: lsatReadArticles.size,
      })
    },
  ),

  http.get('http://localhost:8000/api/lsat/library/tracks', () =>
    HttpResponse.json(lsatLibraryTracksFixture),
  ),

  http.get('http://localhost:8000/api/lsat/library/search', ({ request }) => {
    const q = (new URL(request.url).searchParams.get('q') ?? '').toLowerCase()
    if (q.length < 2) {
      return HttpResponse.json(
        { detail: { q: 'must be between 2 and 100 characters' } },
        { status: 422 },
      )
    }
    const results = lsatLibrarySearchFixture.results.filter((r) =>
      (r.title + r.snippet).toLowerCase().includes(q),
    )
    return HttpResponse.json({ query: q, results, count: results.length })
  }),

  http.get('http://localhost:8000/api/lsat/library/:articleId', ({ params }) => {
    const detail = lsatLibraryDetailFixtures[params.articleId as string]
    if (!detail) {
      return HttpResponse.json({ detail: 'article not found' }, { status: 404 })
    }
    return HttpResponse.json(detail)
  }),

  // Mock analysis endpoint. The shape is checked against the backend's own
  // Pydantic schema by __tests__/lib/apiContract.test.ts (BL-20260811-16) —
  // every required field of AnalysisResponse/IRACOutput/PrecedentList is
  // present and no invented ones are, so a component test can never pass
  // against a payload the real API would not send.
  http.post('http://localhost:8000/api/analysis', () =>
    HttpResponse.json({
      id: 'analysis-123',
      timestamp: '2026-01-01T00:00:00Z',
      latency_ms: 1200,
      confidence: 0.87,
      requires_human_review: false,
      irac: {
        issue: 'Whether the right to privacy includes...',
        rule: 'The Constitution protects zones of privacy...',
        application: 'In this case, the statute...',
        conclusion: 'The law is unconstitutional.',
        confidence: 0.87,
        reasoning_trace: ['Framed the issue', 'Applied the rule'],
        sources: [
          {
            title: 'Roe v. Wade, 410 U.S. 113 (1973)',
            url: 'https://case.law/...',
            verified: true,
            resolved_case_id: 'case:roe',
          },
        ],
      },
      precedents: {
        precedents: [
          {
            case_id: 'case:roe',
            title: 'Roe v. Wade',
            court: 'SCOTUS',
            year: 1973,
            relevance_score: 0.91,
            distinguishing_factors: ['Different statutory scheme'],
            url: 'https://case.law/...',
          },
        ],
        summary: 'One controlling privacy precedent.',
        confidence: 0.9,
      },
      agent_trace: [
        {
          agent: 'LegalAnalyst',
          trace_id: 'tr-1',
          latency_ms: 700,
          confidence: 0.87,
        },
        {
          agent: 'PrecedentHunter',
          trace_id: 'tr-2',
          latency_ms: 500,
          confidence: 0.9,
        },
      ],
    }),
  ),

  // Precedent chain (BL-20260429-22). Registered ahead of the `:caseId`
  // catch-all below, which would otherwise swallow /api/graph/path.
  http.get('http://localhost:8000/api/graph/path', () =>
    HttpResponse.json({
      available: true,
      found: false,
      hops: 0,
      nodes: [],
      edges: [],
    }),
  ),

  // Account identity (spec 036 / BL-20260906-68). AllowAny, so signed out is
  // a 200 rather than a 401 — the shell asks this before anything
  // account-scoped, and the default here is "signed out".
  http.get('http://localhost:8000/api/auth/me', () =>
    HttpResponse.json({
      authenticated: false,
      username: null,
      id: null,
      is_staff: false,
      scopes: [],
    }),
  ),

  // The session half of spec 036, now that something in the app renders a
  // form for it (BL-20260906-08). The default is a refusal: a test that wants
  // a successful sign-in says so with `server.use`, and every other test gets
  // the anonymous shell it was written against.
  http.get('http://localhost:8000/api/auth/csrf', () =>
    HttpResponse.json({ csrf_token: 'test-csrf-token' }),
  ),
  http.post('http://localhost:8000/api/auth/login', () =>
    HttpResponse.json({ detail: 'invalid credentials' }, { status: 401 }),
  ),
  http.post('http://localhost:8000/api/auth/logout', () =>
    HttpResponse.json({ authenticated: false, was_authenticated: true }),
  ),

  // Matters (spec 036). The shell's ScopeSwitcher asks on every render, so a
  // default of "signed out, no matters" keeps unrelated shell tests quiet;
  // tests that care override it with server.use().
  http.get('http://localhost:8000/api/matters', () =>
    HttpResponse.json({ matters: [], count: 0 }),
  ),

  // Court vocabulary (BL-20260905-89). Also ahead of the `:caseId`
  // catch-all, which would otherwise answer /api/graph/courts with a case.
  http.get('http://localhost:8000/api/graph/courts', () =>
    HttpResponse.json({ available: true, courts: [], count: 0 }),
  ),

  // Mock graph query
  http.get('http://localhost:8000/api/graph/:caseId', ({ params }) => {
    return HttpResponse.json({
      nodes: [
        { id: params.caseId, label: 'Case', type: 'Case' },
        { id: 'doctrine:privacy', label: 'Right to Privacy', type: 'LegalConcept' },
      ],
      edges: [{ source: params.caseId, target: 'doctrine:privacy', label: 'HAS_HOLDING' }],
    })
  }),
]

export const server = setupServer(...handlers)