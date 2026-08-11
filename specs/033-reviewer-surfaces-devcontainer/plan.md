# Plan: Reviewer Surfaces (Live Trace, Verified Citations) + Dev Container

- **Spec**: [spec.md](spec.md) (033-reviewer-surfaces-devcontainer)
- **Approach**: three small, independent slices that each surface something
  the backend already produced but nobody could see. No backend changes at
  all — this is the consumption side of specs 026, 032, and the Docker-first
  rule.

## Slice A — Live trace in Analysis Studio (FR-1 … FR-4)

The ordering is the whole contract, so the code follows it literally:

```
newStreamId() → openAgentStream() → await ready → POST{stream_id}
                      │
                      └─ on failure: socket = null, POST WITHOUT stream_id
```

Two deliberate choices:

- **`stream_id` is only sent when the socket actually opened.** Sending it
  regardless would tell the server to publish to a group with no
  subscriber — harmless, but it would misreport the client's state.
- **`LiveTrace` renders `null` until the first event.** A panel that
  appears and stays empty is worse than no panel: it looks broken when the
  real story is "streaming unavailable, analysis proceeding normally."

`socket?.close()` sits in `finally`, so neither the success nor the error
path leaks a connection.

## Slice B — Verified-citation badges (FR-5)

Tri-state on purpose, because `verified` is genuinely three-valued:

| `verified` | Render | Meaning |
|---|---|---|
| `true` | `verified in graph` | resolved against the corpus |
| `false` | `unverified` + tooltip | model asserted it; graph could not resolve it |
| absent | no badge | path predates the check — do not guess |

The tooltip deliberately says "verify against the official record" rather
than implying the badge means *correct*: resolution proves the authority
exists in our corpus, not that the proposition is right (§13).

## Slice C — Dev container (FR-6)

Attach the editor to the **same compose service** the Makefile uses, rather
than defining a parallel environment that can drift:

- `service: backend`, `workspaceFolder: /app`.
- `overrideCommand: true` — otherwise the container's daphne command owns
  the lifecycle and the editor session dies with it.
- `python.defaultInterpreterPath: /usr/local/bin/python` — the image
  installs the package with `pip install -e`, so the system interpreter *is*
  the project environment; there is no venv to point at (which is exactly
  why the old `./backend/.venv/bin/python` setting was wrong).
- `PHOENIX_COLLECTOR_ENDPOINT: ""` so in-editor pytest runs don't spew the
  OTEL export tracebacks that pollute container test output.

## Test strategy

3 new component tests: both badges render (and the unresolved citation is
still listed), no badges when the field is absent, and the analysis
completes with no live panel when the socket cannot connect. Plus the
7 `lib/agentStream` unit tests from spec 032 already covering the client.

**Known coverage limit, stated rather than papered over:** jsdom has no
WebSocket, so the component tests exercise the *fallback* path only. The
streaming path is covered backend-side by the spec-032 end-to-end
subscribe→post→receive test; proving the two halves work *together* in a
browser needs the Playwright e2e harness that does not exist yet.

Gates: full backend suite (no backend changes, run as a regression check),
`npm test`, `npx tsc --noEmit`, `make lint-specs`, JSONC validation of the
devcontainer.

## Rollback

Each slice is independent: drop the `LiveTrace` mount, drop the badge
spans, or delete `.devcontainer/`. Nothing else depends on them.
