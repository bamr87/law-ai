'use client'

import { INSTANCE_SCOPE } from '@/lib/scope/instance'

/**
 * v1: a single instance scope. The control is a labelled readout, not a
 * URL-trusted id picker (architecture trap: a scope switcher is an IDOR
 * vector). When spec 036 matters land, resolve slug → id server-side.
 */
export default function ScopeSwitcher() {
  return (
    <div
      className="max-w-xs truncate rounded-full border border-slate-700 bg-slate-900/60 px-3 py-1 text-center text-xs text-slate-300"
      title="Instance is the only live scope (spec 040). Org/team/project wait on spec 036."
    >
      <span className="text-slate-500">Scope · </span>
      {INSTANCE_SCOPE.name}
    </div>
  )
}
