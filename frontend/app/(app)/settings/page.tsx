import PageLayout from '@/components/shell/PageLayout'
import SettingsForm from '@/components/shell/SettingsForm'

export const metadata = {
  title: 'Settings · Law AI',
  description: 'Instance-scoped settings with inheritance provenance.',
}

export default function SettingsPage() {
  return (
    <PageLayout
      eyebrow="Instance"
      title="Settings"
      accent="slate"
      width="narrow"
      description="Values live on this instance. Org, team, and project scopes are not live — they wait on user accounts (spec 036). Every control names where its value came from. Override is explicit."
    >
      <SettingsForm />
    </PageLayout>
  )
}
