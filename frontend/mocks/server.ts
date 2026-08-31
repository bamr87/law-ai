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

/** Concept catalog fixture (spec 045 FR-12): note the external reference —
 *  the UI must resolve concepts WITHOUT ever rendering that link. */
export const lsatConceptsFixture = {
  count: 1,
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
  ],
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
        model: 'claude_code/claude-opus-5',
      },
    ],
  },
}

export const handlers = [
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
          model: 'claude_code/claude-opus-5',
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
          model: 'claude_code/claude-opus-5',
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
  http.get('http://localhost:8000/api/lsat/validation', () =>
    HttpResponse.json(lsatValidationFixture),
  ),

  // Mock LSAT concept catalog (spec 045 FR-12 references).
  http.get('http://localhost:8000/api/lsat/concepts', () =>
    HttpResponse.json(lsatConceptsFixture),
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

  // Mock analysis endpoint
  http.post('http://localhost:8000/api/analysis', async ({ request }) => {
    const body = await request.json() as any
    return HttpResponse.json({
      id: 'analysis-123',
      irac: {
        issue: 'Whether the right to privacy includes...',
        rule: 'The Constitution protects zones of privacy...',
        application: 'In this case, the statute...',
        conclusion: 'The law is unconstitutional.',
      },
      sources: [
        { id: 'case:roe', title: 'Roe v. Wade, 410 U.S. 113 (1973)', url: 'https://case.law/...' },
      ],
      confidence: 0.87,
      agent_trace: ['LegalAnalyst', 'PrecedentHunter'],
    })
  }),

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