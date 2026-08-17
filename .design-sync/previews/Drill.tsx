import { Drill } from 'law-ai-ui';

/**
 * Logical Reasoning drill — question card plus prev/next navigation and the
 * progress counter. LR items have no passage, so the panel is question-only.
 */
export function LogicalReasoningDrill() {
  return <Drill section="LR" />;
}

/**
 * Reading Comprehension — the two-column layout: passage panel beside the
 * question. This is the widest state the component renders.
 */
export function ReadingComprehensionDrill() {
  return <Drill section="RC" onAnnounce={(msg) => console.log('[a11y]', msg)} />;
}

/** Logic Games — the game setup and its constraint list sit beside the question. */
export function LogicGamesDrill() {
  return <Drill section="LG" />;
}
