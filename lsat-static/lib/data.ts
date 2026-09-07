// Build-time import of the HITL-approved LSAT bank. Bundled into the static
// export, so the published site makes zero network calls for content.
import raw from '../content.json'
import type {
  Article,
  Concept,
  Content,
  Passage,
  Question,
  SectionCode,
  SolveGuide,
  Track,
  WritingPrompt,
  WritingRubric,
} from './types'

export const content = raw as unknown as Content

/**
 * The drillable sections — the ones with a multiple-choice question bank.
 *
 * 'WS' is deliberately absent: Argumentative Writing has section metadata and
 * concept tags but no keyed questions, so it gets its own view rather than a
 * Drill. Mirrors `MCQ_SECTIONS` in the backend's `bank.py`.
 */
export const SECTIONS: SectionCode[] = ['LR', 'RC', 'LG']

export function sectionMeta(code: SectionCode) {
  return content.sections.find((s) => s.code === code)
}

export function questionsFor(code: SectionCode): Question[] {
  return content.questions.filter((q) => q.section === code)
}

const _passages = new Map<string, Passage>(content.passages.map((p) => [p.id, p]))

export function passageById(id: string | null | undefined): Passage | undefined {
  return id ? _passages.get(id) : undefined
}

const _guides = new Map<string, SolveGuide>(
  (content.guides ?? []).map((g) => [g.question_id, g]),
)

/**
 * Solve guide for a question, if one was authored.
 *
 * Unlike the API-backed lab there is no server to withhold spoiler steps, so
 * the whole guide is in the bundle — as the answer keys already are, since the
 * site grades offline. `SolveAssist` keeps spoiler steps locked in the UI
 * until the question is graded, mirroring the API's `public_guide_view`.
 */
export function guideFor(questionId: string): SolveGuide | undefined {
  return _guides.get(questionId)
}

const _concepts = new Map<string, Concept>(content.concepts.map((c) => [c.id, c]))

export function conceptById(id: string): Concept | undefined {
  return _concepts.get(id)
}

// ---------------------------------------------------------------------------
// Argumentative Writing (spec 047)
// ---------------------------------------------------------------------------

export const writingPrompts: WritingPrompt[] = content.writing_prompts ?? []

const _rubrics = new Map<string, WritingRubric>(
  (content.writing_rubrics ?? []).map((r) => [r.id, r]),
)

export function writingPromptById(id: string): WritingPrompt | undefined {
  return writingPrompts.find((p) => p.id === id)
}

/**
 * The rubric a prompt is read against.
 *
 * The bundle carries the full rubric *and* the annotated model response by
 * design: the published site has no backend, so self-scoring against the
 * rubric is the only feedback available offline (spec 047 FR-3). `Writing`
 * keeps both locked until the learner submits, the same way `SolveAssist`
 * locks spoiler steps until a question is graded.
 */
export function rubricFor(prompt: WritingPrompt): WritingRubric | undefined {
  return _rubrics.get(prompt.rubric_id)
}

// ---------------------------------------------------------------------------
// Knowledge library (spec 048)
// ---------------------------------------------------------------------------

/**
 * The whole library is in the bundle, bodies included. That is the point: the
 * published site has no backend, so reading, cross-linking and searching all
 * have to work from what shipped (spec 048 NFR-OFFLINE-1). Unlike guides and
 * model responses there is nothing here to keep locked — an article is study
 * material, not an answer key.
 */
export const articles: Article[] = content.library ?? []

const _articles = new Map<string, Article>(articles.map((a) => [a.id, a]))

export function articleById(id: string): Article | undefined {
  return _articles.get(id)
}

export const tracks: Track[] = content.library_tracks ?? []

export function trackById(id: string): Track | undefined {
  return tracks.find((t) => t.id === id)
}

/** Article ids that point at this one — prerequisite, related, or inline. */
export function inboundArticles(id: string): Article[] {
  return articles.filter(
    (a) =>
      a.id !== id &&
      (a.prerequisites.includes(id) ||
        a.related.includes(id) ||
        a.blocks.some((b) =>
          b.block_type === 'paragraph'
            ? b.spans.some((s) => s.kind === 'article' && s.ref_id === id)
            : false,
        )),
  )
}

/**
 * Articles that teach a concept — the inverse of `Article.concepts`.
 *
 * Mirrors the platform's `articles_teaching` (spec 048 FR-7), inline concept
 * spans included: a learner who misses a concept-tagged question needs a way
 * from the tag to the material, not only from the material to the tag.
 */
export function articlesTeaching(conceptId: string): Article[] {
  return articles.filter(
    (a) =>
      a.concepts.includes(conceptId) ||
      a.blocks.some((b) =>
        b.block_type === 'paragraph'
          ? b.spans.some((s) => s.kind === 'concept' && s.ref_id === conceptId)
          : false,
      ),
  )
}

/** Bank questions tagged with a concept. */
export function questionsForConcept(conceptId: string): Question[] {
  return content.questions.filter((q) =>
    (q.concepts ?? []).includes(conceptId),
  )
}

/** Bank questions tagged with any concept this article teaches. */
export function drillsForArticle(article: Article): Question[] {
  if (article.concepts.length === 0) return []
  return content.questions.filter((q) =>
    (q.concepts ?? []).some((c) => article.concepts.includes(c)),
  )
}
