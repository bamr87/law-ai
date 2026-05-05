import LsatLab from '@/components/LsatLab'

export const metadata = {
  title: 'LSAT Lab · LawGraph AI',
  description:
    'Practice every LSAT section — Logical Reasoning, Reading Comprehension, Logic Games — with concept references and an open-source AI tutor.',
}

export default function LsatPage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-8">
        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-amber-400/80">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400" />
          Practice & study
        </div>
        <h1 className="mt-2 text-4xl font-bold tracking-tight text-slate-100">
          LSAT Lab
        </h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-400">
          A full LSAT workbench: drill Logical Reasoning, Reading
          Comprehension, and Logic Games against an open-source bank, browse
          the catalog of recurring reasoning patterns, and ask the local
          Ollama-powered tutor to walk you through any item. Every attempt
          and tutor invocation is auditable via{' '}
          <code className="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-300">
            /api/lsat/*
          </code>
          .
        </p>
      </header>
      <LsatLab />
    </div>
  )
}
