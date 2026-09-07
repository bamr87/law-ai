import MatterList from '@/components/matters/MatterList'
import TaskCalendar from '@/components/matters/TaskCalendar'
import PageLayout from '@/components/shell/PageLayout'

export const metadata = {
  title: 'Matters · Law AI',
  description:
    'Your matters and their deadlines: the container each legal question’s research, authorities and tasks belong to.',
}

export default function MattersPage() {
  return (
    <PageLayout
      eyebrow="Workspace"
      title="Matters"
      accent="emerald"
      width="regular"
      description={
        <>
          A matter is one legal question you are working: the research, the
          authorities you verified, and the deadlines you set. Matters are
          per-account and never shared by a link.
        </>
      }
    >
      <div className="space-y-8">
        {/* TaskCalendar renders its own heading: signed out it has nothing to
            show, and the heading has to disappear with it. */}
        <TaskCalendar />
        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
            Your matters
          </h2>
          <MatterList />
        </section>
      </div>
    </PageLayout>
  )
}
