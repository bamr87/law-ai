import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createNavStore } from '../support/urlNav'
import LsatLab from '@/components/LsatLab'
import { __resetTimerStore, getTimerSnapshot } from '@/lib/lsat/timerStore'
import { server } from '@/mocks/server'

const nav = createNavStore('/lsat')

vi.mock('next/navigation', async () => {
  const { useSyncExternalStore } = await import('react')
  return {
    usePathname: () => nav.path,
    useSearchParams: () =>
      useSyncExternalStore(nav.subscribe, nav.read, nav.read),
    useRouter: () => ({ push: nav.push, replace: nav.replace }),
  }
})

const sampleSections = {
  count: 3,
  sections: [
    {
      code: 'LR',
      name: 'Logical Reasoning',
      description: 'Short arguments with question stems.',
      format: 'Short prompt + 5 choices',
      timing: '~35 min',
      scoring: 'Each item 1 pt',
      skills: ['identify conclusions'],
      tips: ['Diagram conditionals'],
      concepts: ['modus-tollens'],
      references: [
        { title: 'LSAC LR overview', url: 'https://example.test/lr' },
      ],
      question_count: 7,
    },
    {
      code: 'RC',
      name: 'Reading Comprehension',
      description: 'Long passages with linked questions.',
      format: 'Passage + 5–8 questions',
      timing: '~35 min',
      scoring: 'Each item 1 pt',
      skills: ['main point'],
      tips: ['Summarise each paragraph'],
      concepts: ['main-point'],
      references: [],
      question_count: 3,
    },
    {
      code: 'LG',
      name: 'Analytical Reasoning',
      description: 'Sequencing and grouping puzzles.',
      format: 'Setup + rules + 5–7 questions',
      timing: '~35 min',
      scoring: 'Each item 1 pt',
      skills: ['symbolize rules'],
      tips: ['Sketch every fixed slot'],
      concepts: ['sequencing'],
      references: [],
      question_count: 3,
    },
  ],
}

const sampleQuestion = {
  id: 'lr-001',
  section: 'LR',
  type: 'LR',
  difficulty: 'med',
  stem: 'All swans observed are white. Therefore all swans are white.',
  choices: [
    { label: 'A', text: 'Alpha' },
    { label: 'B', text: 'Bravo' },
    { label: 'C', text: 'Charlie' },
    { label: 'D', text: 'Delta' },
    { label: 'E', text: 'Echo' },
  ],
  concepts: ['flaw-in-reasoning'],
  references: [],
  passage_id: null,
}

const lgGames = [
  {
    id: 'lg-game-001',
    section: 'LG',
    title: 'Concert scheduling',
    summary: 'Seven acts, one stage.',
    passage: null,
    setup: 'Seven acts perform one at a time.',
    rules: ['A performs before B.'],
    source: 'Test',
  },
  {
    id: 'lg-game-002',
    section: 'LG',
    title: 'Office assignment',
    summary: 'Six staff, three rooms.',
    passage: null,
    setup: 'Six staff share three rooms.',
    rules: ['C shares with D.'],
    source: 'Test',
  },
]

const lgTagged = {
  ...sampleQuestion,
  id: 'lg-001',
  section: 'LG',
  type: 'LG',
  stem: 'Which order is possible?',
  concepts: ['sequencing'],
  passage_id: 'lg-game-001',
}

const lgUntagged = {
  ...sampleQuestion,
  id: 'lg-002',
  section: 'LG',
  type: 'LG',
  stem: 'Which pair must be grouped?',
  concepts: ['grouping-game'],
  passage_id: 'lg-game-001',
}

/**
 * A Logic Games bank where `sequencing` tags one question of one game
 * (BL-20260905-01). `/api/lsat/questions` answers the tag the way the API
 * does — with and without a `section`, since the lab asks it which section
 * carries the tag and the panel asks it which games do.
 */
function useLgConceptBank() {
  server.use(
    http.get('http://localhost:8000/api/lsat/questions', () =>
      HttpResponse.json({ count: 1, questions: [lgTagged] }),
    ),
    // BL-20260906-74: the concept filter is answered by this endpoint now,
    // so the double serves the same projection the server does — only the
    // game that carries the tag comes back when one is asked for.
    http.get('http://localhost:8000/api/lsat/passages', ({ request }) => {
      const concept = new URL(request.url).searchParams.get('concept')
      const passages = concept ? [lgGames[0]] : lgGames
      return HttpResponse.json({ count: passages.length, passages })
    }),
    http.get('http://localhost:8000/api/lsat/passages/lg-game-001', () =>
      HttpResponse.json({
        count: 2,
        passage: lgGames[0],
        questions: [lgTagged, lgUntagged],
      }),
    ),
  )
}

