// Build-time import of the HITL-approved LSAT bank. Bundled into the static
// export, so the published site makes zero network calls for content.
import raw from '../content.json'
import type {
  Concept,
  Content,
  Passage,
  Question,
  SectionCode,
  SolveGuide,
} from './types'

export const content = raw as unknown as Content

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
