'use client'

import {
  fetchIdentity,
  signIn,
  signOut,
  type AccountIdentity,
} from '@/lib/api'
import { reloadPage } from '@/lib/shell/reload'
import { useCallback, useEffect, useId, useRef, useState } from 'react'

/**
 * Sign in, and see who you are signed in as (BL-20260906-08).
 *
 * `/api/auth/login` shipped with spec 036 and nothing ever rendered a form for
 * it, so a session could only be obtained by logging into Django's `/admin/`
 * and coming back. Everything account-shaped in this app — the Share control
 * in the Analysis Studio, the matters screens, per-user settings — silently
 * required that. This is the missing surface, and it is deliberately the
 * smallest one that closes the gap: a masthead button, a username/password
 * form, and a way out.
 *
 * Two things it does not do. It does not register accounts — there is no
 * self-service signup endpoint, and inventing one in the client would be
 * pretending. And it never says *which* half of a credential was wrong: the
 * backend answers one "invalid credentials" for both, and repeating that
 * verbatim is what keeps this from being a username oracle.
 */
export default function AccountMenu() {
  // `null` while the first probe is in flight: neither signed in nor out yet,
  // and rendering "Sign in" during that window makes the button flicker for
  // every signed-in visitor on every load.
  const [identity, setIdentity] = useState<AccountIdentity | null>(null)
  const [open, setOpen] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const buttonRef = useRef<HTMLButtonElement | null>(null)
  const panelRef = useRef<HTMLDivElement | null>(null)
  const panelId = useId()

  useEffect(() => {
    let live = true
    fetchIdentity().then((me) => {
      if (live) setIdentity(me)
    })
    return () => {
      live = false
    }
  }, [])

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false)
    setError('')
    if (restoreFocus) buttonRef.current?.focus()
  }, [])

  // Escape and an outside click close it — the same contract every other
  // masthead popover keeps (`useMenuPopover`), which this cannot reuse because
  // its contents are a form, not a roving list of menu rows.
  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close(true)
    }
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node
      if (
        !panelRef.current?.contains(target) &&
        !buttonRef.current?.contains(target)
      ) {
        close(false)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('mousedown', onDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('mousedown', onDown)
    }
  }, [open, close])

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true)
    setError('')
    try {
      setIdentity(
        await signIn(
          String(form.get('username') ?? ''),
          String(form.get('password') ?? ''),
        ),
      )
      close(true)
      // A session changes what half this app is willing to fetch — matters,
      // the caller's own settings rows, the scope switcher's list. Those are
      // read once per load by components that never expected identity to
      // change under them, so the honest move after a sign-in is a reload
      // rather than a partial refresh that leaves some panels anonymous.
      reloadPage()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed.')
    } finally {
      setBusy(false)
    }
  }

  const onSignOut = async () => {
    setBusy(true)
    try {
      await signOut()
    } catch {
      /* the session is gone either way as far as this browser is concerned */
    }
    setBusy(false)
    close(true)
    reloadPage()
  }

  // Nothing at all until the probe answers, so the masthead does not shuffle.
  if (identity === null) return null

  const label = identity.authenticated
    ? (identity.username ?? 'Account')
    : 'Sign in'

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => (open ? close(false) : setOpen(true))}
        title={
          identity.authenticated
            ? `Signed in as ${identity.username ?? 'you'}`
            : 'Sign in to reach your matters and shared analyses'
        }
        className={
          'tap-target max-w-40 truncate rounded-md border px-2.5 text-xs transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 ' +
          (open
            ? 'border-blue-500/40 bg-blue-600/10 text-blue-200'
            : 'border-slate-700 text-slate-400 hover:border-blue-500/40 hover:text-white')
        }
      >
        {label}
      </button>

      {open && (
        <div
          ref={panelRef}
          id={panelId}
          role="dialog"
          aria-label="Account"
          data-testid="account-menu"
          style={{ zIndex: 'var(--z-popover)' }}
          className="absolute right-0 top-full mt-1 w-64 rounded-md border border-slate-700 bg-slate-900 p-3 shadow-xl"
        >
          {identity.authenticated ? (
            <div className="space-y-3">
              <p className="text-xs text-slate-300">
                Signed in as{' '}
                <span className="font-medium text-slate-100">
                  {identity.username}
                </span>
                {identity.is_staff && (
                  <span className="ml-1 rounded bg-slate-800 px-1 text-[10px] uppercase tracking-wider text-slate-400">
                    staff
                  </span>
                )}
              </p>
              <button
                type="button"
                onClick={onSignOut}
                disabled={busy}
                className="w-full rounded-md border border-slate-700 px-2 py-1.5 text-xs text-slate-300 transition hover:border-blue-500/40 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 disabled:opacity-50"
              >
                Sign out
              </button>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-2">
              <label className="block text-[11px] text-slate-400">
                Username
                <input
                  name="username"
                  autoComplete="username"
                  required
                  className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
                />
              </label>
              <label className="block text-[11px] text-slate-400">
                Password
                <input
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
                />
              </label>
              {error && (
                <p role="alert" className="text-[11px] text-rose-300">
                  {error}
                </p>
              )}
              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-md border border-blue-500/40 bg-blue-600/10 px-2 py-1.5 text-xs text-blue-200 transition hover:bg-blue-600/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 disabled:opacity-50"
              >
                {busy ? 'Signing in…' : 'Sign in'}
              </button>
              <p className="text-[10px] leading-snug text-slate-400">
                Accounts are created by an administrator. Signing in is what
                makes your matters and shared analyses reachable.
              </p>
            </form>
          )}
        </div>
      )}
    </div>
  )
}
