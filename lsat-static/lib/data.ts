// Build-time import of the HITL-approved LSAT bank. Bundled into the static
// export, so the published site makes zero network calls for content.
import raw from '../content.json'
import type { Content, Passage, Question, SectionCode } from './types'

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
