/**
 * Per-route scroll memory for the shell's main region.
 *
 * The shell locks the viewport and scrolls an inner element, which means the
 * browser's native scroll restoration (which only ever restores the document)
 * does nothing for us. Without this, every Back navigation dumps the user at
 * the top of a list they had scrolled halfway down.
 *
 * sessionStorage, not localStorage: a scroll offset is worth restoring within
 * a tab's lifetime and is noise a week later.
 */

const STORE_KEY = 'lawai.shell.scroll'

type Memory = Record<string, number>

function storage(): Storage | null {
  try {
    // Private-mode Safari and SSR both make this throw or return undefined.
    return typeof window === 'undefined' ? null : window.sessionStorage
  } catch {
    return null
  }
}

function read(store: Storage | null = storage()): Memory {
  if (!store) return {}
  try {
    const raw = store.getItem(STORE_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed))
      return {}
    const out: Memory = {}
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof v === 'number' && Number.isFinite(v) && v >= 0) out[k] = v
    }
    return out
  } catch {
    return {}
  }
}

/** Scroll offset previously recorded for `key`, or 0 for a first visit. */
export function recallScroll(
  key: string,
  store: Storage | null = storage(),
): number {
  return read(store)[key] ?? 0
}

/**
 * Record where the user is on `key`. A 0 offset is *deleted* rather than
 * stored — "top of the page" is the default, so keeping it only grows the
 * blob for no behavioural difference.
 */
export function rememberScroll(
  key: string,
  top: number,
  store: Storage | null = storage(),
): void {
  if (!store) return
  const mem = read(store)
  if (top <= 0) {
    if (!(key in mem)) return
    delete mem[key]
  } else {
    mem[key] = Math.round(top)
  }
  try {
    store.setItem(STORE_KEY, JSON.stringify(mem))
  } catch {
    /* quota or disabled storage — scroll memory is a nicety, never a failure */
  }
}

export function clearScrollMemory(store: Storage | null = storage()): void {
  try {
    store?.removeItem(STORE_KEY)
  } catch {
    /* ignore */
  }
}
