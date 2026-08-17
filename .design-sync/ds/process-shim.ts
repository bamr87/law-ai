// Browser-safe `process` shim.
//
// frontend/lib/api.ts and frontend/lib/agentStream.ts read
// `process.env.NEXT_PUBLIC_*` at MODULE scope. Next.js normally inlines those
// at build time; the design-sync bundle has no such step, so without this the
// IIFE throws `ReferenceError: process is not defined` on load and
// `window.LawAI` is never assigned — every preview then renders empty.
//
// Leaving `env` empty is deliberate: both call sites already fall back to
// sensible defaults (`http://localhost:8000`, no API key), which is exactly
// what a design-time render should use.
//
// This module MUST be evaluated before any app module. `entry.tsx` imports it
// as its first import for that reason — ES modules evaluate dependencies in
// import-declaration order, and re-exports are hoisted above statements, so a
// bare assignment in entry.tsx would run too late.

const g = globalThis as unknown as { process?: { env: Record<string, string | undefined> } };
g.process ??= { env: {} };
g.process.env ??= {};

export {};
