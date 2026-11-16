<!-- kit: community v0.1.0 · the fleet default SECURITY policy (UPS-REPO-14). Inherited from the owner's
     .github repo by every repo without its own copy. -->

# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| The latest release (or the default branch, for repos that do not cut releases) | ✅ |
| Anything older | ❌ |

Security fixes ship as patch releases through release-please.

## Reporting a vulnerability

**Do not open a public issue.** Report privately through GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) on the affected repository (**Security → Report a vulnerability**), or email **amr.abdel@gmail.com**.

Please include the affected repository and version or commit, what an attacker can do, and the steps to reproduce.

## Response window

You will get an acknowledgement **within 7 days**. We then agree a fix timeline with you, and credit you in the advisory unless you ask us not to.

<!-- Law AI additions. Everything above is the community kit's text, verbatim (bamr87/bamr87 templates/community/SECURITY.md); the section below is this repository's own. -->

## Law AI specifics

Law AI handles legal text that may be privileged, which adds four things to the policy above.

- **Send no client material.** Reproduce the problem with synthetic data. A report must never carry privileged text, client facts or a live credential.
- **Where prompt text goes.** The Claude tiers and the xAI tier of the LLM provider chain send prompt text to a third party. `LLM_PROVIDER_CHAIN=ollama` is the only configuration that keeps it on the host, and a deployment holding data under a confidentiality obligation that forbids third-party processing must pin it ([docs/constitution.md](docs/constitution.md) §1, [AGENTS.md](AGENTS.md)).
- **The security model.** [docs/security.md](docs/security.md) holds the threat model, how API tokens, sessions and JWTs gate the `/api/*` routers, and the production hardening checklist. Read it before you report: it names the known gaps and the backlog items that track them.
- **What else counts as a vulnerability here.** Anything that defeats one of Law AI's own guarantees: a request that gets past the API-token, session or JWT checks without the right credential, or reaches another account's matters; prompt text that leaves the host while the chain is pinned to `ollama`; a model call, tool call or retrieval that escapes the provenance and audit log (constitution §4); and ingested or analysis output that skips its human-approval gate (constitution §5).
