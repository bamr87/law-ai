import MatterWorkspace from '@/components/matters/MatterWorkspace'
import PageLayout from '@/components/shell/PageLayout'

export const metadata = {
  title: 'Matter · Law AI',
  description: 'One matter: its tasks, its study plan, and its export bundle.',
}

export default async function MatterPage({
  params,
}: {
  params: Promise<{ slug: string }>
}) {
  const { slug } = await params
  return (
    <PageLayout
      eyebrow="Workspace"
      title="Matter"
      accent="emerald"
      width="regular"
      description={
        <>
          Everything filed under this matter. The slug in this URL is only a
          request — the server resolves it against your own matters, so a slug
          that is not yours simply does not exist here.
        </>
      }
    >
      <MatterWorkspace slug={slug} />
    </PageLayout>
  )
}
