// Static export for GitHub Pages (LSAT exercises only).
//
// `output: 'export'` emits a fully static site to `out/` — no Node server, no
// API. The LSAT bank is imported at build time from ./content.json (the
// HITL-approved artifact refreshed by `make lsat-export`), so the published
// site never talks to a backend.
//
// GitHub project Pages serve under `https://<owner>.github.io/<repo>/`, so the
// asset paths need a base path. It defaults to `/law-ai` (this repo) and can be
// overridden at build time with PAGES_BASE_PATH (e.g. `""` for a user/org site
// or a custom domain at the root).
const rawBase = process.env.PAGES_BASE_PATH ?? '/law-ai'
// Normalise: no trailing slash; empty string means "served at root".
const basePath = rawBase === '/' ? '' : rawBase.replace(/\/$/, '')

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  trailingSlash: true,
  // `next/image` optimisation needs a server; disable it for a static host.
  images: { unoptimized: true },
  ...(basePath ? { basePath, assetPrefix: basePath } : {}),
}

export default nextConfig
