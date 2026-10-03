import PlaybookBrowser from '@/components/lsat/PlaybookBrowser'
import PageLayout from '@/components/shell/PageLayout'

export const metadata = {
  title: 'LSAT Playbooks · Law AI',
  description:
    'Every LSAT question type: how the stem gives it away, what it asks, the method that solves it, and the traps the exam plants in the choices.',
}

export default function LsatPlaybooksPage() {
  return (
    <PageLayout
      eyebrow="Practice & study"
      title="Question-type playbooks"
      accent="amber"
      width="wide"
      description={
        <>
          The exam recycles a fixed set of question types, and each one signals
          itself in the stem. Here is the whole set: the phrasing that gives a
          type away, the task it sets, the method that works it, and the traps
          planted in its wrong answers. Turn on “Diagnose first” in the lab to
          be quizzed on them before every question. Study aid only; this is
          LSAT preparation material, not legal advice.
        </>
      }
    >
      <PlaybookBrowser />
    </PageLayout>
  )
}
