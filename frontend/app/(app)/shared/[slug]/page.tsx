import SharedAnalysisView from '@/components/SharedAnalysis'
import PageLayout from '@/components/shell/PageLayout'

export const metadata = {
  title: 'Shared analysis · Law AI',
  description: 'A shared Analysis Studio run, opened from its share link.',
}

/**
 * `/shared/<slug>` — the public face of a share link (BL-20260429-26).
 *
 * The slug is the only credential, so this page never assumes a session and
 * never offers an action: it renders the analysis and the mandatory
 * not-legal-advice disclaimer, and says "link not available" for anything the
 * backend refuses (revoked, archived, unshareable, or never minted — all
 * indistinguishable by design).
 */
export default async function SharedAnalysisPage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  return (
    <PageLayout
      eyebrow="Shared"
      title="Shared analysis"
      accent="emerald"
      width="regular"
      description="Someone shared this Analysis Studio run with you. It is a record of one AI-generated analysis, not advice."
    >
      <SharedAnalysisView slug={slug} />
    </PageLayout>
  )
}
