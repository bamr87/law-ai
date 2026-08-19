import { Stats } from 'law-ai-ui';

// Stats reads attempt history from localStorage, so an unseeded card only ever
// shows the empty state. Seeding at module scope (before React mounts) is what
// makes the populated view — the one worth looking at — renderable.
// Timestamps are fixed rather than Date.now()-derived so the card is
// deterministic across captures.
const T0 = 1_760_000_000_000;
const ATTEMPTS = [
  { qid: 'lr-001', section: 'LR', choice: 'A', correct: true, ts: T0 + 1_000 },
  { qid: 'lr-002', section: 'LR', choice: 'C', correct: true, ts: T0 + 2_000 },
  { qid: 'lr-003', section: 'LR', choice: 'B', correct: false, ts: T0 + 3_000 },
  { qid: 'lr-004', section: 'LR', choice: 'E', correct: true, ts: T0 + 4_000 },
  { qid: 'lr-005', section: 'LR', choice: 'D', correct: true, ts: T0 + 5_000 },
  { qid: 'lr-006', section: 'LR', choice: 'A', correct: false, ts: T0 + 6_000 },
  { qid: 'rc-001', section: 'RC', choice: 'E', correct: true, ts: T0 + 7_000 },
  { qid: 'rc-002', section: 'RC', choice: 'B', correct: true, ts: T0 + 8_000 },
  { qid: 'rc-003', section: 'RC', choice: 'A', correct: false, ts: T0 + 9_000 },
  { qid: 'lg-001', section: 'LG', choice: 'D', correct: true, ts: T0 + 10_000 },
  { qid: 'lg-002', section: 'LG', choice: 'C', correct: true, ts: T0 + 11_000 },
];

try {
  window.localStorage.setItem('lsat-practice.attempts.v1', JSON.stringify(ATTEMPTS));
} catch {
  /* storage disabled — the card falls back to the empty state */
}

/**
 * All-time and per-section accuracy after a learner has worked through part of
 * the bank: the hero percentage, the per-section table, and the guarded reset.
 */
export function WithProgress() {
  return <Stats />;
}
