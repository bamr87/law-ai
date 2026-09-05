import LsatLab from '@/components/LsatLab'
import PageLayout from '@/components/shell/PageLayout'

export const metadata = {
  title: 'LSAT Lab · Law AI',
  description:
    'Practice every LSAT section — Logical Reasoning, Reading Comprehension, Logic Games — with post-grade concept references and an open-source AI tutor.',
}

export default function LsatPage() {
  return (
    <PageLayout
      eyebrow="Practice & study"
      title="LSAT Lab"
      accent="amber"
      width="roomy"
      description={
        <>
          A full LSAT workbench: drill Logical Reasoning, Reading Comprehension,
          and Logic Games against an open-source bank, and ask the local
          Ollama-powered tutor to walk you through any item. The catalog of
          recurring reasoning patterns lives in the library, next to the
          articles that teach them. Every attempt and tutor invocation is
          auditable via{' '}
          <code className="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-300">
            /api/lsat/*
          </code>
          .
        </>
      }
    >
      <LsatLab />
    </PageLayout>
  )
}
