import * as React from 'react';
import { AnalysisStudio } from 'law-ai-ui';
import { installApiMock, ALL_ROUTES } from '../ds/preview-mocks';

// Analysis runs are POSTed to /api/analysis. The studio starts on an empty
// prompt (the analysis only fires on submit, which a static card can't do), so
// this card documents the input surface; the mocked response shape is wired up
// so the same preview shows the result state once submitted interactively.
installApiMock(ALL_ROUTES);

/**
 * The Analysis Studio input surface: fact-pattern prompt, jurisdiction selector,
 * the local-LLM toggle, and the UPL disclaimer that ships beside every run.
 */
export function FactPatternInput() {
  return <AnalysisStudio />;
}

/**
 * The result state — IRAC output, ranked precedents, retrieval coverage and the
 * per-agent trace. It only exists after a submit, so this cell drives the studio
 * the way a user would: fill the prompt, then run. The response comes from the
 * mocked /api/analysis fixture.
 */
export function IracResult() {
  // Scoped to this cell's own subtree: every export renders into the same card
  // page, so a bare document.querySelector would drive the sibling cell's form.
  const hostRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const timer = setTimeout(() => {
      const root = hostRef.current;
      if (!root) return;
      const area = root.querySelector('textarea');
      if (!area) return;
      // React tracks the value on the DOM node, so assigning `.value` directly
      // is swallowed on the next render — go through the native setter and
      // dispatch the event React actually listens for.
      const setValue = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        'value',
      )?.set;
      setValue?.call(
        area,
        'Our client’s mother arrived at the intersection moments after a delivery van struck her adult son, and saw him bleeding on the roadway before paramedics moved him. She has since been unable to work. Can she recover for negligent infliction of emotional distress in California?',
      );
      area.dispatchEvent(new Event('input', { bubbles: true }));

      const run = [...root.querySelectorAll('button')].find((b) =>
        (b.textContent ?? '').includes('Run analysis'),
      ) as HTMLButtonElement | undefined;
      run?.click();
    }, 60);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div ref={hostRef}>
      <AnalysisStudio />
    </div>
  );
}
