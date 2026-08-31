import AppShell from '@/components/shell/AppShell'
import type { ReactNode } from 'react'

export default function AppGroupLayout({
  children,
  sidebar,
  inspector,
}: {
  children: ReactNode
  sidebar: ReactNode
  inspector: ReactNode
}) {
  return (
    <AppShell sidebar={sidebar} inspector={inspector}>
      {children}
    </AppShell>
  )
}
