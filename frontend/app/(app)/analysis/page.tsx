import AnalysisStudio from '@/components/AnalysisStudio'
import PageLayout from '@/components/shell/PageLayout'

export const metadata = {
  title: 'Analysis Studio · Law AI',
  description:
    'Multi-agent legal analysis with IRAC briefs, precedents, and full provenance traces.',
}

export default function AnalysisPage() {
  return (
    <PageLayout
      eyebrow="Studio"
      title="Analysis Studio"
      accent="indigo"
      width="regular"
      description={
        <>
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
        </>
      }
    >
      <AnalysisStudio />
    </PageLayout>
  )
}
