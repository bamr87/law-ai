import { describe, expect, it } from 'vitest'

import { content, playbookFor, guideFor } from '@/lib/data'

describe('playbooks catalog (#126)', () => {
  it('ships strategies, traps, and one item per archetype stamp in the bank', () => {
    const catalog = content.playbooks
    expect(catalog).toBeDefined()
    expect(catalog!.strategies.length).toBeGreaterThan(0)
    expect(catalog!.traps.length).toBeGreaterThan(0)
    expect(catalog!.items.length).toBe(content.counts.playbooks)

    const stamped = new Set(
      content.questions.map((q) => q.archetype).filter(Boolean) as string[],
    )
    for (const id of stamped) {
      expect(playbookFor(id), `missing playbook for stamped ${id}`).toBeDefined()
    }
  })

  it('omits cue_patterns from learner items', () => {
    for (const item of content.playbooks?.items ?? []) {
      expect(item).not.toHaveProperty('cue_patterns')
      expect(item.cues.length).toBeGreaterThan(0)
      expect(item.task.length).toBeGreaterThan(0)
      expect(item.method.length).toBeGreaterThan(0)
      expect(item.strategies.length).toBeGreaterThan(0)
      expect(item.traps.length).toBeGreaterThan(0)
    }
  })

  it('still serves authored guides when present', () => {
    const withGuide = content.guides?.[0]
    if (!withGuide) return
    expect(guideFor(withGuide.question_id)?.steps.length).toBeGreaterThan(0)
  })
})
