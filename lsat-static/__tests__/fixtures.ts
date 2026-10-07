/**
 * Small deterministic stand-ins for `content.json` (BL-20260901-07).
 *
 * The shipped bundle is ~840 KB and changes every time the bank is re-exported,
 * so behavioural tests mock `@/lib/data` with these instead: three LR
 * questions, one four-step guide whose last step is a spoiler, and one writing
 * prompt with a rubric. Content drift is covered elsewhere, by the root suite's
 * `TestContentDrift`; these fixtures only have to be *shaped* like the export.
 */
import type { SearchHit } from '@/lib/search'
import type {
  Article,
  Concept,
  Question,
  Section,
  SectionCode,
  SolveGuide,
  Track,
  WritingPrompt,
  WritingRubric,
} from '@/lib/types'

export const SECTION_LR: Section = {
  code: 'LR',
  name: 'Logical Reasoning',
  description: 'Short arguments, one question each.',
  format: '25 questions',
  timing: '35 minutes',
}

export const SECTION_WS: Section = {
  code: 'WS',
  name: 'Argumentative Writing',
  description: 'Choose a position and defend it.',
  format: 'One prompt',
  timing: '35 minutes',
}

function question(n: number, correct: string): Question {
  return {
    id: `lr-fixture-0${n}`,
    section: 'LR',
    type: 'Assumption',
    difficulty: 'medium',
    stem: `Fixture stem ${n}.`,
    choices: [
      { label: 'A', text: `Choice A of ${n}` },
      { label: 'B', text: `Choice B of ${n}` },
      { label: 'C', text: `Choice C of ${n}` },
      { label: 'D', text: `Choice D of ${n}` },
      { label: 'E', text: `Choice E of ${n}` },
    ],
    correct,
    explanation: `Explanation ${n}.`,
  }
}

export const QUESTIONS: Question[] = [question(1, 'C'), question(2, 'A'), question(3, 'E')]

export const CONCEPTS: Concept[] = []

/** Four steps, the last one a spoiler — the shape SolveAssist locks. */
export const GUIDE: SolveGuide = {
  question_id: 'lr-fixture-01',
  method: 'Assumption negation',
  steps: [
    { kind: 'orient', title: 'Read the question stem', text: 'Step one text.', spoiler: false },
    { kind: 'inventory', title: 'Split premise from conclusion', text: 'Step two text.', spoiler: false },
    { kind: 'infer', title: 'Name the gap', text: 'Step three text.', spoiler: false },
    { kind: 'answer', title: 'The answer', text: 'Step four text.', spoiler: true },
  ],
}

export const RUBRIC: WritingRubric = {
  id: 'argumentative-writing-v1',
  name: 'Argumentative Writing',
  summary: 'Four criteria, four bands.',
  bands: [
    { level: 1, label: 'Emerging', descriptor: 'Little support.' },
    { level: 4, label: 'Strong', descriptor: 'Fully developed.' },
  ],
  criteria: [
    {
      id: 'position',
      name: 'Position',
      description: 'Takes and holds a position.',
      weight: 1,
      look_for: ['A thesis in the first paragraph'],
      band_notes: { '1': 'No thesis.', '4': 'A clear thesis.' },
    },
  ],
}

export const PROMPT: WritingPrompt = {
  id: 'ws-fixture-01',
  title: 'Fixture prompt one',
  rubric_id: RUBRIC.id,
  difficulty: 'medium',
  issue: 'Should the town build the bypass?',
  context: 'The council has costed two routes.',
  positions: [
    { id: 'build', name: 'Build it', summary: 'Traffic falls.' },
    { id: 'stop', name: 'Do not build it', summary: 'Farmland is lost.' },
  ],
  perspectives: [{ id: 'p1', text: 'A haulier says deliveries are late.' }],
  task: 'Argue for one position.',
  prewriting_minutes: 5,
  time_limit_minutes: 35,
  model_response: {
    position_id: 'build',
    thesis: 'The bypass is worth its cost.',
    essay: 'First paragraph.\n\nSecond paragraph.',
    annotations: [{ criterion_id: 'position', note: 'The thesis is in sentence one.' }],
  },
  self_check: [{ criterion_id: 'position', prompt: 'Did you state a position?' }],
}

export const PROMPT_B: WritingPrompt = {
  ...PROMPT,
  id: 'ws-fixture-02',
  title: 'Fixture prompt two',
}

/** Fifty-one words — one over the submit threshold in `DraftPanel`. */
export const LONG_DRAFT = Array.from({ length: 51 }, (_, i) => `word${i}`).join(' ')

// ---------------------------------------------------------------------------
// Knowledge library (spec 048) — BL-20260903-07 / BL-20260905-03
// ---------------------------------------------------------------------------

function article(over: Partial<Article> & Pick<Article, 'id' | 'title'>): Article {
  return {
    kind: 'question-type',
    level: 'core',
    summary: `Summary of ${over.title}.`,
    sections: ['LR'],
    concepts: [],
    archetypes: [],
    prerequisites: [],
    related: [],
    tags: [],
    status: 'reviewed',
    last_reviewed: '2026-09-01',
    revision: 1,
    blocks: [],
    outline: [],
    word_count: 400,
    reading_minutes: 2,
    ...over,
  }
}

