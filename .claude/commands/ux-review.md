---
description: "Run one UI/UX + navigation review pass over the app shell, fix the worst finding, and promote the fix into the gate"
argument-hint: "(optional) a dimension (D1-D8), route, or component to focus the pass on"
---

Run one pass of the Law AI **UI/UX review loop**.

Read [docs/ui-ux-review.md](../../docs/ui-ux-review.md) and follow the procedure in the `ux-review` skill exactly: orient against the pass log, run `make ux-audit` and `make test-frontend` as the mechanical floor, score rubric dimensions D1–D8 with file-and-line evidence, then fix **one** finding end to end and promote it into the audit or the shell tests so it cannot regress.

Focus (optional): $ARGUMENTS

Honor the stop conditions — anything that changes what the product claims about legal authority, weakens a UPL disclaimer, HITL gate, or provenance surface, adds a runtime npm dependency, or redesigns a feature's information model is a human decision, not a UX pass. All gates run in Docker via `make`; close the constitution §11 loop before opening the PR.
