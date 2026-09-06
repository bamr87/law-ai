'use client'

/**
 * Renders the typed blocks that `library.py` compiles articles into.
 *
 * There is deliberately no Markdown parser and no `dangerouslySetInnerHTML`
 * anywhere in this file. The backend closed the article dialect and emits a
 * typed tree; this component's whole job is to map block and span kinds onto
 * elements (spec 048 FR-2/FR-11, NFR-SAFETY-1). A construct the backend
 * cannot parse never reaches here, and a block type this file does not know
 * renders as nothing rather than as escaped source.
 *
 * `lsat-static/components/library/BlockRenderer.tsx` is the offline twin.
 * The two must cover the same block-type set; `tests/test_lsat_site.py`
 * asserts it.
 */

import type {
  LsatBlock,
  LsatCalloutBlock,
  LsatCalloutVariant,
  LsatCell,
  LsatListBlock,
  LsatNotationBlock,
  LsatParagraphBlock,
  LsatSpan,
  LsatTableBlock,
} from '@/lib/api'

export interface CrossRefHandlers {
  /** Follow an `[[article:id]]` reference. */
  onArticle?: (articleId: string) => void
}

const CALLOUT_STYLE: Record<
  LsatCalloutVariant,
  { border: string; label: string; glyph: string }
> = {
  example: { border: 'border-l-sky-500 bg-sky-500/5', label: 'text-sky-300', glyph: '◆' },
  trap: { border: 'border-l-rose-500 bg-rose-500/5', label: 'text-rose-300', glyph: '▲' },
  tip: {
    border: 'border-l-emerald-500 bg-emerald-500/5',
    label: 'text-emerald-300',
    glyph: '●',
  },
  note: {
    border: 'border-l-slate-500 bg-slate-500/5',
    label: 'text-slate-300',
    glyph: '■',
  },
  warning: {
    border: 'border-l-amber-500 bg-amber-500/5',
    label: 'text-amber-300',
    glyph: '▲',
  },
  drill: {
    border: 'border-l-violet-500 bg-violet-500/5',
    label: 'text-violet-300',
    glyph: '✦',
  },
}

function Spans({
  spans,
  handlers,
}: {
  spans: LsatSpan[]
  handlers?: CrossRefHandlers
}) {
  return (
    <>
      {spans.map((span, i) => {
        const key = `${span.kind}-${i}`
        switch (span.kind) {
          case 'strong':
            return (
              <strong key={key} className="font-semibold text-slate-100">
                {span.text}
              </strong>
            )
          case 'em':
            return (
              <em key={key} className="italic text-slate-200">
                {span.text}
              </em>
            )
          case 'code':
            return (
              <code
                key={key}
                className="rounded bg-slate-800 px-1 py-0.5 font-mono text-[0.85em] text-amber-200"
              >
                {span.text}
              </code>
            )
          case 'link':
            return (
              <a
                key={key}
                href={span.href ?? '#'}
                target={span.href?.startsWith('#') ? undefined : '_blank'}
                rel="noreferrer"
                className="text-sky-300 underline decoration-sky-500/40 underline-offset-2 hover:text-sky-200"
              >
                {span.text}
              </a>
            )
          case 'concept':
            // Anchors into the reader's own concept glossary rather than a
            // route that does not exist — works offline and on the static twin.
            return (
              <a
                key={key}
                href={`#concept-${span.ref_id}`}
                title={`Concept: ${span.ref_id}`}
                className="border-b border-dotted border-emerald-500/60 text-emerald-300 hover:text-emerald-200"
              >
                {span.text}
              </a>
            )
          case 'article':
            return (
              <button
                key={key}
                type="button"
                onClick={() => handlers?.onArticle?.(span.ref_id ?? '')}
                className="border-b border-dotted border-indigo-500/60 text-indigo-300 hover:text-indigo-200"
              >
                {span.text}
              </button>
            )
          case 'question':
            return (
              <span
                key={key}
                title={`Bank question ${span.ref_id} — drill it in the LSAT Lab`}
                className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[0.8em] text-slate-300"
              >
                {span.text}
              </span>
            )
          default:
            return <span key={key}>{span.text}</span>
        }
      })}
    </>
  )
}

function Cells({ cell, handlers }: { cell: LsatCell; handlers?: CrossRefHandlers }) {
  return <Spans spans={cell} handlers={handlers} />
}

function Paragraph({
  block,
  handlers,
  compact = false,
}: {
  block: LsatParagraphBlock
  handlers?: CrossRefHandlers
  compact?: boolean
}) {
  return (
    <p className={compact ? 'text-sm leading-relaxed' : 'leading-7 text-slate-300'}>
      <Spans spans={block.spans} handlers={handlers} />
    </p>
  )
}

