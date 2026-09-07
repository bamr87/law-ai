import Script from 'next/script'

/**
 * Installs the feedback widget's console/error ring buffer before the app runs.
 *
 * This is a separate component from `FeedbackButton` for one reason, and it is
 * the whole reason the buffer is worth having: a script that loads after
 * hydration reports a clean console for every failure that happened during the
 * initial render — which is exactly the class of failure a bug report exists to
 * carry. `beforeInteractive` is the App Router's "before the framework", and it
 * is only honoured from the ROOT layout.
 *
 * Vendored from the fleet kit (bamr87/bamr87 `templates/feedback/capture.js`)
 * into `public/`; the drift gate holds the copy to the hub's. Every captured
 * line is redacted on the way in — bearer tokens, API keys, JWTs, email
 * addresses — so a credential cannot reach a report even by accident.
 */
export default function FeedbackCapture() {
  return (
    // The lint rule fires on `beforeInteractive` outside `pages/_document.js`,
    // which is the Pages Router's rule; the App Router's equivalent location is
    // the root layout, and that is exactly where this renders. Verified rather
    // than assumed: `next/dist/client/script.js` branches on
    // `strategy === 'beforeInteractive'` with appDir, and the production build
    // emits the preload for this file into <head>.
    // eslint-disable-next-line @next/next/no-before-interactive-script-outside-document
    <Script src="/fleet-feedback-capture.js" strategy="beforeInteractive" />
  )
}
