import NavBar from '@/components/NavBar'
import type { Metadata } from 'next'
import { Providers } from './providers'
import './globals.css'

export const metadata: Metadata = {
  title: 'LawGraph AI',
  description: 'Open-source agent-orchestrated legal intelligence platform',
  icons: {
    icon: '/favicon.ico',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="antialiased">
        <Providers>
          {/* Centered, side-bordered column — the shared EDGAR shell. */}
          <div className="mx-auto flex min-h-svh max-w-[1200px] flex-col border-x border-border">
            <NavBar />
            {children}
          </div>
        </Providers>
      </body>
    </html>
  )
}