beforeEach(() => {
  // The timer store is module-level, so pace would leak between cases. So
  // would the URL, now that the active tab lives in it (BL-20260831-02).
  nav.reset()
  __resetTimerStore()
  server.use(
    http.get('http://localhost:8000/api/lsat/stats', () =>
      HttpResponse.json({
        attempts: 0,
        correct: 0,
        accuracy: 0,
        by_section: {},
      }),
    ),
    http.get('http://localhost:8000/api/lsat/sections', () =>
      HttpResponse.json(sampleSections),
    ),
    http.get('http://localhost:8000/api/lsat/questions', () =>
      HttpResponse.json({ count: 1, questions: [sampleQuestion] }),
    ),
    http.post('http://localhost:8000/api/lsat/grade', () =>
      HttpResponse.json({
        question_id: 'lr-001',
        correct: false,
        correct_choice: 'C',
        explanation: 'Hasty generalisation — sample bias.',
        section: 'LR',
        concepts: ['flaw-in-reasoning'],
      }),
    ),
    http.post('http://localhost:8000/api/lsat/tutor', () =>
      HttpResponse.json({
        question_id: 'lr-001',
        user_choice: 'A',
        correct_choice: 'C',
        is_correct: false,
        explanation: 'Hasty generalisation.',
        coaching: 'Walkthrough — the inductive leap is the flaw.',
        next_steps: ['Review sampling bias', 'Drill 5 more flaw items'],
        concepts: [
          {
            id: 'flaw-in-reasoning',
            name: 'Flaw in reasoning',
            sections: ['LR'],
            summary: 'Identify the logical defect.',
            detail: null,
            examples: [],
            see_also: [],
            references: [],
          },
        ],
        references: [],
        model: 'mistral:7b-instruct-q4_K_M',
        used_llm: true,
        confidence: 0.85,
        requires_human_review: false,
        latency_ms: 120,
      }),
    ),
    http.get('http://localhost:8000/api/lsat/concepts', () =>
      HttpResponse.json({
        count: 1,
        concepts: [
          {
            id: 'modus-tollens',
            name: 'Modus tollens',
            sections: ['LR'],
            summary: 'Deny the consequent to deny the antecedent.',
            detail: 'Deeper detail about modus tollens.',
            examples: ['If P then Q. Not Q. Therefore not P.'],
            see_also: ['contrapositive'],
            references: [
              { title: 'SEP — Logic', url: 'https://plato.stanford.edu/' },
            ],
          },
        ],
      }),
    ),
    http.get('http://localhost:8000/api/lsat/passages', () =>
      HttpResponse.json({
        count: 1,
        passages: [
          {
            id: 'rc-passage-001',
            section: 'RC',
            title: 'Federal pleading evolution',
            summary: 'Conley → Twombly → Iqbal.',
            passage: 'Long passage text.',
            setup: null,
            rules: [],
            source: 'Test',
          },
        ],
      }),
    ),
    http.get('http://localhost:8000/api/lsat/passages/rc-passage-001', () =>
      HttpResponse.json({
        count: 1,
        passage: {
          id: 'rc-passage-001',
          section: 'RC',
          title: 'Federal pleading evolution',
          summary: 'Conley → Twombly → Iqbal.',
          passage: 'Long passage text.',
          setup: null,
          rules: [],
          source: 'Test',
        },
        questions: [
          { ...sampleQuestion, id: 'rc-001', section: 'RC', type: 'RC' },
        ],
      }),
    ),
  )
})

/**
 * The grade round trip, awaited on purpose (BL-20260831-13, BL-20260905-02).
 *
 * Clicking Submit fires `POST /api/lsat/grade` through MSW and re-renders the
 * card from the response. Under a parallel vitest run that window has been
 * seen to exceed `waitFor`'s 1s default about once in ten runs, which is a
 * slow tick, not a regression — so the wait is explicit and generous, and the
 * suite's `testTimeout` (vitest.config.ts) leaves room for it. A genuinely
 * broken grade path still fails, five seconds later.
 *
 * Unhandled requests are already hard failures (`onUnhandledRequest: 'error'`
 * in vitest.setup.ts), so a grade URL that stops matching its handler surfaces
 * as an error rather than as a mysterious timeout here.
 */
