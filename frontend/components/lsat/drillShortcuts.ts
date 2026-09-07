import type { ShortcutGroup } from '@/lib/shell/shortcuts'

/**
 * The keys a drill card actually binds (`QuestionCard.handleKeyDown` and the
 * choice list's roving tabindex), published to the shell's `?` sheet
 * (BL-20260901-10).
 *
 * Wording is kept in step with the published static site's own reference
 * (`lsat-static/components/ShortcutHelp.tsx`) so the two products describe the
 * same drill the same way. It lists **only** what the platform binds — a
 * shortcut sheet that promises a key nothing listens to is worse than no sheet
 * at all — and since BL-20260901-06 that is the static site's whole drill map:
 * the letters and Enter, N/P between questions (BL-20260901-08), and the hint
 * keys H/J/K/R that `SolveAssist` now answers.
 *
 * One row is platform-only and says so here: `X` crosses a choice out
 * (BL-20260429-18). The static export has no tutor to coach against what was
 * ruled out, so the key would be decoration there — the sheet lists what this
 * product binds, not what the other one might.
 *
 * A module-level constant on purpose — `usePageShortcuts` identifies a group
 * by title and a new object per render would re-register on every render.
 */
export const LSAT_DRILL_SHORTCUTS: ShortcutGroup = {
  title: 'Question drill',
  rows: [
    { keys: 'A – E', label: 'Select that answer choice' },
    { keys: '↑ ↓', label: 'Move between choices (when a choice has focus)' },
    {
      keys: 'Home / End',
      label: 'First / last choice (when a choice has focus)',
    },
    {
      keys: 'X',
      label: 'Cross out the focused choice (the tutor coaches against it)',
    },
    { keys: 'Enter', label: 'Check the answer — then again to advance' },
    { keys: 'N', label: 'Next question, once this one is checked' },
    {
      keys: 'P',
      label: 'Previous question (Reading Comprehension / Logic Games)',
    },
    { keys: 'H', label: 'Reveal the next hint' },
    { keys: 'J / K', label: 'Move back / forward through revealed hints' },
    { keys: 'R', label: 'Reveal the final step (after checking)' },
  ],
}

/**
 * The keys the Argumentative Writing surface binds (BL-20260901-09).
 *
 * A separate group from the drill's because it is a different task with a
 * different hazard: the whole screen is a text field for 35 minutes, so the
 * only key that fires from inside it is `Ctrl`/`⌘`+`Enter` — a bare letter
 * would be swallowed by the essay.
 *
 * `Esc` is listed but is not bound through `lib/lsat/keyboard.ts`: the shell
 * owns Escape on every route, so the editor handles it on its own element.
 *
 * That is also where this row diverges from the static site's sheet, and the
 * divergence is deliberate (BL-20260905-41). `lsat-static` has no shell, so it
 * gives Escape two stages: the first press blurs the textarea, a second one
 * returns to the prompt list. Here the second press belongs to the shell —
 * chaining it to a page-registered handler would make one key mean two things
 * on every route — so the way back to the list is the "← All prompts" button,
 * and this row says so rather than promising a stage that does not exist.
 */
export const LSAT_WRITING_SHORTCUTS: ShortcutGroup = {
  title: 'Argumentative Writing',
  rows: [
    { keys: 'O', label: 'Open the first prompt, and jump into the editor' },
    { keys: 'T', label: 'Start or pause the writing clock' },
    { keys: 'Ctrl / ⌘ + Enter', label: 'Submit the draft and unlock feedback' },
    { keys: 'M', label: 'Show or hide the model response' },
    {
      keys: 'Esc',
      label: 'Leave the editor — O returns to it, “← All prompts” leaves it',
    },
  ],
}
