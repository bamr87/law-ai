import AppShell from '@/components/shell/AppShell'
import SettingsServerSync from '@/components/shell/SettingsServerSync'
import {
  parseScopeId,
  parseSettingRows,
  SETTINGS_SCOPE_KEY,
  SETTINGS_STORAGE_KEY,
} from '@/lib/scope/rows'
import { cookies } from 'next/headers'
import type { ReactNode } from 'react'

/**
 * The shell, laid out the way this visitor chose — from the first paint.
 *
 * Layout preferences live in a localStorage-backed store the server cannot
 * read, so a hidden rail or a right-hand sidebar used to appear after
 * hydration and reflow the page on every full load. The store mirrors its rows
 * into the `law-ai.settings.v1` cookie; reading it here makes the server
 * render the same layout the client is about to (BL-20260905-09).
 *
 * Reading a cookie opts this route group out of static prerendering, which
 * costs nothing: the frontend runs as a Node server and every screen here is
 * dynamic anyway.
 */
export default async function AppGroupLayout({
  children,
  sidebar,
  inspector,
}: {
  children: ReactNode
  sidebar: ReactNode
  inspector: ReactNode
}) {
  const jar = await cookies()
  const rows = parseSettingRows(jar.get(SETTINGS_STORAGE_KEY)?.value)
  // Who those rows belong to. Layout preferences are written at `user:<pk>`
  // for a signed-in visitor (BL-20260905-10), and a resolver that walks the
  // instance scope alone skips them — which would put the reflow this layout
  // exists to prevent straight back.
  const userScopeId = parseScopeId(jar.get(SETTINGS_SCOPE_KEY)?.value)

  return (
    <AppShell
      sidebar={sidebar}
      inspector={inspector}
      initialSettings={rows}
      initialUserScopeId={userScopeId}
    >
      {/* Renders nothing; pulls server-persisted settings once (BL-20260830-07). */}
      <SettingsServerSync />
      {children}
    </AppShell>
  )
}
