import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'LSAT Practice — LawGraph',
  description:
    'Serverless LSAT practice: Logical Reasoning drills, Reading Comprehension passages, and Logic Games with instant explanations. Openly licensed, runs entirely in your browser.',
  icons: {
    icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%E2%9A%96%EF%B8%8F%3C/text%3E%3C/svg%3E",
  },
}

export const viewport: Viewport = {
  themeColor: '#0f172a',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
