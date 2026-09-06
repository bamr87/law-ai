/**
 * The `localStorage` keys this site writes, in one place (BL-20260702-10).
 *
 * Attempts have always had `progress.ts`; the library's read marks and the
 * writing drafts were each a pair of private helpers inside the component that
 * owned them. That was fine until something needed to enumerate all of it —
 * export and restore — because the writing keys are per prompt, so there is no
 * fixed list to read: they have to be found by prefix.
 *
 * Every accessor is guarded. Private browsing and blocked site data both throw
 * on access, and per-device state is a convenience: the site has to read fine
 * without it.
 */

export const LIBRARY_READ_KEY = 'lsat-library-read'
export const WRITING_DRAFT_PREFIX = 'lsat-writing:draft:'
export const WRITING_SUBMITTED_PREFIX = 'lsat-writing:submitted:'

export function readLocal(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeLocal(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* storage unavailable — this session still works, it just is not saved */
  }
}

export function removeLocal(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    /* non-fatal */
  }
}

/** Every stored key starting with `prefix`. Empty where storage is blocked. */
export function keysWithPrefix(prefix: string): string[] {
  const found: string[] = []
  try {
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const key = window.localStorage.key(i)
      if (key?.startsWith(prefix)) found.push(key)
    }
  } catch {
    return []
  }
  return found
}

// --- knowledge library ------------------------------------------------------

/** Article ids the reader has marked read. */
export function readLibraryRead(): Set<string> {
  try {
    const raw = readLocal(LIBRARY_READ_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? new Set(parsed.map(String)) : new Set()
  } catch {
    return new Set()
  }
}

export function writeLibraryRead(ids: Set<string>): void {
  writeLocal(LIBRARY_READ_KEY, JSON.stringify([...ids].sort()))
}

// --- argumentative writing --------------------------------------------------

export function writingDraftKey(promptId: string): string {
  return `${WRITING_DRAFT_PREFIX}${promptId}`
}

export function writingSubmittedKey(promptId: string): string {
  return `${WRITING_SUBMITTED_PREFIX}${promptId}`
}

export interface WritingState {
  /** Prompt id → draft text. */
  drafts: Record<string, string>
  /** Prompt ids whose draft has been submitted. */
  submitted: string[]
}

/** Every draft and submission on this device, found by key prefix. */
export function readWritingState(): WritingState {
  const drafts: Record<string, string> = {}
  for (const key of keysWithPrefix(WRITING_DRAFT_PREFIX)) {
    const value = readLocal(key)
    if (value) drafts[key.slice(WRITING_DRAFT_PREFIX.length)] = value
  }
  const submitted: string[] = []
  for (const key of keysWithPrefix(WRITING_SUBMITTED_PREFIX)) {
    if (readLocal(key) === '1') {
      submitted.push(key.slice(WRITING_SUBMITTED_PREFIX.length))
    }
  }
  return { drafts, submitted: submitted.sort() }
}

/**
 * Write writing state back.
 *
 * `replace` clears the prompts this device knows about and the file does not —
 * otherwise "replace" would leave a draft behind and quietly make the device
 * disagree with the file it was just told to become.
 */
export function writeWritingState(state: WritingState, replace = false): void {
  if (replace) {
    const keep = new Set(Object.keys(state.drafts))
    const kept = new Set(state.submitted)
    for (const key of keysWithPrefix(WRITING_DRAFT_PREFIX)) {
      if (!keep.has(key.slice(WRITING_DRAFT_PREFIX.length))) removeLocal(key)
    }
    for (const key of keysWithPrefix(WRITING_SUBMITTED_PREFIX)) {
      if (!kept.has(key.slice(WRITING_SUBMITTED_PREFIX.length))) removeLocal(key)
    }
  }
  for (const [id, text] of Object.entries(state.drafts)) {
    writeLocal(writingDraftKey(id), text)
  }
  for (const id of state.submitted) writeLocal(writingSubmittedKey(id), '1')
}

// --- per-device preferences -------------------------------------------------

/**
 * Whether the reader pinned the site header open (BL-20260901-05).
 *
 * It lives here with the attempts and the drafts because it is stored the same
 * way, but it is deliberately *not* in the export snapshot (`lib/backup.ts`),
 * and that is the decision BL-20260905-16 asked for:
 *
 *  - **A preference is not progress.** The snapshot exists so a month of
 *    drilling survives a replaced phone. A restore is allowed to overwrite
 *    history — that is what `replace` means — and having it also reach over
 *    and re-answer "should this header hide on scroll?" for the device the
 *    file landed on would be a surprise, not a recovery. The pin is cheap to
 *    re-set and costs nothing when it is lost.
 *  - **The two products do not share a preference key shape**, and should not.
 *    The platform's preferences (`frontend/lib/settings/`) are scoped rows
 *    resolved user-over-instance and mirrored to a server; this site has no
 *    server and no account, so a scope chain here would be one scope with
 *    extra steps. A shared shape would only be worth its cost if a preference
 *    ever had to travel between the two, and none can: this site is a static
 *    export with no way to reach the platform.
 */
export const HEADER_PINNED_KEY = 'lsat-practice.header-pinned.v1'

export function readHeaderPinned(): boolean {
  // Private browsing and blocked site data both throw; the default stands.
  return readLocal(HEADER_PINNED_KEY) === '1'
}

export function writeHeaderPinned(pinned: boolean): void {
  writeLocal(HEADER_PINNED_KEY, pinned ? '1' : '0')
}
