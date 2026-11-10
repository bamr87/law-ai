# CLAUDE.md

Guidance for AI coding agents (Claude Code, Copilot, Cursor) working in **lawmode**.

LawMode.ai is a dormant MVP of an always-on AI legal reviewer for developers: a Python package and CLI (`lawmode/`), plus a VS Code extension (`vscode-extension/`), that runs a multi-chain legal-reasoning pipeline over code, prompts and commits and writes auditable review artifacts. It was imported into `bamr87/law-ai` with full history in #174 and now lives here as a subdirectory with its own tooling; the parent repo's [AGENTS.md](../AGENTS.md) and [docs/constitution.md](../docs/constitution.md) govern it. Its LLM providers are OpenAI and xAI (`lawmode/llm/`), outside law-ai's Anthropic-default runtime. "Done" here means documentation-only or test-backed changes that keep `make test` green in this directory; whether to revive, fold into law-ai proper, or retire LawMode is an open decision for the maintainer, so do not start feature work without a spec.

## Stack & commands

Run from `lawmode/` (see its [Makefile](Makefile)):

```bash
make install        # pip install -e ".[dev]"
make test           # pytest tests/ -v (tests/integration/ call live xAI/OpenAI APIs and need keys)
make lint           # ruff check + mypy
make docker-build   # build the LawMode image; make docker-run to run it
```

## Conventions

- Conventional Commits: `type(scope): description` (`feat`/`fix`/`docs`/`refactor`/`test`/`chore`/`ci`).
- Default branch is `main` — branch from it and open a PR; never push to it directly.
- README-First, README-Last: read the nearest `README.md` before changing a directory, and update it after.
- Don't suppress type errors (`as any`, `@ts-ignore`, `# type: ignore`) or leave empty exception handlers.

## Fleet context

The standalone `bamr87/lawmode` repository no longer resolves; this directory inside [bamr87/law-ai](https://github.com/bamr87/law-ai) is the copy of record. Fleet standards from the [bamr87/bamr87 hub](https://github.com/bamr87/bamr87) apply through law-ai: its PRD ([docs/prd.md](../docs/prd.md)), feature catalog ([features/features.yml](../features/features.yml)), constitution and amendments. Branch from law-ai `main`, open a draft PR, and record follow-ups in law-ai's [BACKLOG.md](../BACKLOG.md).
