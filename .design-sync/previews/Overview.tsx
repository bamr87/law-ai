import { Overview } from 'law-ai-ui';

/**
 * The LSAT landing view: intro copy plus one card per section, each with the
 * exam facts, timing, strategy tips and a start button. Content comes from the
 * app's own bundled question bank, so the counts are the real ones.
 */
export function SectionPicker() {
  return <Overview onStart={(section) => console.log('start drill:', section)} />;
}
