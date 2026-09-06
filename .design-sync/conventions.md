# Law AI UI — conventions

`window.LawAI` exports 15 components from two apps. They share a dark palette but **two different styling idioms** — match the idiom of the group you are building in, and never blend them.

| Group | Components | Idiom |
|---|---|---|
| `frontend` | `AgentDashboard` `AgentTrace` `AnalysisStudio` `GraphViewer` `HomeStats` `KnowledgeGraph` `LegalDisclaimerBanner` `LegalDisclaimerFooter` `LsatLab` | Tailwind utility classes |
| `lsat-static` | `Concepts` `Drill` `Overview` `PassagePanel` `QuestionCard` `Stats` | Hand-written semantic CSS classes + `var(--*)` tokens |

## Always wrap in the dark shell

Components inherit their background and text colour from the page. On a white page, translucent surfaces (`bg-slate-900/40`) and token-coloured text wash out. Both apps wrap everything in a dark shell — reproduce it:

```jsx
<div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-950 to-slate-900 text-slate-200 antialiased">
  {/* your design */}
</div>
```

For `lsat-static` components, put content inside `.wrap` (max-width 960px, centred, padded) as that app does.

## Idiom 1 — `frontend`: Tailwind utilities

**Only six colour ramps are compiled**: `slate` `blue` `emerald` `amber` `red` `indigo`, shades `50`–`950`, across `bg-` `text-` `border-` `ring-` `from-` `via-` `to-`. Opacity suffixes (`/10`, `/20`, `/40`…), `hover:`, `focus:`, and `sm: md: lg:` are available. **Anything outside these ramps — `violet`, `pink`, `teal` — is not in the stylesheet and renders unstyled.** Stay inside them.

Semantic use in this app:

| Role | Classes |
|---|---|
| Page / raised surface | `bg-slate-950`, `bg-slate-900`, `bg-slate-900/40` |
| Borders | `border-slate-800`, `border-slate-700` |
| Body / muted / heading text | `text-slate-200`, `text-slate-400`, `text-slate-500`, `text-white` |
| Primary action, links, accents | `bg-blue-600`, `text-blue-400`, `ring-blue-500/30` |
| Success / online | `bg-emerald-500/10`, `text-emerald-300`, `text-emerald-400` |
| Warning, legal disclaimer | `border-amber-500/40`, `bg-amber-500/10`, `text-amber-100` |
| Error / destructive | `text-red-400`, `bg-red-500/10` |

Cards are `rounded-xl border border-slate-800 bg-slate-900 p-6`; sticky bars add `backdrop-blur`; numeric readouts use `tabular-nums`.

## Idiom 2 — `lsat-static`: semantic classes + tokens

**No utility classes here — use the class names below.** They are defined in the shipped stylesheet and already carry the visual language.

Tokens: `--bg` `--bg-elev` `--bg-elev-2` `--border` `--text` `--text-muted` `--accent` (amber) `--accent-dim` `--ok` (green) `--no` (red) `--radius`. Reference as `var(--accent)`.

| Purpose | Classes |
|---|---|
| Layout / chrome | `.wrap` `.site-header` `.nav-link` `.nav-link-active` `.intro` `.cards` `.search` `.sr-only` |
| Buttons | `.btn` `.btn-primary` `.btn-danger` |
| Cards & labels | `.card` `.card-head` `.card-facts` `.pill` `.pill-muted` `.empty` |
| Questions | `.qcard` `.qcard-stem` `.choice` `.choice-label` `.choice-correct` `.choice-wrong` |
| Answer feedback | `.explain` `.verdict` `.verdict-ok` `.verdict-no` `.refs` |
| Passages | `.passage` `.passage-title` `.passage-rules` |
| Drills & stats | `.drill-head` `.drill-grid` `.drill-nav` `.stat-hero` `.stat-num` `.stat-table` `.concept` `.concept-tags` |

## Components that own their data

`AgentDashboard` `AnalysisStudio` `HomeStats` `KnowledgeGraph` `LsatLab` `Concepts` `Stats` take **no props**. The first four fetch from `/api/*` on mount and render offline/empty states when no backend answers — expect that in a static design. `Concepts` and `Stats` read bundled content and `localStorage` respectively. Everything else is prop-driven; read the component's `.d.ts` for the exact contract.

## The UPL rule — not optional

This is a legal product. Any design that shows model-generated legal analysis **must** render `LegalDisclaimerBanner` beside it, and every page carries `LegalDisclaimerFooter`. Do not design analysis output without them.

## Where the truth lives

Read `_ds/<folder>/styles.css` and its `@import`ed `_ds_bundle.css` for the real class and token definitions, and `components/<group>/<Name>/<Name>.prompt.md` plus `<Name>.d.ts` for each component's API.

## Example

```jsx
<div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-950 to-slate-900 text-slate-200 antialiased">
  <main className="mx-auto max-w-7xl px-4 py-8">
    <h1 className="text-xl font-semibold tracking-tight">Matter review</h1>
    <div className="mt-6 grid gap-6 lg:grid-cols-2">
      <LawAI.AgentTrace steps={['Retrieved 24 authorities', 'Resolved 7 citations']} confidence={0.87} />
      <LawAI.LegalDisclaimerBanner />
    </div>
  </main>
</div>
```
