import HomeStats from '@/components/HomeStats'
import Link from 'next/link'

export default function Home() {
  return (
    <main className="relative">
      {/* Ambient gradient backdrop */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[600px] overflow-hidden"
      >
        <div className="absolute left-1/2 top-[-120px] h-[500px] w-[900px] -translate-x-1/2 rounded-full bg-blue-500/20 blur-[120px]" />
        <div className="absolute left-[20%] top-[60px] h-[300px] w-[300px] rounded-full bg-indigo-500/15 blur-[100px]" />
        <div className="absolute right-[15%] top-[120px] h-[260px] w-[260px] rounded-full bg-emerald-500/10 blur-[100px]" />
      </div>

      {/* Hero */}
      <section className="mx-auto max-w-7xl px-6 pb-12 pt-20">
        <div className="text-center">
          <a
            href="https://github.com"
            target="_blank"
            rel="noreferrer"
            className="group mx-auto inline-flex items-center gap-2 rounded-full border border-slate-700/60 bg-slate-900/60 px-3 py-1 text-xs text-slate-300 backdrop-blur transition hover:border-blue-500/50 hover:text-white"
          >
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            Open-source · Local-first · Audit-grade
            <span className="text-slate-500 transition group-hover:translate-x-0.5 group-hover:text-blue-300">
              →
            </span>
          </a>

          <h1 className="mt-8 bg-gradient-to-br from-white via-slate-100 to-slate-400 bg-clip-text text-7xl font-bold leading-[1.05] tracking-tight text-transparent sm:text-8xl">
            LawGraph AI
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-400 sm:text-xl">
            The open-source, agent-orchestrated legal intelligence platform.
            Multi-agent reasoning, Neo4j knowledge graphs, GraphRAG retrieval —
            all on your laptop.
          </p>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/agents"
              className="group inline-flex items-center gap-2 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-blue-500/30 transition hover:shadow-blue-500/50"
            >
              Open Agent Ops
              <span className="transition group-hover:translate-x-0.5">→</span>
            </Link>
            <Link
              href="/analysis"
              className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/60 px-5 py-2.5 text-sm font-semibold text-slate-200 backdrop-blur transition hover:border-slate-500 hover:text-white"
            >
              Try Analysis Studio
            </Link>
          </div>
        </div>

        <div className="mx-auto mt-14 max-w-4xl">
          <HomeStats />
        </div>
      </section>

      {/* Capabilities */}
      <section className="mx-auto max-w-7xl px-6 py-16">
        <SectionHeading
          eyebrow="Capabilities"
          title="Four surfaces, one platform"
          subtitle="Each module reads from the same provenance-tracked graph and audit log."
        />

        <div className="mt-10 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          <Card
            href="/agents"
            icon="🤖"
            title="Agent Ops"
            desc="Live registry, audit-grade run trail, BACKLOG triage, spec lifecycle."
            accent="blue"
            recommended
          />
          <Card
            href="/analysis"
            icon="📊"
            title="Analysis Studio"
            desc="Multi-agent legal analysis with traces, IRAC briefs, and precedents."
            accent="indigo"
          />
          <Card
            href="/graph"
            icon="🕸️"
            title="Knowledge Graph"
            desc="Interactive Cytoscape view of citations, doctrines, and case relationships."
            accent="emerald"
          />
          <Card
            href="/lsat"
            icon="🎓"
            title="LSAT Lab"
            desc="Adaptive practice grounded in real case law with rationale links."
            accent="amber"
          />
        </div>
      </section>

      {/* AO-SDLC pipeline */}
      <section className="mx-auto max-w-7xl px-6 py-16">
        <SectionHeading
          eyebrow="Workflow"
          title="The AO-SDLC chain"
          subtitle="Every non-trivial change runs the full spec-driven cycle. CI gates enforce it."
        />
        <ol className="mt-10 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {PIPELINE.map((step, i) => (
            <li
              key={step.label}
              className="group relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900/40 p-4 backdrop-blur transition hover:border-slate-700"
            >
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-slate-500">
                <span className="font-mono">0{i + 1}</span>
                <span>{step.phase}</span>
              </div>
              <div className="mt-2 font-mono text-sm text-blue-300">
                /{step.label}
              </div>
              <p className="mt-1 text-xs text-slate-400">{step.blurb}</p>
              {i < PIPELINE.length - 1 && (
                <span
                  aria-hidden
                  className="absolute right-2 top-1/2 hidden -translate-y-1/2 text-slate-700 lg:block"
                >
                  →
                </span>
              )}
            </li>
          ))}
        </ol>
      </section>

      {/* Tech stack */}
      <section className="mx-auto max-w-7xl px-6 py-16">
        <SectionHeading
          eyebrow="Built on"
          title="100% open-source stack"
          subtitle="No proprietary lock-in. Local Ollama for the runtime LLM. Everything auditable."
        />
        <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {STACK.map((item) => (
            <div
              key={item.name}
              className="rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3 backdrop-blur"
            >
              <div className="text-xs uppercase tracking-wider text-slate-500">
                {item.layer}
              </div>
              <div className="mt-0.5 font-medium text-slate-100">{item.name}</div>
              <div className="text-xs text-slate-500">{item.note}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-800/60">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-3 px-6 py-8 text-xs text-slate-500 sm:flex-row">
          <div>© 2026 LawGraph AI · Released under AGPL-3.0</div>
          <div className="flex items-center gap-4">
            <a href="https://github.com/bamr87/law-ai/blob/main/docs/architecture.md" target="_blank" rel="noopener noreferrer" className="hover:text-slate-300">Architecture</a>
            <a href="https://github.com/bamr87/law-ai/blob/main/docs/constitution.md" target="_blank" rel="noopener noreferrer" className="hover:text-slate-300">Constitution</a>
            <a href="https://github.com/bamr87/law-ai/blob/main/BACKLOG.md" target="_blank" rel="noopener noreferrer" className="hover:text-slate-300">BACKLOG</a>
            <a href="https://github.com/bamr87/law-ai" target="_blank" rel="noopener noreferrer" className="hover:text-slate-300">GitHub</a>
          </div>
        </div>
      </footer>
    </main>
  )
}

// ---------------------------------------------------------------------------

function SectionHeading({
  eyebrow,
  title,
  subtitle,
}: {
  eyebrow: string
  title: string
  subtitle: string
}) {
  return (
    <div className="text-center">
      <div className="text-xs uppercase tracking-[0.2em] text-blue-400/80">
        {eyebrow}
      </div>
      <h2 className="mt-2 text-3xl font-bold tracking-tight text-slate-100 sm:text-4xl">
        {title}
      </h2>
      <p className="mx-auto mt-3 max-w-2xl text-sm text-slate-400">
        {subtitle}
      </p>
    </div>
  )
}

function Card({
  href,
  icon,
  title,
  desc,
  accent,
  recommended,
}: {
  href: string
  icon: string
  title: string
  desc: string
  accent: 'blue' | 'indigo' | 'emerald' | 'amber'
  recommended?: boolean
}) {
  const accentClass: Record<string, string> = {
    blue: 'hover:border-blue-500/50 hover:shadow-blue-500/20',
    indigo: 'hover:border-indigo-500/50 hover:shadow-indigo-500/20',
    emerald: 'hover:border-emerald-500/50 hover:shadow-emerald-500/20',
    amber: 'hover:border-amber-500/50 hover:shadow-amber-500/20',
  }
  const accentGradient: Record<string, string> = {
    blue: 'from-blue-500/15',
    indigo: 'from-indigo-500/15',
    emerald: 'from-emerald-500/15',
    amber: 'from-amber-500/15',
  }
  return (
    <Link
      href={href}
      className={
        'group relative block overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur transition hover:shadow-2xl ' +
        accentClass[accent]
      }
    >
      <div
        aria-hidden
        className={
          'pointer-events-none absolute -right-12 -top-12 h-32 w-32 rounded-full bg-gradient-to-br to-transparent opacity-0 blur-2xl transition group-hover:opacity-100 ' +
          accentGradient[accent]
        }
      />
      {recommended && (
        <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-emerald-300">
          <span className="inline-block h-1 w-1 animate-pulse rounded-full bg-emerald-400" />
          Live
        </span>
      )}
      <div className="text-3xl">{icon}</div>
      <h3 className="mt-4 text-lg font-semibold text-slate-100 group-hover:text-white">
        {title}
      </h3>
      <p className="mt-2 text-sm text-slate-400">{desc}</p>
      <div className="mt-4 inline-flex items-center gap-1 text-xs text-slate-500 transition group-hover:text-slate-300">
        Open <span aria-hidden>→</span>
      </div>
    </Link>
  )
}

const PIPELINE = [
  { phase: 'Capture', label: 'specify', blurb: 'Draft the spec and FR/NFR/AC IDs.' },
  { phase: 'Resolve', label: 'clarify', blurb: 'Close every OPEN QUESTION.' },
  { phase: 'Design', label: 'plan', blurb: 'Architecture, files, test strategy.' },
  { phase: 'Decompose', label: 'tasks', blurb: 'Concrete T-N task breakdown.' },
  { phase: 'Ship', label: 'implement', blurb: 'Code + tests, gates green.' },
  { phase: 'Loop', label: 'evolve', blurb: 'Pick the next BACKLOG item.' },
] as const

const STACK = [
  { layer: 'LLM Runtime', name: 'Ollama', note: 'Llama 3.1 · Mistral · Phi-3' },
  { layer: 'Orchestration', name: 'CrewAI + LangGraph', note: 'Crews + stateful workflows' },
  { layer: 'Knowledge Graph', name: 'Neo4j Community', note: 'Cypher + GraphRAG' },
  { layer: 'API & UI', name: 'FastAPI · Next.js 15', note: 'Pydantic v2 · Tailwind' },
] as const
