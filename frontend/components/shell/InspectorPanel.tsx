'use client'

import { LegalDisclaimerBanner } from '@/components/LegalDisclaimer'
import { moduleForPath } from '@/lib/modules/catalog'
import { usePathname } from 'next/navigation'

/**
 * Right-hand context panel. Owns its own scroll so the UPL banner stays
 * reachable no matter how far down the main region the reader has gone —
 * on a UPL route the disclaimer is the point of the panel.
 */
export default function InspectorPanel() {
  const pathname = usePathname() || '/'
  const mod = moduleForPath(pathname)

  return (
    <div className="shell-panel-scroll flex h-full flex-col gap-4 p-4">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
          Inspector
        </p>
        <h2 className="mt-1 text-sm font-semibold text-slate-100">
          {mod.inspectorTitle}
        </h2>
        <p className="mt-2 text-xs leading-relaxed text-slate-400">
          {mod.inspectorBody}
        </p>
      </div>
      {mod.upl && <LegalDisclaimerBanner />}
    </div>
  )
}
