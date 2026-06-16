import HomeStats from '@/components/HomeStats'
import { cn } from '@/lib/cn'
import {
  ArrowRight,
  Bot,
  GraduationCap,
  Network,
  Scale,
  type LucideIcon,
} from 'lucide-react'
import Link from 'next/link'

type Accent = 'brand' | 'accent' | 'success' | 'warning'

export default function Home() {
  return (
    <main className="relative">
      <section className="mx-auto max-w-7xl px-6 pb-12 pt-20">
        <div className="text-center">
          <a
            href="https://github.com/bamr87/law-ai"
            target="_blank"
            rel="noreferrer"
            className="group mx-auto inline-flex items-center gap-2 rounded-full border border-border bg-surface/60 px-3 py-1 text-xs text-muted backdrop-blur transition hover:border-brand/50 hover:text-ink"
          >
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
            Open-source · Local-first · Audit-grade
            <ArrowRight className="h-3.5 w-3.5 text-subtle transition group-hover:translate-x-0.5 group-hover:text-brand" />
          </a>

          <h1 className="mt-8 bg-gradient-to-br from-white via-slate-100 to-slate-400 bg-clip-text text-7xl font-bold leading-[1.05] tracking-tight text-transparent sm:text-8xl">
            LawGraph AI
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-lg text-muted sm:text-xl">
            The open-source, agent-orchestrated legal intelligence platform.
            Multi-agent reasoning, Neo4j knowledge graphs, GraphRAG retrieval —
            all on your laptop.
          </p>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/agents"
              className="group inline-flex items-center gap-2 rounded-lg bg-gradient-to-br from-brand to-brand-strong px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand/30 transition hover:shadow-brand/50"
            >
              Open Agent Ops
              <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/analysis"
              className="inline-flex items-center gap-2 rounded-lg border border-border-strong bg-surface/60 px-5 py-2.5 text-sm font-semibold text-ink backdrop-blur transition hover:border-brand/40"
            >
              Try Analysis Studio
            </Link>
          </div>
        </div>

        <div className="mx-auto mt-14 max-w-4xl">
          <HomeStats />
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-6 py-16">
        <SectionHeading
          eyebrow="Capabilities"
          title="Four surfaces, one platform"
          subtitle="Each module reads from the same provenance-tracked graph and audit log."
        />
        <div className="mt-10 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          <FeatureCard
            href="/agents"
            icon={Bot}
            title="Agent Ops"
            desc="Live registry, audit-grade run trail, BACKLOG triage, spec lifecycle."
            accent="brand"
            recommended
          />
          <FeatureCard
            href="/analysis"
            icon={Scale}
            title="Analysis Studio"
            desc="Multi-agent legal analysis with traces, IRAC briefs, and precedents."
            accent="accent"
          />
          <FeatureCard
            href="/graph"
            icon={Network}
            title="Knowledge Graph"
            desc="Interactive Cytoscape view of citations, doctrines, and case relationships."
            accent="success"
          />
          <FeatureCard
            href="/lsat"
            icon={GraduationCap}
            title="LSAT Lab"
            desc="Adaptive practice grounded in real case law with rationale links."
            accent="warning"
          />
        </div>
      </section>

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
              className="group relative overflow-hidden rounded-xl border border-border bg-surface/50 p-4 backdrop-blur transition hover:border-border-strong"
            >
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-subtle">
                <span className="font-mono">0{i + 1}</span>
                <span>{step.phase}</span>
              </div>
              <div className="mt-2 font-mono text-sm text-brand">
                /{step.label}
              </div>
              <p className="mt-1 text-xs text-muted">{step.blurb}</p>
              {i < PIPELINE.length - 1 && (
                <ArrowRight
                  aria-hidden
                  className="absolute right-2 top-1/2 hidden h-4 w-4 -translate-y-1/2 text-border-strong lg:block"
                />
              )}
            </li>
          ))}
        </ol>
      </section>

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
              className="rounded-lg border border-border bg-surface/50 px-4 py-3 backdrop-blur"
            >
              <div className="text-xs uppercase tracking-wide text-subtle">
                {item.layer}
              </div>
              <div className="mt-0.5 font-medium text-ink">{item.name}</div>
              <div className="text-xs text-subtle">{item.note}</div>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-border/60">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-3 px-6 py-8 text-xs text-subtle sm:flex-row">
          <div>© 2026 LawGraph AI · Released under AGPL-3.0</div>
          <div className="flex items-center gap-4">
            {FOOTER_LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                target="_blank"
                rel="noopener noreferrer"
                className="transition hover:text-ink"
              >
                {l.label}
              </a>
            ))}
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
      <div className="text-xs uppercase tracking-[0.2em] text-brand/80">
        {eyebrow}
      </div>
      <h2 className="mt-2 text-3xl font-bold tracking-tight text-ink sm:text-4xl">
        {title}
      </h2>
      <p className="mx-auto mt-3 max-w-2xl text-sm text-muted">{subtitle}</p>
    </div>
  )
}

