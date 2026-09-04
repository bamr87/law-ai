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