const GRADED = /Incorrect — answer was C/

function awaitGraded() {
  return screen.findByText(GRADED, {}, { timeout: 5000 })
}

/**
 * Pick a choice and submit it, checking the two preconditions a stray timeout
 * would otherwise hide: the radio really is selected, and Submit really is
 * enabled. A click that lands before the radio state settles used to look
 * exactly like a slow grade.
 */
function gradeChoice(name: RegExp) {
  const radio = screen.getByRole('radio', { name })
  fireEvent.click(radio)
  expect(radio).toHaveAttribute('aria-checked', 'true')
  const submit = screen.getByRole('button', { name: /^Submit$/ })
  expect(submit).toBeEnabled()
  fireEvent.click(submit)
}

describe('LsatLab', () => {
  it('renders the section overview by default', async () => {
    render(<LsatLab />)
    await waitFor(() => {
      expect(screen.getAllByText('Logical Reasoning').length).toBeGreaterThan(0)
    })
    expect(screen.getByText(/four-section roadmap/i)).toBeInTheDocument()
    expect(screen.getAllByText('Reading Comprehension').length).toBeGreaterThan(
      0,
    )
    expect(screen.getByText('Analytical Reasoning')).toBeInTheDocument()
    // The section timer is docked in the sidebar by default (spec 043), so the
    // page itself no longer renders it. Dock behaviour is covered by
    // __tests__/shell/lsatTimerDock.test.tsx.
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()
  })

  it('sizes the section tabs as 44px tap targets', () => {
    // The switcher a student reaches for most, at a 390px viewport
    // (BL-20260831-11). Guarded mechanically by ux_audit R14.
    render(<LsatLab />)
    for (const tab of screen.getAllByRole('tab')) {
      expect(tab).toHaveClass('tap-target')
    }
  })

  it('opens the tab the URL names, and puts a tab change in history', async () => {
    // Deep-linked view state (BL-20260831-02): ?tab=RC is a shareable link,
    // and switching tabs is a history entry so Back returns to the last one.
    nav.reset('tab=RC')
    render(<LsatLab />)
    await waitFor(() =>
      expect(
        screen.getByRole('tab', { name: /Reading Comprehension/i }),
      ).toHaveAttribute('aria-selected', 'true'),
    )

    fireEvent.click(screen.getByRole('tab', { name: /Logic Games/i }))
    expect(nav.push).toHaveBeenCalled()
    expect(nav.hrefs[nav.hrefs.length - 1]).toBe('/lsat?tab=LG')
    expect(screen.getByRole('tab', { name: /Logic Games/i })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  it('falls back to the overview for a tab the URL invents', async () => {
    nav.reset('tab=NOPE')
    render(<LsatLab />)
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute(
        'aria-selected',
        'true',
      ),
    )
  })

  // BL-20260905-01: the library's concept catalog links "drill them in the
  // lab", and the lab used to open on Overview with the section still to be
  // found and the filter still to be applied by hand.
  describe('concept deep link', () => {
    it('opens LR filtered by the concept the URL names', async () => {
      const seen: string[] = []
      server.use(
        http.get('http://localhost:8000/api/lsat/questions', ({ request }) => {
          seen.push(request.url)
          return HttpResponse.json({ count: 1, questions: [sampleQuestion] })
        }),
      )
      nav.reset('concept=flaw-in-reasoning')
      render(<LsatLab />)

      await waitFor(() =>
        expect(
          screen.getByRole('tab', { name: /Logical Reasoning/i }),
        ).toHaveAttribute('aria-selected', 'true'),
      )
      await waitFor(() =>
        expect(seen.some((u) => u.includes('concept=flaw-in-reasoning'))).toBe(
          true,
        ),
      )
      expect(screen.getByText(/Drilling flaw-in-reasoning/)).toBeInTheDocument()
    })

    it('clears the filter from the chip, and stays on the drill', async () => {
      nav.reset('concept=flaw-in-reasoning')
      render(<LsatLab />)
      await waitFor(() =>
        expect(
          screen.getByText(/Drilling flaw-in-reasoning/),
        ).toBeInTheDocument(),
      )
      fireEvent.click(
        screen.getByRole('button', { name: 'Stop drilling flaw-in-reasoning' }),
      )
      await waitFor(() =>
        expect(
          screen.queryByText(/Drilling flaw-in-reasoning/),
        ).not.toBeInTheDocument(),
      )
      // Dropping the filter is not navigation: it replaces rather than pushes,
      // so Back still leaves the lab rather than re-applying a filter the
      // learner just dismissed.
      expect(nav.replace).toHaveBeenCalled()
      expect(nav.hrefs[nav.hrefs.length - 1]).toBe('/lsat?tab=LR')
    })

    it('says so when the concept has no questions, instead of a stray one', async () => {
      server.use(
        http.get('http://localhost:8000/api/lsat/questions', () =>
          HttpResponse.json({ count: 0, questions: [] }),
        ),
      )
      nav.reset('concept=unused-concept')
      render(<LsatLab />)
      expect(
        await screen.findByText(
          /No Logical Reasoning questions are tagged unused-concept yet/,
        ),
      ).toBeInTheDocument()
    })

    it('lets an explicit ?tab= win over the concept default', async () => {
      nav.reset('concept=flaw-in-reasoning&tab=stats')
      render(<LsatLab />)
      await waitFor(() =>
        expect(screen.getByRole('tab', { name: 'Stats' })).toHaveAttribute(
          'aria-selected',
          'true',
        ),
      )
    })

    // Two thirds of the concepts the bank tags carry no LR question at all,
    // and the library advertises a count over the whole bank — so a concept
    // link that always opened LR told the learner "no questions are tagged
    // sequencing" about a tag with 21 Logic Games questions behind it.
    it('opens the Logic Games drill for an LG-tagged concept, and drills only the tagged questions', async () => {
      useLgConceptBank()
      nav.reset('concept=sequencing')
      render(<LsatLab />)

      await waitFor(() =>
        expect(
          screen.getByRole('tab', { name: /Logic Games/i }),
        ).toHaveAttribute('aria-selected', 'true'),
      )
      expect(screen.getByText(/Drilling sequencing/)).toBeInTheDocument()
      // Never the LR panel's "nothing is tagged that" — the lie this fixes.
      expect(
        screen.queryByText(/No Logical Reasoning questions are tagged/),
      ).not.toBeInTheDocument()

      // Only the game that carries the tag is on offer…
      const select = await screen.findByLabelText('Game')
      await waitFor(() =>
        expect(within(select).getAllByRole('option')).toHaveLength(1),
      )
      expect(within(select).getByRole('option')).toHaveTextContent(
        'Concert scheduling',
      )
      // …and inside it, only the tagged question.
      expect(
        await screen.findByText(/Which order is possible/),
      ).toBeInTheDocument()
      expect(
        screen.queryByText(/Which pair must be grouped/),
      ).not.toBeInTheDocument()
      expect(screen.getByText('Question 1 of 1.')).toBeInTheDocument()
    })

    it('opens the Reading Comprehension drill for an RC-tagged concept', async () => {
      server.use(
        http.get('http://localhost:8000/api/lsat/questions', () =>
          HttpResponse.json({
            count: 1,
            questions: [
              {
                ...sampleQuestion,
                id: 'rc-001',
                section: 'RC',
                type: 'RC',
                concepts: ['rc-structure'],
                passage_id: 'rc-passage-001',
              },
            ],
          }),
        ),
      )
      nav.reset('concept=rc-structure')
      render(<LsatLab />)

      await waitFor(() =>
        expect(
          screen.getByRole('tab', { name: /Reading Comprehension/i }),
        ).toHaveAttribute('aria-selected', 'true'),
      )
      expect(screen.getByText(/Drilling rc-structure/)).toBeInTheDocument()
      expect(
        await screen.findByText('Federal pleading evolution'),
      ).toBeInTheDocument()
    })

    it('says so when no set in the section carries the tag', async () => {
      server.use(
        http.get('http://localhost:8000/api/lsat/questions', () =>
          HttpResponse.json({ count: 0, questions: [] }),
        ),
        // No passage carries the tag either (BL-20260906-74: the panel asks
        // the passages endpoint that question now).
        http.get('http://localhost:8000/api/lsat/passages', () =>
          HttpResponse.json({ count: 0, passages: [] }),
        ),
      )
      // An explicit tab, so this is the passage panel's own empty state and
      // not the section resolver falling back.
      nav.reset('concept=unused-concept&tab=RC')
      render(<LsatLab />)
      expect(
        await screen.findByText(
          /No Reading Comprehension questions are tagged unused-concept yet/,
        ),
      ).toBeInTheDocument()
      // With the way out the LR panel already offered.
      expect(
        screen.getByRole('button', { name: 'Drill the whole section instead' }),
      ).toBeInTheDocument()
    })
  })

  it('keeps the shell’s panel params when it writes its own', async () => {
    nav.reset('sidebar=0&tab=RC')
    render(<LsatLab />)
    fireEvent.click(screen.getByRole('tab', { name: /Logic Games/i }))
    const href = nav.hrefs[nav.hrefs.length - 1]
    expect(href).toContain('sidebar=0')
    expect(href).toContain('tab=LG')
  })

  it('switches to LR practice and grades a question', async () => {
    render(<LsatLab />)
    fireEvent.click(screen.getByRole('tab', { name: /Logical Reasoning/i }))

    await waitFor(() => {
      expect(screen.getByText(/All swans observed/)).toBeInTheDocument()
    })
    expect(screen.getByLabelText(/time on this question/i)).toHaveTextContent(
      '0:00',
    )

    gradeChoice(/A.*Alpha/)
    await awaitGraded()
    // Spec 045 FR-12: the author-rationale block with external source links
    // is gone — post-grade references resolve only to the concept catalog.
    // This supersedes the earlier assertion that the rationale text renders.
    expect(screen.queryByText(/Author rationale/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Hasty generalisation/)).not.toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: /LSAC LR overview/i }),
    ).not.toBeInTheDocument()
    await screen.findByText(/Derived from/i, {}, { timeout: 5000 })
    expect(
      (await screen.findAllByText('flaw-in-reasoning', {}, { timeout: 5000 }))
        .length,
    ).toBeGreaterThan(1)
    // Pace now lives in the timer store, because the timer can be docked in a
    // side panel — a different React subtree from this page (spec 043).
    expect(getTimerSnapshot().answered).toBe(1)
  })

  it('invokes the AI tutor when requested', async () => {
    render(<LsatLab />)
    fireEvent.click(screen.getByRole('tab', { name: /Logical Reasoning/i }))

    await waitFor(() =>
      expect(screen.getByText(/All swans observed/)).toBeInTheDocument(),
    )
    gradeChoice(/A.*Alpha/)
    await awaitGraded()

    fireEvent.click(screen.getByRole('button', { name: /Ask AI Tutor/ }))
    await screen.findByText(
      /Walkthrough — the inductive leap/,
      {},
      { timeout: 5000 },
    )
    expect(screen.getByText(/Review sampling bias/)).toBeInTheDocument()
  })

  it('labels an offline tutor answer as a fallback, not as a model', async () => {
    // The provider chain can answer from the deterministic fallback when no
    // tier is reachable (backend test_tutor_falls_back_when_no_provider_is
    // _reachable). The lab must say so rather than passing coaching off as a
    // model's, and must not print `fallback/offline` as if it were one
    // (BL-20260503-07).
    server.use(
      http.post('http://localhost:8000/api/lsat/tutor', () =>
        HttpResponse.json({
          question_id: 'lr-001',
          user_choice: 'A',
          correct_choice: 'C',
          is_correct: false,
          explanation: 'Hasty generalisation.',
          coaching: 'Offline coaching — compare the sample with the claim.',
          next_steps: ['Review sampling bias'],
          concepts: [],
          references: [],
          model: 'fallback/offline',
          used_llm: false,
          confidence: 0.55,
          requires_human_review: false,
          cached: false,
          latency_ms: 1,
        }),
      ),
    )

    render(<LsatLab />)
    fireEvent.click(screen.getByRole('tab', { name: /Logical Reasoning/i }))
    await screen.findByText(/All swans observed/, {}, { timeout: 5000 })

    gradeChoice(/A.*Alpha/)
    await awaitGraded()

    fireEvent.click(screen.getByRole('button', { name: /Ask AI Tutor/ }))
    expect(
      await screen.findByText(/offline fallback/, {}, { timeout: 5000 }),
    ).toBeInTheDocument()
    // The coaching still renders — a fallback answer is a real answer.
    expect(
      screen.getByText(/Offline coaching — compare the sample/),
    ).toBeInTheDocument()
    expect(screen.getByText(/55% conf/)).toBeInTheDocument()
    expect(screen.queryByText(/fallback\/offline/)).not.toBeInTheDocument()
    expect(
      screen.queryByText(/mistral:7b-instruct-q4_K_M/),
    ).not.toBeInTheDocument()
  })

  // The concept catalog is no longer a tab here — it moved into the library,
  // next to the articles that teach those concepts. Covered by
  // `__tests__/components/lsat/LsatLibrary.test.tsx`.
  it('offers no concept catalog tab, and points at the library instead', async () => {
    render(<LsatLab />)
    expect(
      screen.queryByRole('tab', { name: /^Concepts$/ }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /knowledge library/i }),
    ).toHaveAttribute('href', '/lsat/library')
  })

  it('renders RC passage + questions side by side', async () => {
    render(<LsatLab />)
    fireEvent.click(screen.getByRole('tab', { name: /Reading Comprehension/i }))
    await waitFor(() =>
      expect(
        screen.getByText('Federal pleading evolution'),
      ).toBeInTheDocument(),
    )
    // Passage detail loads via a second fetch after the list resolves —
    // wait for the body text instead of asserting synchronously.
    await waitFor(() =>
      expect(screen.getByText(/Long passage text/)).toBeInTheDocument(),
    )
    expect(screen.getByLabelText(/time on this question/i)).toHaveTextContent(
      '0:00',
    )
    // The pace denominator the docked clock divides by (BL-20260829-01): one
    // ungraded question in the open stack.
    await waitFor(() => expect(getTimerSnapshot().remainingQuestions).toBe(1), {
      timeout: 5000,
    })
  })

  it('paces LR against the bank the overview reports', async () => {
    render(<LsatLab />)
    fireEvent.click(screen.getByRole('tab', { name: /Logical Reasoning/i }))
    await waitFor(() =>
      expect(screen.getByText(/All swans observed/)).toBeInTheDocument(),
    )
    // 7 items in the LR bank per the sections fixture, none graded yet.
    await waitFor(() => expect(getTimerSnapshot().remainingQuestions).toBe(7), {
      timeout: 5000,
    })

    gradeChoice(/A.*Alpha/)
    await awaitGraded()
    await waitFor(() => expect(getTimerSnapshot().remainingQuestions).toBe(6), {
      timeout: 5000,
    })
  })

  it('stops quoting a pace once the student leaves the stack', async () => {
    render(<LsatLab />)
    fireEvent.click(screen.getByRole('tab', { name: /Reading Comprehension/i }))
    await waitFor(() => expect(getTimerSnapshot().remainingQuestions).toBe(1), {
      timeout: 5000,
    })

    // Back to a tab with no drill in it: a stale count would have the clock
    // quoting seconds-per-question for a stack that is no longer on screen.
    fireEvent.click(screen.getByRole('tab', { name: /Overview/i }))
    await waitFor(
      () => expect(getTimerSnapshot().remainingQuestions).toBeNull(),
      { timeout: 5000 },
    )
  })

  it('drives a whole LR drill from the keyboard, without losing focus', async () => {
    // The keyboard contract is bound to the card element, so *where focus is*
    // after each step is the test: a keystroke that lands on <body> reaches
    // nothing, which is how a mouse-free run used to stall after one question.
    let served = 0
    server.use(
      http.get('http://localhost:8000/api/lsat/questions', () => {
        served += 1
        return HttpResponse.json({
          count: 1,
          questions: [{ ...sampleQuestion, id: `lr-00${served}` }],
        })
      }),
    )

    render(<LsatLab />)
    fireEvent.click(screen.getByRole('tab', { name: /Logical Reasoning/i }))
    await waitFor(() =>
      expect(screen.getByText(/All swans observed/)).toBeInTheDocument(),
    )
    expect(screen.getByText('lr-001')).toBeInTheDocument()

    const alpha = screen.getByRole('radio', { name: /A.*Alpha/ })
    alpha.focus()
    fireEvent.keyDown(alpha, { key: 'b' })
    const bravo = screen.getByRole('radio', { name: /B.*Bravo/ })
    expect(bravo).toHaveAttribute('aria-checked', 'true')
    // The letter moves focus with the selection (BL-20260702-13): if focus
    // stayed on A, the Enter below would grade B while A is under the cursor,
    // which is the divergence this card used to have.
    expect(document.activeElement).toBe(bravo)

    fireEvent.keyDown(bravo, { key: 'Enter' })
    await awaitGraded()
    // Graded choices stay in the focus order. `disabled` would have thrown
    // focus to <body>, outside the element every shortcut is bound to.
    expect(bravo).toHaveAttribute('aria-disabled', 'true')
    expect(bravo).not.toBeDisabled()
    expect(document.activeElement).toBe(bravo)

    fireEvent.keyDown(bravo, { key: 'n' })
    await waitFor(() => expect(screen.getByText('lr-002')).toBeInTheDocument())
    // Focus followed the new question in, so the next keystroke has somewhere
    // to land.
    expect(document.activeElement).not.toBe(document.body)
    expect(document.activeElement).toHaveTextContent('lr-002')
  })

  it('opens the writing surface from the Overview card (BL-20260901-09)', async () => {
    server.use(
      http.get('http://localhost:8000/api/lsat/sections', () =>
        HttpResponse.json({
          count: sampleSections.sections.length + 1,
          sections: [
            ...sampleSections.sections,
            {
              code: 'WS',
              name: 'Argumentative Writing',
              description: 'One essay, no answer key.',
              format: 'Prompt + perspectives',
              timing: '35 min',
              scoring: 'Unscored, sent to schools',
              skills: ['take a position'],
              tips: ['Name the trade-off'],
              concepts: [],
              references: [],
              question_count: 0,
            },
          ],
        }),
      ),
    )

    render(<LsatLab />)
    await waitFor(() =>
      expect(screen.getByText('Argumentative Writing')).toBeInTheDocument(),
    )
    // WS used to have no tab, so its card said "No drill in the lab yet" and
    // the section was practisable only on the published static site.
    expect(
      screen.queryByText(/No drill in the lab yet/i),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Practice LR/i }),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Practice WS/i }))
    // The jump selects the real tab and mounts the real panel.
    expect(
      await screen.findByRole('tab', { name: 'Writing', selected: true }),
    ).toBeInTheDocument()
    expect(await screen.findByText('Municipal broadband')).toBeInTheDocument()
  })

  // BL-20260905-42: the lab refreshed the all-time stats only from a graded
  // MCQ, so an essay read against the rubric left the Stats tab's
  // Argumentative Writing card quoting the run before it.
  it('refreshes the all-time stats when a writing evaluation lands', async () => {
    window.localStorage.clear()
    let statsCalls = 0
    server.use(
      http.get('http://localhost:8000/api/lsat/stats', () => {
        statsCalls += 1
        return HttpResponse.json({
          attempts: 0,
          correct: 0,
          accuracy: 0,
          by_section: {},
          // The band only exists once the evaluation has been recorded.
          writing:
            statsCalls === 1
              ? undefined
              : {
                  attempts: 1,
                  by_prompt: { 'ws-broadband': 2.8 },
                  latest_band: 2.8,
                  best_band: 2.8,
                  band_trend: [2.8],
                  degraded: 0,
                  model: 'claude_code/claude-opus-5',
                  prompt_version: 'v1',
                },
        })
      }),
    )
    nav.reset('tab=WS')
    render(<LsatLab />)

    fireEvent.click(await screen.findByRole('button', { name: 'Open prompt' }))
    const editor = await screen.findByLabelText('Your response')
    fireEvent.change(editor, {
      target: {
        value: Array.from({ length: 60 }, (_, i) => `word${i}`).join(' '),
      },
    })
    fireEvent.click(
      screen.getByRole('button', { name: /Submit and unlock feedback/ }),
    )
    await screen.findByText('Self-check')
    // Submitting grades nothing, so nothing has refreshed yet.
    expect(statsCalls).toBe(1)

    fireEvent.click(
      screen.getByRole('button', { name: /Read my draft against the rubric/ }),
    )
    await waitFor(() => expect(statsCalls).toBe(2))

    fireEvent.click(screen.getByRole('tab', { name: 'Stats' }))
    expect(await screen.findByText('Latest band')).toBeInTheDocument()
    expect(screen.getAllByText('2.80').length).toBeGreaterThan(0)
  })
})