function List({
  block,
  handlers,
  compact = false,
}: {
  block: LsatListBlock
  handlers?: CrossRefHandlers
  compact?: boolean
}) {
  const className = compact
    ? 'ml-5 space-y-1 text-sm leading-relaxed'
    : 'ml-5 space-y-2 leading-7 text-slate-300'
  const items = block.items.map((item, i) => (
    <li key={i} className={block.ordered ? 'list-decimal' : 'list-disc'}>
      <Cells cell={item} handlers={handlers} />
    </li>
  ))
  return block.ordered ? (
    <ol className={className}>{items}</ol>
  ) : (
    <ul className={className}>{items}</ul>
  )
}

function Notation({ block }: { block: LsatNotationBlock }) {
  return (
    <figure className="my-4">
      {/* Overflow scrolls inside the figure: a board or a conditional chain
        * must never be reflowed, and must never widen the page either. */}
      <pre className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-300">
        {block.lines.join('\n')}
      </pre>
      {block.caption && (
        <figcaption className="mt-1 text-xs text-slate-400">{block.caption}</figcaption>
      )}
    </figure>
  )
}

function Table({
  block,
  handlers,
}: {
  block: LsatTableBlock
  handlers?: CrossRefHandlers
}) {
  return (
    <div className="my-4 overflow-x-auto rounded-lg border border-slate-800">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-slate-900/80">
            {block.headers.map((cell, i) => (
              <th
                key={i}
                scope="col"
                className="border-b border-slate-800 px-3 py-2 text-left font-semibold text-slate-200"
              >
                <Cells cell={cell} handlers={handlers} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, r) => (
            <tr key={r} className="odd:bg-slate-950/40">
              {row.map((cell, c) => (
                <td
                  key={c}
                  className="border-b border-slate-900 px-3 py-2 align-top text-slate-300"
                >
                  <Cells cell={cell} handlers={handlers} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Callout({
  block,
  handlers,
}: {
  block: LsatCalloutBlock
  handlers?: CrossRefHandlers
}) {
  const style = CALLOUT_STYLE[block.variant] ?? CALLOUT_STYLE.note
  return (
    <aside
      className={`my-5 rounded-r-lg border-l-4 px-4 py-3 ${style.border}`}
      aria-label={`${block.variant}: ${block.title}`}
    >
      <div
        className={`mb-2 text-[11px] font-semibold uppercase tracking-wider ${style.label}`}
      >
        <span aria-hidden="true">{style.glyph}</span> {block.title}
      </div>
      <div className="space-y-2 text-slate-300">
        {block.blocks.map((child, i) => {
          if (child.block_type === 'paragraph')
            return <Paragraph key={i} block={child} handlers={handlers} compact />
          if (child.block_type === 'list')
            return <List key={i} block={child} handlers={handlers} compact />
          return <Notation key={i} block={child} />
        })}
      </div>
    </aside>
  )
}

/** Every block type the backend can emit. Keep in lockstep with the static twin. */
export const SUPPORTED_BLOCK_TYPES = [
  'heading',
  'paragraph',
  'list',
  'callout',
  'table',
  'notation',
] as const

export default function BlockRenderer({
  blocks,
  handlers,
}: {
  blocks: LsatBlock[]
  handlers?: CrossRefHandlers
}) {
  return (
    <>
      {blocks.map((block, i) => {
        switch (block.block_type) {
          case 'heading':
            // Article headings start at h2: the page title is the h1, so
            // emitting another one would break the document outline.
            return block.level === 2 ? (
              <h2
                key={i}
                id={block.anchor}
                className="mt-8 scroll-mt-24 border-b border-slate-800 pb-2 text-xl font-semibold text-slate-100"
              >
                {block.text}
              </h2>
            ) : (
              <h3
                key={i}
                id={block.anchor}
                className="mt-6 scroll-mt-24 text-base font-semibold text-slate-200"
              >
                {block.text}
              </h3>
            )
          case 'paragraph':
            return (
              <div key={i} className="mt-4">
                <Paragraph block={block} handlers={handlers} />
              </div>
            )
          case 'list':
            return (
              <div key={i} className="mt-4">
                <List block={block} handlers={handlers} />
              </div>
            )
          case 'callout':
            return <Callout key={i} block={block} handlers={handlers} />
          case 'table':
            return <Table key={i} block={block} handlers={handlers} />
          case 'notation':
            return <Notation key={i} block={block} />
          default:
            return null
        }
      })}
    </>
  )
}
