// Design-system entry for the Law AI UI surface.
//
// This repo ships no component library — the UI lives inside two Next.js apps
// (`frontend/` = the Law AI platform, `lsat-static/` = the static LSAT practice
// site). This file is the synthetic package entry the design-sync converter
// bundles: it re-exports each app's default-exported component under a named
// export so `window.LawAI.<Name>` resolves.
//
// Keep this list in sync with `componentSrcMap` in ../config.json.

// MUST stay the first import: it installs a browser-safe `process` before any
// app module is evaluated. See ./process-shim.ts for why ordering matters.
import './process-shim';

// Preview-only surface wrapper, referenced by `provider` in ../config.json.
// Not a synced component (it is absent from `componentSrcMap`) — it only needs
// to be a bundle export so the preview harness can resolve it.
export { PreviewSurface } from './preview-surface';

// ── frontend/ — the Law AI platform ─────────────────────────────────────────
export { default as AgentDashboard } from '../../frontend/components/AgentDashboard';
export { default as AgentTrace } from '../../frontend/components/AgentTrace';
export { default as AnalysisStudio } from '../../frontend/components/AnalysisStudio';
export { default as GraphViewer } from '../../frontend/components/GraphViewer';
export { default as HomeStats } from '../../frontend/components/HomeStats';
export { default as KnowledgeGraph } from '../../frontend/components/KnowledgeGraph';
export { LegalDisclaimerBanner } from '../../frontend/components/LegalDisclaimer';
export { default as LegalDisclaimerFooter } from '../../frontend/components/LegalDisclaimer';
export { default as LsatLab } from '../../frontend/components/LsatLab';
export { default as NavBar } from '../../frontend/components/NavBar';

// ── lsat-static/ — the static LSAT practice site ────────────────────────────
export { default as Concepts } from '../../lsat-static/components/Concepts';
export { default as Drill } from '../../lsat-static/components/Drill';
export { default as Overview } from '../../lsat-static/components/Overview';
export { default as PassagePanel } from '../../lsat-static/components/PassagePanel';
export { default as QuestionCard } from '../../lsat-static/components/QuestionCard';
export { default as Stats } from '../../lsat-static/components/Stats';
