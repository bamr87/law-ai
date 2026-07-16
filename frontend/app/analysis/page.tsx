import AnalysisStudio from '@/components/AnalysisStudio'

export const metadata = {
  title: 'Analysis Studio · Law AI',
  description:
    'Multi-agent legal analysis with IRAC briefs, precedents, and full provenance traces.',
}

export default function AnalysisPage() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <header className="mb-8">
        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-indigo-400/80">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-indigo-400" />
          Studio
        </div>
        <h1 className="mt-2 text-4xl font-bold tracking-tight text-slate-100">
          Analysis Studio
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-400">
          Paste a fact pattern and run the{' '}
          <code className="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-300">
            LegalAnalyst
          </code>{' '}
          and{' '}
          <code className="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-300">
            PrecedentHunter
          </code>{' '}
          crews in parallel. Every run is logged to the audit store with a HITL
          flag when confidence drops below 70%.
        </p>
      </header>
      <AnalysisStudio />
    </div>
  )
}
