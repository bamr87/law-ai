import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Law AI',
  description: 'Open-source agent-orchestrated legal intelligence platform',
  // The icon comes from `app/icon.svg` (App Router convention). The previous
  // `/favicon.ico` reference pointed at a file that was never added, so every
  // page load logged a 404.
}

export const viewport = {
  // The shell is viewport-locked; letting the page zoom-pan on iOS would let
  // a user scroll the chrome off screen with no way to scroll it back.
  width: 'device-width',
  initialScale: 1,
  // Zoom stays enabled — capping it fails WCAG 1.4.4.
  maximumScale: 5,
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="h-full">
      {/* `h-full` + `overflow-hidden`: the document never scrolls. The shell
       * owns scrolling so its chrome cannot be scrolled away, and the UPL
       * disclaimer footer moves inside the shell's scroll region with it. */}
      <body className="h-full overflow-hidden bg-gradient-to-b from-slate-950 via-slate-950 to-slate-900 text-slate-200 antialiased">
        {children}
      </body>
    </html>
  )
}
