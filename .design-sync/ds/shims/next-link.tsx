// Browser-safe stand-in for `next/link`.
//
// The real module pulls in Next's client router, which reads
// `process.env.__NEXT_*` at module scope and needs an App Router runtime —
// neither exists in a preview card or in a design built with this DS.
//
// Outside a Next app a `<Link>` IS an anchor, so that is what this renders:
// same DOM, same classes, same accessibility attributes. Next-only routing
// props are accepted and dropped so React never forwards them to the DOM.
//
// Wired in via `compilerOptions.paths` in ../tsconfig.json.

import * as React from 'react';

type NextOnlyProps = {
  replace?: boolean;
  scroll?: boolean;
  shallow?: boolean;
  passHref?: boolean;
  prefetch?: boolean | null;
  locale?: string | false;
  legacyBehavior?: boolean;
  onNavigate?: unknown;
};

export type LinkProps = Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> &
  NextOnlyProps & { href: string | { pathname?: string } };

export default function Link({
  href,
  children,
  replace: _replace,
  scroll: _scroll,
  shallow: _shallow,
  passHref: _passHref,
  prefetch: _prefetch,
  locale: _locale,
  legacyBehavior: _legacyBehavior,
  onNavigate: _onNavigate,
  ...rest
}: LinkProps) {
  const to = typeof href === 'string' ? href : (href?.pathname ?? '#');
  return (
    <a href={to} {...rest}>
      {children}
    </a>
  );
}
