import LegalDisclaimerFooter from '@/components/LegalDisclaimer'
import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Law AI',
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
      <body className="flex min-h-screen flex-col bg-gradient-to-b from-slate-950 via-slate-950 to-slate-900 text-slate-200 antialiased">
        <div className="flex-1">{children}</div>
        <LegalDisclaimerFooter />
      </body>
    </html>
  )
}
