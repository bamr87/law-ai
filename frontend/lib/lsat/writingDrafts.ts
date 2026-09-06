'use client'

/**
 * Per-browser storage for Argumentative Writing drafts (BL-20260901-09).
 *
 * A 35-minute essay must survive a refresh, a stray Back, and a closed tab.
 * It is not sent anywhere: the platform posts a *finished* draft to
 * `/api/lsat/writing/evaluate` when the learner asks for feedback, and until
 * then the text stays in this browser — the same contract `lsat-static` gives
 * (`lib/deviceState.ts`), down to the key prefixes, so a learner who drafts on
 * the published site and then opens the lab finds their work.
 *
 * Every access is guarded: private browsing and blocked site data both throw,
 * and a lost draft is a worse outcome than a lost feature, but neither may
 * break the page.
 */

export const WRITING_DRAFT_PREFIX = 'lsat-writing:draft:'
export const WRITING_SUBMITTED_PREFIX = 'lsat-writing:submitted:'

export const writingDraftKey = (promptId: string): string =>
  `${WRITING_DRAFT_PREFIX}${promptId}`

export const writingSubmittedKey = (promptId: string): string =>
  `${WRITING_SUBMITTED_PREFIX}${promptId}`

function safeGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSet(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* non-fatal */
  }
}

/** The draft held for a prompt, or '' when there is none. */
export function loadWritingDraft(promptId: string): string {
  return safeGet(writingDraftKey(promptId)) ?? ''
}

export function saveWritingDraft(promptId: string, draft: string): void {
  safeSet(writingDraftKey(promptId), draft)
}

/**
 * Whether this browser has already submitted a draft for the prompt.
 *
 * Submitting is what unlocks the rubric band notes and the annotated model
 * response, so it has to outlive the tab: coming back to a prompt you have
 * already written must not re-lock the feedback you earned.
 */
export function loadWritingSubmitted(promptId: string): boolean {
  return safeGet(writingSubmittedKey(promptId)) === '1'
}

export function saveWritingSubmitted(promptId: string): void {
  safeSet(writingSubmittedKey(promptId), '1')
}
