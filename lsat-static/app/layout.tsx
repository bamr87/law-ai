import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'LSAT Practice — Law AI',
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
      <body>
        {/* First tab stop. `main#view` has always been a focus target; nothing
            pointed at it until now. */}
        <a className="skip-link" href="#view">
          Skip to main content
        </a>
        {children}
        {/* UPL guardrail (BL-20260810-07). This site is aimed at prospective
            law students — laypeople — so the disclaimer ships on every page. */}
        <footer role="contentinfo" className="site-disclaimer">
          <p>
            <strong>Study aid, not legal advice.</strong> These practice
            questions and explanations are AI-assisted study material for LSAT
            preparation. They are not legal advice, do not describe the law of
            any jurisdiction, and create no attorney–client relationship.
          </p>
        </footer>
      </body>
    </html>
  )
}
