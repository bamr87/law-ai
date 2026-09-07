import AccountData from '@/components/matters/AccountData'
import PageLayout from '@/components/shell/PageLayout'

export const metadata = {
  title: 'Your data · Law AI',
  description:
    'Export everything this instance holds about you, or delete your account.',
}

export default function AccountDataPage() {
  return (
    <PageLayout
      eyebrow="Workspace"
      title="Your data"
      accent="slate"
      width="narrow"
      description={
        <>
          Portability and deletion. Export is a single JSON bundle; deletion
          archives your matters and de-identifies the audit records they
          touched rather than erasing them.
        </>
      }
    >
      <AccountData />
    </PageLayout>
  )
}