const ACCENT_BORDER: Record<Accent, string> = {
  brand: 'hover:border-brand/50',
  accent: 'hover:border-accent/50',
  success: 'hover:border-success/50',
  warning: 'hover:border-warning/50',
}
const ACCENT_WASH: Record<Accent, string> = {
  brand: 'from-brand/15',
  accent: 'from-accent/15',
  success: 'from-success/15',
  warning: 'from-warning/15',
}
const ACCENT_ICON: Record<Accent, string> = {
  brand: 'bg-brand/15 text-brand',
  accent: 'bg-accent/15 text-accent',
  success: 'bg-success/15 text-success',
  warning: 'bg-warning/15 text-warning',
}

function FeatureCard({
  href,
  icon: Icon,
  title,
  desc,
  accent,
  recommended,
}: {
  href: string
  icon: LucideIcon
  title: string
  desc: string
  accent: Accent
  recommended?: boolean
}) {
  return (
    <Link
      href={href}
      className={cn(
        'group relative block overflow-hidden rounded-2xl border border-border bg-surface/60 p-6 backdrop-blur transition hover:shadow-[var(--shadow-pop)]',
        ACCENT_BORDER[accent],
      )}
    >
      <div
        aria-hidden
        className={cn(
          'pointer-events-none absolute -right-12 -top-12 h-32 w-32 rounded-full bg-gradient-to-br to-transparent opacity-0 blur-2xl transition group-hover:opacity-100',
          ACCENT_WASH[accent],
        )}
      />
      {recommended && (
        <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full border border-success/30 bg-success/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-success">
          <span className="inline-block h-1 w-1 animate-pulse rounded-full bg-success" />
          Live
        </span>
      )}
      <div
        className={cn(
          'inline-flex h-11 w-11 items-center justify-center rounded-xl',
          ACCENT_ICON[accent],
        )}
      >
        <Icon className="h-5 w-5" aria-hidden />
      </div>
      <h3 className="mt-4 text-lg font-semibold text-ink">{title}</h3>
      <p className="mt-2 text-sm text-muted">{desc}</p>
      <div className="mt-4 inline-flex items-center gap-1 text-xs text-subtle transition group-hover:text-muted">
        Open <ArrowRight className="h-3.5 w-3.5" aria-hidden />
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
  { layer: 'API & UI', name: 'Django · Next.js', note: 'DRF + Channels · Tailwind' },
] as const

const FOOTER_LINKS = [
  { href: 'https://github.com/bamr87/law-ai/blob/main/docs/architecture.md', label: 'Architecture' },
  { href: 'https://github.com/bamr87/law-ai/blob/main/docs/constitution.md', label: 'Constitution' },
  { href: 'https://github.com/bamr87/law-ai/blob/main/BACKLOG.md', label: 'BACKLOG' },
  { href: 'https://github.com/bamr87/law-ai', label: 'GitHub' },
] as const
