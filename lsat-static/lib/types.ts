// Types for the LSAT bank artifact (content.json), produced by
// `python manage.py lsat_export` (spec 025 FR-1/FR-2). Kept in lockstep with
// the source bank by tests/test_lsat_site.py.

// 'WS' (Argumentative Writing) carries section metadata and concept tags but
// has no keyed-question form — its practice items are WritingPrompts, not
// Questions. See `SECTIONS` in lib/data.ts for the drillable subset.
export type SectionCode = 'LR' | 'RC' | 'LG' | 'WS'

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
  /** RC text. On a comparative set (spec 047 FR-9) this is Passage A. */
  passage?: string
  /** Passage B of a comparative RC set; absent on a single-text passage. */
  passage_b?: string | null
  title_a?: string | null
  title_b?: string | null
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

// ---------------------------------------------------------------------------
// Solve guides (spec 045 schema, shipped to the static site by spec 046)
// ---------------------------------------------------------------------------

export type StepKind =
  | 'orient'
  | 'inventory'
  | 'symbolize'
  | 'diagram'
  | 'infer'
  | 'eliminate'
  | 'answer'

export interface SequenceRep {
  rep_type: 'sequence'
  slots: string[]
  entities: string[]
  placements: Record<string, string>
  exclusions: Record<string, string[]>
  note?: string | null
}

export interface GridCell {
  row: string
  column: string
  mark: 'yes' | 'no' | 'maybe'
  note?: string | null
}

export interface GridRep {
  rep_type: 'grid'
  rows: string[]
  columns: string[]
  cells: GridCell[]
  note?: string | null
}

export interface NotationRule {
  rule_text: string
  symbols: string
  note?: string | null
}

export interface NotationRep {
  rep_type: 'notation'
  rules: NotationRule[]
}

export interface ArgumentNode {
  id: string
  role: 'premise' | 'conclusion' | 'assumption' | 'objection'
  text: string
}

export interface ArgumentEdge {
  from: string
  to: string
  relation: 'supports' | 'opposes'
}

export interface ArgumentMapRep {
  rep_type: 'argument_map'
  nodes: ArgumentNode[]
  edges: ArgumentEdge[]
}

export interface PassageParagraph {
  paragraph: number
  role: string
  gist: string
}

export interface PassageMapRep {
  rep_type: 'passage_map'
  paragraphs: PassageParagraph[]
}

export type Representation =
  | SequenceRep
  | GridRep
  | NotationRep
  | ArgumentMapRep
  | PassageMapRep

export interface SolveStep {
  kind: StepKind
  title: string
  text: string
  representation?: Representation | null
  spoiler: boolean
}

export interface SolveGuide {
  question_id: string
  method: string
  steps: SolveStep[]
  version?: number
  source?: string | null
}

// ---------------------------------------------------------------------------
// Argumentative Writing (spec 047 schema)
// ---------------------------------------------------------------------------

export interface RubricBand {
  level: number
  label: string
  descriptor: string
}

export interface RubricCriterion {
  id: string
  name: string
  description: string
  weight: number
  look_for: string[]
  band_notes: Record<string, string>
}

export interface WritingRubric {
  id: string
  name: string
  version?: number
  summary: string
  bands: RubricBand[]
  criteria: RubricCriterion[]
  source?: string | null
}

export interface WritingPosition {
  id: string
  name: string
  summary: string
}

export interface WritingPerspective {
  id: string
  text: string
}

export interface ModelAnnotation {
  criterion_id: string
  note: string
}

export interface ModelResponse {
  position_id: string
  thesis: string
  essay: string
  annotations: ModelAnnotation[]
}

export interface SelfCheckItem {
  criterion_id: string
  prompt: string
}

export interface WritingPrompt {
  id: string
  title: string
  rubric_id: string
  difficulty: string
  issue: string
  context: string
  positions: WritingPosition[]
  perspectives: WritingPerspective[]
  task: string
  prewriting_minutes: number
  time_limit_minutes: number
  concepts?: string[]
  model_response: ModelResponse
  self_check: SelfCheckItem[]
  references?: Reference[]
  source?: string | null
}

export interface Content {
  schema_version: number | string
  generated_at: string
  counts: {
    total: number
    guides?: number
    /** Present since spec 047; WS has prompts rather than keyed questions. */
    writing_prompts?: number
  } & Record<SectionCode, number>
  sections: Section[]
  concepts: Concept[]
  passages: Passage[]
  questions: Question[]
  /** Present since spec 046; older artifacts predate solve guides. */
  guides?: SolveGuide[]
  /** Present since spec 047; older artifacts predate the writing section. */
  writing_rubrics?: WritingRubric[]
  writing_prompts?: WritingPrompt[]
}
