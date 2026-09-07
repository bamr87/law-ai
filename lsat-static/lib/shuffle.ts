/**
 * Per-attempt answer shuffling for the offline drill (BL-20260606-01).
 *
 * The platform shuffles on the server and hands the client a signed token to
 * reverse it. The static site has no server: the bundle carries the key, so
 * the permutation is drawn here and never leaves the browser. That is the same
 * trust model the site already has — grading is client-side too — and it fixes
 * the same defect: a question whose credited answer sits third forever teaches
 * position as well as reasoning.
 *
 * The order is drawn once per question **per session** and kept in memory, so
 * paging back through a section shows the board you answered rather than a new
 * one, and a reload is a new attempt with a new order.
 *
 * Mirrors `backend/law_ai/lsat/services/shuffle.py`: same relabelling, same
 * conservative label-reference remap, so an explanation reads correctly on
 * both products.
 */
import type { Question } from '@/lib/types'

export const LABELS = ['A', 'B', 'C', 'D', 'E'] as const

/** `order[i]` is the original index shown at display position `i`. */
export type Order = readonly number[]

const SESSION_ORDERS = new Map<string, Order>()

function draw(count: number): Order {
  const order = Array.from({ length: count }, (_, i) => i)
  for (let i = count - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[order[i], order[j]] = [order[j], order[i]]
  }
  return order
}

/** This session's order for a question, drawn on first sight. */
export function orderFor(questionId: string, count: number): Order {
  const existing = SESSION_ORDERS.get(questionId)
  if (existing && existing.length === count) return existing
  const order = draw(count)
  SESSION_ORDERS.set(questionId, order)
  return order
}

/** Test seam: forget every drawn order, so a case can control its own board. */
export function resetOrders(): void {
  SESSION_ORDERS.clear()
}

/**
 * Test seam: fix one question's order. A suite about the keyboard, or about a
 * saved answer, should not also be a suite about the shuffle — pinning the
 * identity order here keeps those cases asserting on the bank's own labels.
 */
export function presetOrder(questionId: string, order: Order): void {
  SESSION_ORDERS.set(questionId, order)
}

/** The identity order: the board exactly as the bank stores it. */
export function identityOrder(count: number): Order {
  return Array.from({ length: count }, (_, i) => i)
}

/** The stored label behind a label the learner saw. */
export function toCanonical(label: string, order: Order): string {
  const position = LABELS.indexOf(label as (typeof LABELS)[number])
  return position < 0 ? label : LABELS[order[position]]
}

/** Where a stored label ended up on screen. */
export function toDisplay(label: string, order: Order): string {
  const source = LABELS.indexOf(label as (typeof LABELS)[number])
  if (source < 0) return label
  const position = order.indexOf(source)
  return position < 0 ? label : LABELS[position]
}

/** `canonical label → displayed label`. */
export function displayMapping(order: Order): Record<string, string> {
  const map: Record<string, string> = {}
  order.forEach((source, position) => {
    map[LABELS[source]] = LABELS[position]
  })
  return map
}

// The shapes a label reference actually takes: "(B)", "choice C", and a bare
// label doing subject work ("A is correct", "B and C"). Everything else — the
// article "A", a name starting with one — is left alone.
const REFERENCE_PATTERNS: RegExp[] = [
  /\(([A-E])\)/g,
  /\b(?:choice|answer|option)\s+([A-E])\b/gi,
  /(?<![A-Za-z0-9(])([A-E])(?=\s*(?:is|are|was|were|and|or|remains|says|states)\b|\s*[,;:)/]|—|–)/g,
]

/**
 * Rewrite the label references in `text` through `mapping`, in one pass, so a
 * swap cannot rewrite the same reference twice.
 */
export function remapLabels(text: string, mapping: Record<string, string>): string {
  if (!text) return text
  const spans: Array<{ start: number; end: number; to: string }> = []
  for (const pattern of REFERENCE_PATTERNS) {
    pattern.lastIndex = 0
    let match = pattern.exec(text)
    while (match !== null) {
      const label = match[1]
      const start = match.index + match[0].indexOf(label)
      const end = start + label.length
      const overlaps = spans.some((s) => start < s.end && s.start < end)
      const to = mapping[label]
      if (!overlaps && to) spans.push({ start, end, to })
      match = pattern.exec(text)
    }
  }
  if (spans.length === 0) return text
  spans.sort((a, b) => a.start - b.start)
  let out = ''
  let cursor = 0
  for (const span of spans) {
    out += text.slice(cursor, span.start) + span.to
    cursor = span.end
  }
  return out + text.slice(cursor)
}

/** A question as this attempt shows it: choices relabelled, key and prose moved. */
export interface ShuffledQuestion {
  choices: Question['choices']
  correct: string
  explanation: string
  order: Order
  mapping: Record<string, string>
}

export function permuteQuestion(question: Question): ShuffledQuestion {
  const order = orderFor(question.id, question.choices.length)
  const mapping = displayMapping(order)
  return {
    choices: order.map((source, position) => ({
      ...question.choices[source],
      label: LABELS[position],
    })),
    correct: toDisplay(question.correct, order),
    explanation: remapLabels(question.explanation ?? '', mapping),
    order,
    mapping,
  }
}