export const ARTICLES: Article[] = [
  article({
    id: 'lib-orientation',
    title: 'What the LSAT measures',
    kind: 'orientation',
    level: 'foundation',
    concepts: ['necessary-assumption'],
    related: ['lib-assumptions'],
    outline: [{ level: 2, text: 'The three scored sections', anchor: 'three-sections' }],
    blocks: [
      { block_type: 'heading', level: 2, text: 'The three scored sections', anchor: 'three-sections' },
      {
        block_type: 'paragraph',
        spans: [
          { kind: 'text', text: 'Start here, then read ' },
          { kind: 'article', text: 'the assumption family', ref_id: 'lib-assumptions' },
          { kind: 'text', text: ' on ' },
          { kind: 'concept', text: 'necessary assumptions', ref_id: 'necessary-assumption' },
          { kind: 'text', text: '.' },
        ],
      },
    ],
  }),
  article({
    id: 'lib-assumptions',
    title: 'The assumption family',
    prerequisites: ['lib-orientation'],
    concepts: ['necessary-assumption'],
    outline: [{ level: 2, text: 'Negating a candidate', anchor: 'negating' }],
    blocks: [
      { block_type: 'heading', level: 2, text: 'Negating a candidate', anchor: 'negating' },
      { block_type: 'paragraph', spans: [{ kind: 'text', text: 'Negate the choice and see what breaks.' }] },
    ],
  }),
  article({
    id: 'lib-diagramming',
    title: 'Conditional diagramming',
    kind: 'technique',
    sections: ['LG'],
    concepts: ['conditional-chain'],
    blocks: [
      { block_type: 'paragraph', spans: [{ kind: 'text', text: 'Arrows, contrapositives, chains.' }] },
    ],
  }),
]

export const TRACKS: Track[] = [
  {
    id: 'track-start',
    name: 'Start here',
    summary: 'The first week.',
    goal: 'Know what the exam asks before drilling it.',
    article_ids: ['lib-orientation', 'lib-assumptions'],
    tags: [],
    article_count: 2,
    estimated_minutes: 20,
  },
]

export const LIBRARY_CONCEPTS: Concept[] = [
  {
    id: 'necessary-assumption',
    name: 'Necessary assumption',
    summary: 'Something the argument cannot do without.',
    detail: 'Negating it destroys the conclusion.',
    examples: ['If the plan works, funding was secured.'],
    sections: ['LR'],
    see_also: ['conditional-chain'],
  },
  {
    id: 'conditional-chain',
    name: 'Conditional chain',
    summary: 'Linked sufficient/necessary statements.',
    sections: ['LG'],
    see_also: ['no-such-concept'],
  },
]

/**
 * The `@/lib/data` surface the library components read, over the fixtures
 * above. One place, so `Library.test.tsx` and `Concepts.test.tsx` cannot
 * disagree about what the corpus contains.
 */
export function libraryData() {
  const byId = new Map(ARTICLES.map((a) => [a.id, a]))
  const conceptsById = new Map(LIBRARY_CONCEPTS.map((c) => [c.id, c]))
  return {
    articles: ARTICLES,
    tracks: TRACKS,
    content: { concepts: LIBRARY_CONCEPTS, questions: QUESTIONS },
    articleById: (id: string) => byId.get(id),
    conceptById: (id: string) => conceptsById.get(id),
    trackById: (id: string) => TRACKS.find((t) => t.id === id),
    drillsForArticle: () => [],
    inboundArticles: (id: string) =>
      ARTICLES.filter((a) => a.id !== id && a.related.includes(id)),
    articlesTeaching: (conceptId: string) =>
      ARTICLES.filter(
        (a) =>
          a.concepts.includes(conceptId) ||
          a.blocks.some((b) =>
            b.block_type === 'paragraph'
              ? b.spans.some((s) => s.kind === 'concept' && s.ref_id === conceptId)
              : false,
          ),
      ),
    questionsForConcept: () => [],
  }
}

/**
 * A stand-in ranker: substring over title and summary, in corpus order.
 *
 * Mirrors the real `searchLibrary` signature, including the section narrowing
 * — and, like it, filters BEFORE `limit` so the cap cannot hide a section's
 * matches (issue #120).
 */
export function librarySearch(
  query: string,
  limit = 20,
  section: SectionCode | 'all' = 'all',
): SearchHit[] {
  const needle = query.trim().toLowerCase()
  if (needle.length < 2) return []
  return ARTICLES.filter(
    (a) =>
      `${a.title} ${a.summary}`.toLowerCase().includes(needle) &&
      (section === 'all' || a.sections.includes(section)),
  )
    .slice(0, limit)
    .map((a) => ({
      id: a.id,
      title: a.title,
      kind: a.kind,
      sections: a.sections,
      reading_minutes: a.reading_minutes,
      score: 1,
      matched_in: ['title'],
      snippet: a.summary,
      anchor: null,
    }))
}
