import ReviewQueue from '@/components/ReviewQueue'
import PageLayout from '@/components/shell/PageLayout'

export const metadata = {
  title: 'Review queue · Law AI',
}

export default function ReviewQueuePage() {
  return (
    <PageLayout
      eyebrow="Operations"
      title="Quarantine review queue"
      accent="blue"
      width="wide"
      description={
        <>
          Every ingested document the extractor was not confident about waits
          here for a human (constitution §5). Approving writes it to the
          knowledge graph through the same audited service Django admin and{' '}
          <code className="rounded bg-slate-800 px-1 py-0.5 font-mono text-xs">
            manage.py review_queue
          </code>{' '}
          use — the decision, its author, and its rationale are all recorded.
          Backed by{' '}
          <code className="rounded bg-slate-800 px-1 py-0.5 font-mono text-xs">
            /api/ingestion/reviews
          </code>
          .
        </>
      }
    >
      <ReviewQueue />
    </PageLayout>
  )
}
