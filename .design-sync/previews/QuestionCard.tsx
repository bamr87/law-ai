import { QuestionCard } from 'law-ai-ui';

// Items are taken verbatim from the repo's own HITL-approved bank
// (lsat-static/content.json) so the card shows the real product content.

const LR_001 = {
  id: 'lr-001',
  section: 'LR' as const,
  type: 'LR',
  difficulty: 'easy',
  stem:
    'Every senior partner at the firm has argued at least one case before the state supreme court. Maria is a senior partner at the firm. Therefore, Maria has argued at least one case before the state supreme court.\n\nThe argument above is most similar in its reasoning to which one of the following?',
  choices: [
    { label: 'A', text: 'All birds have feathers. A penguin is a bird. So a penguin has feathers.' },
    { label: 'B', text: 'Most lawyers own at least one suit. Therefore, the lawyer next door owns a suit.' },
    { label: 'C', text: 'Anyone who passed the bar studied. Tom studied, so Tom passed the bar.' },
    { label: 'D', text: 'If it rains, the picnic is canceled. The picnic was canceled, so it rained.' },
    { label: 'E', text: 'No senator is under 30. Lin is 28, so Lin might be a senator.' },
  ],
  correct: 'A',
  explanation:
    "The original is a valid universal-instantiation argument: 'All P are Q; x is P; therefore x is Q.' Choice A has identical form. B uses 'most' (probabilistic). C affirms the consequent. D denies the antecedent reversed. E contradicts a universal.",
  source: 'original (CC0)',
  concepts: ['universal-instantiation', 'parallel-reasoning'],
  references: [
    {
      title: 'Khan Academy — Parallel Reasoning',
      url: 'https://www.khanacademy.org/prep/lsat/lsat-lessons/logical-reasoning/x60ba31fe60ad9ad8:parallel-reasoning/v/parallel-reasoning-1',
      note: null,
    },
  ],
  passage_id: null,
};

const RC_001 = {
  id: 'rc-001',
  section: 'RC' as const,
  type: 'RC',
  difficulty: 'med',
  stem: 'Which one of the following most accurately expresses the main point of the passage?',
  choices: [
    { label: 'A', text: 'Common-law courts have always preferred bright-line rules to flexible standards.' },
    { label: 'B', text: 'Modern federal procedure has eliminated all procedural barriers facing pro se litigants.' },
    { label: 'C', text: 'The drafters of the Federal Rules of Civil Procedure rejected the influence of the common-law tradition.' },
    { label: 'D', text: 'Twombly and Iqbal returned the federal courts to nineteenth-century pleading standards.' },
    { label: 'E', text: 'The shift from rigid pleading to notice pleading reflected a deliberate trade of doctrinal predictability for procedural access.' },
  ],
  correct: 'E',
  explanation:
    "The passage's central thesis is that the move to notice pleading was a *trade-off*: the drafters knowingly sacrificed some predictability to widen the courthouse door. E captures both halves. A overstates ('always'). B is contradicted by the closing paragraph.",
  source: 'original (CC0)',
  concepts: ['main-point'],
  passage_id: 'rc-passage-001',
};

const LG_001 = {
  id: 'lg-001',
  section: 'LG' as const,
  type: 'LG',
  difficulty: 'easy',
  stem: 'Which one of the following could be the order in which the associates argue, from first to fifth?',
  choices: [
    { label: 'A', text: 'F, G, H, J, K' },
    { label: 'B', text: 'G, F, H, K, J' },
    { label: 'C', text: 'K, F, H, J, G' },
    { label: 'D', text: 'F, H, K, J, G' },
    { label: 'E', text: 'H, F, G, J, K' },
  ],
  correct: 'D',
  explanation:
    'Apply the rules as eliminators. A puts F first and H third — not the required immediate F-H block (Rule 1). B places J fifth, violating Rule 2 (J fourth). C starts with K, violating Rule 3. E reverses the block, putting H before F (Rule 1). D satisfies all three.',
  source: 'original (CC0)',
  concepts: ['sequencing', 'elimination-grid'],
  passage_id: 'lg-game-001',
};

const LR_004 = {
  id: 'lr-004',
  section: 'LR' as const,
  type: 'LR',
  difficulty: 'hard',
  stem:
    'Editor: Our new policy requires every opinion piece to cite at least three primary sources. Critics claim this will reduce the diversity of viewpoints we publish, since fewer freelance writers have access to primary sources. But our submission rate has not dropped since the policy took effect, so the critics are mistaken.\n\nThe editor’s reasoning is most vulnerable to the criticism that it…',
  choices: [
    { label: 'A', text: 'treats a necessary condition as if it were sufficient.' },
    { label: 'B', text: 'assumes without warrant that all freelance writers lack primary sources.' },
    { label: 'C', text: 'fails to consider that some published pieces cite more than three sources.' },
    { label: 'D', text: 'infers a general rule from a single anecdote.' },
    { label: 'E', text: 'confuses the volume of submissions with the diversity of viewpoints in those submissions.' },
  ],
  correct: 'E',
  explanation:
    "The critics' claim is about *diversity of viewpoints*. The editor rebuts using *submission volume*. Equating the two is the flaw — submission count and viewpoint diversity are different measures, so E names it.",
  source: 'original (CC0)',
  concepts: ['equivocation', 'flaw-in-reasoning'],
  passage_id: null,
};

/** The canonical card: a Logical Reasoning item at the start of a drill. */
export function LogicalReasoning() {
  return <QuestionCard question={LR_001} index={0} total={70} />;
}

/** Reading Comprehension — wrapping multi-line choices, mid-drill counter. */
export function ReadingComprehension() {
  return <QuestionCard question={RC_001} index={12} total={37} />;
}

/** Logic Games — terse sequence choices, and the last item in its drill. */
export function LogicGames() {
  return <QuestionCard question={LG_001} index={18} total={19} />;
}

/**
 * A `hard` item — the difficulty pill shifts, and `onAnnounce` is wired to
 * receive the screen-reader strings the card emits as the user answers.
 */
export function HardFlawQuestion() {
  return (
    <QuestionCard
      question={LR_004}
      index={3}
      total={70}
      onAnnounce={(msg) => console.log('[a11y]', msg)}
    />
  );
}
