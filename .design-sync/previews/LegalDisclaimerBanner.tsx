import { LegalDisclaimerBanner } from 'law-ai-ui';

/**
 * The UPL guardrail as it sits beside generated analysis — amber note styling,
 * a bolded lede and the full not-legal-advice text. Mount this next to any
 * IRAC output; it is the required companion to model-generated legal content.
 */
export function BesideAnalysis() {
  return <LegalDisclaimerBanner />;
}

/**
 * Constrained to a sidebar column via `className`. The prop is merged onto the
 * root `<aside>`, so layout utilities compose with the banner's own styling.
 */
export function InSidebarColumn() {
  return <LegalDisclaimerBanner className="max-w-xs" />;
}
