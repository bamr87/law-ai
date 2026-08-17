import { PassagePanel } from 'law-ai-ui';
import { passageById } from '../../lsat-static/lib/data';

// Pulled from the app's own bundled bank rather than copied, so these stay in
// lockstep with content.json.
const RC_PASSAGE = passageById('rc-passage-001')!;
const LG_GAME = passageById('lg-game-001')!;

/** Reading Comprehension: a prose passage with title and summary. */
export function ReadingPassage() {
  return <PassagePanel passage={RC_PASSAGE} />;
}

/**
 * Logic Games: the same panel rendering a game setup instead of prose — the
 * numbered constraint list is the structural difference worth seeing.
 */
export function LogicGameSetup() {
  return <PassagePanel passage={LG_GAME} />;
}
