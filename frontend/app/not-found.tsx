import NotFoundReportLink from '@/components/shell/NotFoundReportLink'
import Link from 'next/link'

export const metadata = {
  title: 'Not found · Law AI',
}

export default function NotFound() {
  return (
    <main className="flex h-dvh flex-col items-center justify-center px-6 text-center">
      <p className="font-mono text-xs uppercase tracking-[0.3em] text-slate-500">
        404
      </p>
      <h1 className="mt-3 text-2xl font-bold tracking-tight text-slate-100">
        No such page
      </h1>
      <p className="mt-2 max-w-md text-sm text-slate-400">
        The route you followed is not part of Law AI. It may have moved with a
        spec, or the link may be mistyped.
      </p>
      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <Link
          href="/"
          className="rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:shadow-lg hover:shadow-blue-500/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
        >
          Back to the dashboard
        </Link>
        {/* A 404 that a reader can report is a broken link that gets fixed. The
         * route they asked for is context only this page has. */}
        <NotFoundReportLink />
      </div>
    </main>
  )
}
