import { LegalDisclaimerFooter } from 'law-ai-ui';

/**
 * The global UPL footer, mounted once in the root layout so it appears on every
 * page: the not-legal-advice statement plus the open-source/audit-trail note.
 */
export function GlobalFooter() {
  return <LegalDisclaimerFooter />;
}
