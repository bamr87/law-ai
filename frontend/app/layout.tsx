import NavBar from '@/components/NavBar'
import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'LexGraph AI',
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
      <body className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-950 to-slate-900 text-slate-200 antialiased">
        <NavBar />
        {children}
      </body>
    </html>
  )
}