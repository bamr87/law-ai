import LsatLibrary from '@/components/LsatLibrary'
import PageLayout from '@/components/shell/PageLayout'

export const metadata = {
  title: 'LSAT Library · Law AI',
  description:
    'A reading and research library on the LSAT — exam architecture, section deep dives, every question family, technique, strategy, and review method.',
}

export default function LsatLibraryPage() {
  return (
    <PageLayout
      eyebrow="Practice & study"
      title="LSAT Library"
      accent="amber"
      width="wide"
      description={
        <>
          Long-form study material on how the exam is built and how each
          question family is solved — cross-linked to the concept catalog and
          to the drill bank, and maintained on a schedule by an HITL-gated
          review loop. Study aid only; this is LSAT preparation material, not
          legal advice.
        </>
      }
    >
      <LsatLibrary />
    </PageLayout>
  )
}
