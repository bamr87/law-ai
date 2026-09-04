'use client'

/**
 * Renders the typed blocks that `library.py` compiles articles into.
 *
 * Offline twin of `frontend/components/lsat/library/BlockRenderer.tsx`. There
 * is deliberately no Markdown parser and no `dangerouslySetInnerHTML` here:
 * the backend closed the article dialect and emits a typed tree, so this file
 * only maps block and span kinds onto elements (spec 048 FR-2/FR-11,
 * NFR-SAFETY-1).
 *
 * The two renderers must cover the same block-type set —
 * `tests/test_lsat_site.py` asserts it, so a block type added to one and not
 * the other fails CI rather than silently vanishing from the offline site.
 */

import type {
  Block,
  CalloutBlock,
  Cell,
  ListBlock,
  NotationBlock,
  ParagraphBlock,
  Span,
  TableBlock,
} from '@/lib/types'

export interface CrossRefHandlers {
  /** Follow an `[[article:id]]` reference. */
  onArticle?: (articleId: string) => void
}

function Spans({ spans, handlers }: { spans: Span[]; handlers?: CrossRefHandlers }) {
  return (
    <>
      {spans.map((span, i) => {
        const key = `${span.kind}-${i}`
        switch (span.kind) {
          case 'strong':
            return <strong key={key}>{span.text}</strong>
          case 'em':
            return <em key={key}>{span.text}</em>
          case 'code':
            return (
              <code key={key} className="lib-code">
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
              >
                {span.text}
              </a>
            )
          case 'concept':
            // Anchors into the reader's own glossary at the foot of the
            // article — there is no concept route on this site, and a link
            // that works offline beats one that looks richer and 404s.
            return (
              <a
                key={key}
                href={`#concept-${span.ref_id}`}
                className="lib-ref lib-ref-concept"
                title={`Concept: ${span.ref_id}`}
              >
                {span.text}
              </a>
            )
          case 'article':
            return (
              <button
                key={key}
                type="button"
                className="lib-ref lib-ref-article"
                onClick={() => handlers?.onArticle?.(span.ref_id ?? '')}
              >
                {span.text}
              </button>
            )
          case 'question':
            return (
              <span
                key={key}
                className="lib-ref lib-ref-question"
                title={`Bank question ${span.ref_id}`}
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

function Cells({ cell, handlers }: { cell: Cell; handlers?: CrossRefHandlers }) {
  return <Spans spans={cell} handlers={handlers} />
}

function Paragraph({
  block,
  handlers,
}: {
  block: ParagraphBlock
  handlers?: CrossRefHandlers
}) {
  return (
    <p className="lib-p">
      <Spans spans={block.spans} handlers={handlers} />
    </p>
  )
}

function List({ block, handlers }: { block: ListBlock; handlers?: CrossRefHandlers }) {
  const items = block.items.map((item, i) => (
    <li key={i}>
      <Cells cell={item} handlers={handlers} />
    </li>
  ))
  return block.ordered ? (
    <ol className="lib-list">{items}</ol>
  ) : (
    <ul className="lib-list">{items}</ul>
  )
}

function Notation({ block }: { block: NotationBlock }) {
  return (
    <figure className="lib-figure">
      {/* Scrolls inside the figure: a game board or a conditional chain must
          never be reflowed, and must never widen the page either. */}
      <pre className="lib-notation">{block.lines.join('\n')}</pre>
      {block.caption && <figcaption>{block.caption}</figcaption>}
    </figure>
  )
}

function Table({ block, handlers }: { block: TableBlock; handlers?: CrossRefHandlers }) {
  return (
    <div className="lib-table-wrap">
      <table className="lib-table">
        <thead>
          <tr>
            {block.headers.map((cell, i) => (
              <th key={i} scope="col">
                <Cells cell={cell} handlers={handlers} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, c) => (
                <td key={c}>
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

const CALLOUT_GLYPH: Record<CalloutBlock['variant'], string> = {
  example: '◆',
  trap: '▲',
  tip: '●',
  note: '■',
  warning: '▲',
  drill: '✦',
}

function Callout({
  block,
  handlers,
}: {
  block: CalloutBlock
  handlers?: CrossRefHandlers
}) {
  return (
    <aside
      className={`lib-callout lib-callout-${block.variant}`}
      aria-label={`${block.variant}: ${block.title}`}
    >
      <div className="lib-callout-title">
        <span aria-hidden="true">{CALLOUT_GLYPH[block.variant] ?? '■'}</span>{' '}
        {block.title}
      </div>
      {block.blocks.map((child, i) => {
        if (child.block_type === 'paragraph')
          return <Paragraph key={i} block={child} handlers={handlers} />
        if (child.block_type === 'list')
          return <List key={i} block={child} handlers={handlers} />
        return <Notation key={i} block={child} />
      })}
    </aside>
  )
}

/** Every block type the export can carry. Keep in lockstep with the platform twin. */
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
  blocks: Block[]
  handlers?: CrossRefHandlers
}) {
  return (
    <>
      {blocks.map((block, i) => {
        switch (block.block_type) {
          case 'heading':
            // Article headings start at h3: the view's own title is the h2
            // under the site h1, so emitting an h2 here would break the
            // document outline the reader's outline nav mirrors.
            return block.level === 2 ? (
              <h3 key={i} id={block.anchor} className="lib-h2">
                {block.text}
              </h3>
            ) : (
              <h4 key={i} id={block.anchor} className="lib-h3">
                {block.text}
              </h4>
            )
          case 'paragraph':
            return <Paragraph key={i} block={block} handlers={handlers} />
          case 'list':
            return <List key={i} block={block} handlers={handlers} />
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
