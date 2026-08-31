'use client'

import { LegalDisclaimerBanner } from '@/components/LegalDisclaimer'
import { moduleForPath } from '@/lib/modules/catalog'
import { usePathname } from 'next/navigation'

export default function InspectorPanel() {
  const pathname = usePathname() || '/'
  const mod = moduleForPath(pathname)

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
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
