import SettingsForm from '@/components/shell/SettingsForm'

export const metadata = {
  title: 'Settings · Law AI',
  description: 'Instance-scoped settings with inheritance provenance.',
}

export default function SettingsPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-8">
      <header className="mb-8">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-500">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-400" />
          Instance
        </div>
        <h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-100">
          Settings
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-400">
          Values live on this instance. Org, team, and project scopes are not
          live — they wait on user accounts (spec 036). Every control names
          where its value came from. Override is explicit.
        </p>
      </header>
      <SettingsForm />
    </main>
  )
}
