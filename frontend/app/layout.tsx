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
      <body className="min-h-screen bg-canvas text-ink antialiased">
        {/* Ambient brand glow behind the whole app. */}
        <div
          aria-hidden
          className="pointer-events-none fixed inset-x-0 top-0 -z-10 h-[420px] bg-[radial-gradient(ellipse_60%_60%_at_50%_-10%,rgba(91,124,250,0.14),transparent_70%)]"
        />
        <Providers>
          <NavBar />
          {children}
        </Providers>
      </body>
    </html>
  )
}
