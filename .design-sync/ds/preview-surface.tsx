// Preview-only surface wrapper (wired via `provider` in ../config.json).
//
// Both Law AI apps render their components against a dark shell:
//
//   frontend/app/layout.tsx   <body class="… bg-gradient-to-b from-slate-950
//                              via-slate-950 to-slate-900 text-slate-200 …">
//   lsat-static/app/globals.css   body { background: var(--bg); color: var(--text) }
//
// The preview-card harness hard-codes `body{background:#fff}` in each card's
// own <style> block, which lands after the stylesheet links and so wins. On
// white, translucent surfaces (`bg-slate-900/40`) and inherited text colours
// (`var(--text)`, #e2e8f0) wash out — the cards misrepresent both idioms.
//
// This restores the shell. The two apps happen to agree on the foreground
// colour (Tailwind's slate-200 IS lsat-static's --text, #e2e8f0), so a single
// wrapper is faithful to both. The classes are the app's own, not a copy of
// its colours, so they stay in lockstep with the compiled stylesheet.
//
// This affects PREVIEW CARDS ONLY. A design built with this DS gets the real
// `body` rule from styles.css and needs no wrapper.

import * as React from 'react';

export function PreviewSurface({ children }: { children?: React.ReactNode }) {
  return (
    <div
      className="bg-gradient-to-b from-slate-950 via-slate-950 to-slate-900 text-slate-200 antialiased"
      style={{ padding: '1.25rem', borderRadius: 6 }}
    >
      {children}
    </div>
  );
}

export default PreviewSurface;
