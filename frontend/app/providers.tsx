'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'

/**
 * App-wide React Query provider. Centralises the data layer that every page
 * used to hand-roll with `useState` + `setInterval`. Sensible local-first
 * defaults: short stale time, background polling paused on hidden tabs,
 * one retry with backoff.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 3_000,
            gcTime: 5 * 60_000,
            retry: 1,
            refetchOnWindowFocus: false,
            // Polling hooks set their own refetchInterval; none of it runs
            // while the tab is hidden.
            refetchIntervalInBackground: false,
          },
          mutations: {
            retry: 0,
          },
        },
      }),
  )
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}
