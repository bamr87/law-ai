# Plan: Static LSAT site UI/UX parity

- **Spec**: [spec.md](spec.md)
- **Status**: shipped
- **Approach**: share the primitives physically, extend the gate to both surfaces, then fix what the extended gate finds.

## 1. Architecture

### Sharing across two Next apps

The obvious move — `@import '../../frontend/ui/base.css'` from `lsat-static/app/globals.css` — does not work. Next's CSS pipeline refuses to resolve an import outside an app's own root; Turbopack fails the build with "Module not found". Spec 039 flagged this as R-2 and it is real.

So the shared primitives are **mirrored**: `frontend/ui/base.css` is the source, `lsat-static/app/base.css` is a byte-identical copy produced by `make ui-sync`, and audit rule **R12** fails the build when they differ. Duplication that a gate cannot detect is a fork; duplication a gate enforces is a build artifact that happens to be committed.

What is shared is deliberately narrow — the z-scale, the focus ring, the motion opt-out. Shell metrics and `.shell-scroll` stay in `layout.css`, because a site with no shell should not inherit tokens describing one.

### One contract, two surfaces

```
                     universal (R3-R6, R9-R11)      shell-only (R1, R2, R7, R8)
frontend/  .tsx           ✓                                ✓
lsat-static/ .tsx         ✓                                —
*.css (both)         R4, R9                                —
```

Holding the static site to R7 ("every route uses PageLayout") would be nonsense — it has one route and no PageLayout. Rules it structurally cannot satisfy would teach everyone to ignore the audit, so the split is explicit rather than fudged with exemptions.

Adding CSS scanning matters more than it sounds: the static site writes its entire layout in `globals.css`, so before this the z-scale and sticky-offset rules did not reach half the product.

### The sticky stack, scoped

The platform pins chrome because it owns a viewport-locked shell. The static site document-scrolls, so the equivalent is a sticky stack: site header → drill head (carrying the clock) → passage column.

It applies **only at ≥820px**, the existing two-column breakpoint. Measured at 390px the header wraps to 136px and the drill head is 180px; pinning both would spend 37% of the viewport on chrome. This mirrors the platform's compact behaviour (panels become drawers) rather than copying its desktop layout onto a phone.

`.passage` needed `align-self: start` for the same reason the platform's graph case picker did: a grid item defaults to `stretch`, becomes exactly as tall as its row, and leaves `position: sticky` nowhere to travel. It had been silently doing nothing.

## 2. Two rule bugs the second surface exposed

Extending the audit immediately produced two findings that were **wrong**, and both were rule defects rather than code defects:

- **R3** assumed a shell owns `<main>`, so it flagged the static site's page for rendering the one `<main>` it should. Split: file-level nesting check on the platform, surface-level "exactly one" count on the static export.
- **R11** assumed a `placeholder`-bearing control is never wrapped in an implicit `<label>`. `lsat-static` uses exactly that idiom with an `sr-only` span. Added `_inside_label`, which compares the nearest preceding `<label` against the nearest preceding `</label>`.

This is the strongest argument in the change for extending gates to new surfaces early: a rule proven against one codebase is not proven in general.

## 3. Test strategy

The static site has no test runner (no vitest, no RTL) and adding one is out of scope, so verification is the audit plus a real build and browser:

| Layer | Covers |
|-------|--------|
| `scripts/ux_audit.py` | Both surfaces, `.tsx` and `.css`; R12 mirror drift |
| Injected-violation runs | R3 (main removed), R11 (label stripped), R4 (`z-index: 10`), R9 (`top: 5rem`), R12 (appended byte) all fail; clean tree passes |
| Real static export | Builds; emitted CSS carries the shared tokens and no Tailwind; `out/index.html` has one `<main>` and one `contentinfo` |
| Headless Chromium on the built artifact | Skip link is the first tab stop and reveals on focus; desktop stack pins with a −1px tuck and the clock stays visible; mobile pins the header only |
| `make test-frontend` | The platform's 135 tests still pass after the `base.css` split |

## 4. Rollout

One commit on the same branch. `make ui-sync` is the only new workflow step, and forgetting it is a build failure rather than a silent divergence.

## 5. Risks

Carried from [spec.md](spec.md) §13. The one to watch: `--site-header-h` is a measured constant. It errs a pixel *under* the real height so the failure mode is an invisible tuck rather than a visible gap, and it is confined to the wide-viewport case where the header is a single row.
