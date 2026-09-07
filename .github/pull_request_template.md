## What and why

<!-- The problem, then the change. A reviewer should be able to tell from this
     section alone whether the change is the right one. -->

## Visual evidence

<!-- REQUIRED for any change under frontend/ or lsat-static/ that a user could
     see. Delete this section only for a change with no visible surface.

     Attach images (drag into the box, or reference files committed under
     docs/images/ with a raw.githubusercontent URL — a repo-relative path does
     not render here). Before/after is required for layout, spacing, density
     or width changes. See docs/ui-ux-review.md § "Visual evidence".

     A passing ux_audit.py is not evidence: it checks landmarks and contracts,
     not whether the screen reads correctly.

     THIS IS ENFORCED. The `Visual Evidence Gate` job in ci.yml fails a PR
     that touches frontend/ or lsat-static/ with no image in this body and no
     new or changed file under docs/images/. If the change genuinely has no
     visible surface, add the `no-visual-change` label instead of deleting the
     requirement. -->

| | |
|---|---|
| Screen / state | |
| Viewport(s) | |

## Gates

<!-- Say what you actually ran and what it said. If something could not run,
     say so and why — an unrun gate reported as passing is worse than a
     skipped one.

     make lint · make typecheck · make test · make lint-specs -->

| Gate | Result |
|------|--------|
| `make lint` | |
| `make typecheck` | |
| `make test` | |
| `make lint-specs` | |

## Follow-ups (constitution §11)

<!-- Copy the new BACKLOG.md bullets verbatim, so a reviewer can see what the
     next cycle is set up to inherit. `make lint-specs` enforces that they
     exist; this section is how they reach a human. -->
