'use client'

import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useRef, useState } from 'react'
import { panelHref } from './panels'

/**
 * View state that lives in the URL (BL-20260831-02).
 *
 * Spec 041 made Back and sharing work *across* the shell — the panel layout is
 * in the query string, so a link carries it. Inside a screen they did not: the
 * LSAT Lab tab, the Agent Ops run filters, and the selected case were ordinary
 * `useState`, so Back left the screen entirely and a link to "the RC tab" or
 * "this case" could not be written.
 *
 * These hooks put that state where the panel state already is. They compose
 * with it rather than fighting it: every writer starts from the *current*
 * `useSearchParams` and only touches its own key, so `?sidebar=0&tab=RC` is a
 * perfectly ordinary URL and neither half clobbers the other.
 *
 * The keys are reserved app-wide (see `panels.ts`) so two screens on the same
 * route can never mean different things by `tab`.
 */
export const VIEW_KEYS = [
  'tab',
  'type',
  'q',
  'case',
  'compare',
  // The LSAT lab's concept filter (BL-20260905-01): the library's catalog
  // links `/lsat?concept=<id>` so a tag reaches practice in one step.
  'concept',
  // The lab's question-type filter (spec 053): a playbook's "drill this type"
  // link is `/lsat?tab=LR&archetype=<id>`.
  'archetype',
  // A specific question to open the LR drill on (spec 054): the contrast
  // panel's "try the same argument as a Strengthen question" link.
  'question',
] as const

export type ViewKey = (typeof VIEW_KEYS)[number]

/** Query string with one view key set, or removed when `value` is null. */
export function withViewParam(
  params: URLSearchParams,
  key: ViewKey,
  value: string | null,
): string {
  const next = new URLSearchParams(params.toString())
  if (value === null || value === '') next.delete(key)
  else next.set(key, value)
  return next.toString()
}

/**
 * One view key, validated. A value outside `allowed` — a stale link, a
 * hand-edited URL — reads as the fallback rather than putting the screen in a
 * state it cannot render.
 */
export function readViewParam<T extends string>(
  params: URLSearchParams | null,
  key: ViewKey,
  fallback: T,
  allowed?: readonly T[],
): T {
  const raw = params?.get(key) ?? null
  if (raw === null || raw === '') return fallback
  if (!allowed) return raw as T
  return allowed.includes(raw as T) ? (raw as T) : fallback
}

interface UrlStateOptions<T extends string> {
  fallback: T
  /** Closed set of values, when there is one. */
  allowed?: readonly T[]
  /**
   * `push` (the default) puts a discrete choice — a tab, a selected case — in
   * history so Back steps through it. `replace` is for state a user does not
   * mean to navigate, like a filter they are still typing.
   */
  mode?: 'push' | 'replace'
}

/**
 * A discrete choice, stored in the URL. Reads from the query string, writes
 * back to it; the param is dropped when the value is the fallback, so a
 * default view has a clean URL.
 */
export function useUrlState<T extends string>(
  key: ViewKey,
  { fallback, allowed, mode = 'push' }: UrlStateOptions<T>,
): [T, (next: T) => void] {
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname() || '/'
  const value = readViewParam(params, key, fallback, allowed)

  const set = useCallback(
    (next: T) => {
      const query = withViewParam(
        new URLSearchParams(params?.toString() ?? ''),
        key,
        next === fallback ? null : next,
      )
      const href = panelHref(pathname, query)
      // `scroll: false`: this is a change of view *within* a screen, and
      // jumping the reader to the top of it is not what they asked for.
      if (mode === 'replace') router.replace(href, { scroll: false })
      else router.push(href, { scroll: false })
    },
    [fallback, key, mode, params, pathname, router],
  )

  return [value, set]
}

/**
 * Write several view keys in one navigation.
 *
 * `useUrlState`'s setter reads the *current* params and touches one key, which
 * is what keeps two screens' keys from clobbering each other — but it means two
 * setters called from the same handler both start from the same snapshot and
 * the second wins. A screen whose keys are coupled (the LSAT lab's `concept`
 * decides where `tab` defaults, BL-20260905-01) has to move them together, or
 * dropping one silently resets the other.
 *
 * `null` removes a key, exactly as `withViewParam` does.
 */
export function useUrlWrite(
  mode: 'push' | 'replace' = 'push',
): (updates: Partial<Record<ViewKey, string | null>>) => void {
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname() || '/'

  return useCallback(
    (updates) => {
      let query = new URLSearchParams(params?.toString() ?? '')
      for (const [key, value] of Object.entries(updates)) {
        query = new URLSearchParams(
          withViewParam(query, key as ViewKey, value ?? null),
        )
      }
      const href = panelHref(pathname, query.toString())
      if (mode === 'replace') router.replace(href, { scroll: false })
      else router.push(href, { scroll: false })
    },
    [mode, params, pathname, router],
  )
}

/**
 * Free text, stored in the URL — a filter box.
 *
 * The input stays instant (local state) and the URL catches up after a pause,
 * with `replace` rather than `push`: one history entry per keystroke would
 * make Back useless, which is the thing this whole item is trying to fix.
 */
export function useUrlText(
  key: ViewKey,
  { debounceMs = 300 }: { debounceMs?: number } = {},
): [string, (next: string) => void] {
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname() || '/'
  const fromUrl = readViewParam<string>(params, key, '')

  const [draft, setDraft] = useState(fromUrl)
  const typed = useRef(false)

  // A URL change the user did not type — Back, or a shared link — wins.
  useEffect(() => {
    if (!typed.current) setDraft(fromUrl)
  }, [fromUrl])

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    [],
  )

  const set = useCallback(
    (next: string) => {
      typed.current = true
      setDraft(next)
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => {
        typed.current = false
        const query = withViewParam(
          new URLSearchParams(params?.toString() ?? ''),
          key,
          next,
        )
        router.replace(panelHref(pathname, query), { scroll: false })
      }, debounceMs)
    },
    [debounceMs, key, params, pathname, router],
  )

  return [draft, set]
}
