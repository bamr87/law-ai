// Types for the LSAT bank artifact (content.json), produced by
// `python manage.py lsat_export` (spec 025 FR-1/FR-2). Kept in lockstep with
// the source bank by tests/test_lsat_site.py.

export type SectionCode = 'LR' | 'RC' | 'LG'

export interface Reference {
  title: string
  url: string
  note?: string | null
}

export interface Choice {
  label: string // "A".."E"
  text: string
}

export interface Question {
  id: string
  section: SectionCode
  type: string
  difficulty: string
  stem: string
  choices: Choice[]
  correct: string // one of the choice labels
  explanation: string
  source?: string | null
  concepts?: string[]
  references?: Reference[]
  passage_id?: string | null
}

export interface Passage {
  id: string
  section: SectionCode
  title: string
  summary?: string
  passage?: string
  setup?: string
  rules?: string[]
  source?: string | null
}

export interface Concept {
  id: string
  name: string
  summary?: string
  detail?: string
  examples?: string[]
  see_also?: string[]
  sections?: string[]
}

export interface Section {
  code: SectionCode
  name: string
  description: string
  format: string
  timing: string
  scoring?: string
  skills?: string[]
  tips?: string[]
  concepts?: string[]
  references?: Reference[]
}

export interface Content {
  schema_version: number | string
  generated_at: string
  counts: { total: number } & Record<SectionCode, number>
  sections: Section[]
  concepts: Concept[]
  passages: Passage[]
  questions: Question[]
}
