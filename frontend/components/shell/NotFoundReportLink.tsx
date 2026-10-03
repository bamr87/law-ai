'use client'

import { usePathname } from 'next/navigation'
import { openFeedback } from './FeedbackButton'

/**
 * "Report this link" on the 404 route.
 *
 * Split out as a client component so `app/not-found.tsx` stays a server
 * component — Next renders the root not-found for unmatched routes, and making
 * the whole page client-side to get one button would cost that.
 *
 * The route that failed is the only thing this page knows and the widget does
 * not, so it hands it over pre-filled rather than asking the reader to retype
 * a URL they arrived at by following a broken link.
 */
export default function NotFoundReportLink() {
  const pathname = usePathname() || ''

  return (
    <button
      type="button"
      onClick={() =>
        openFeedback({
          type: 'fix-page',
          description: `This route returned 404: ${pathname}`,
          extra:
            typeof document !== 'undefined' && document.referrer
              ? `Linked from: ${document.referrer}`
              : '',
        })
      }
      className="rounded-lg border border-slate-700 px-5 py-2.5 text-sm font-semibold text-slate-300 transition hover:border-slate-500 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
    >
      Report this link
    </button>
  )
}
