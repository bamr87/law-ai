# DISCLAIMER

## NOT LEGAL ADVICE

**lawmode provides automated legal-risk analysis of source code for informational purposes only.**

This software and its outputs do not constitute legal advice, legal opinion, or any form of legal representation. The information lawmode provides is:

- **General in nature** and may not apply to your specific situation
- **Not a substitute** for consultation with qualified legal counsel
- **Not guaranteed** to be accurate, complete, or up-to-date
- **Not intended** to create an attorney-client relationship

## What a report does and does not say

- **Findings are advisory.** A severity is the model's estimate of a risk. It is not a ruling, and no finding blocks or approves a change by itself.
- **Critical and high findings are for a human.** They are reported as needing human review, and they stay that way until a person has decided on them.
- **No findings is not compliance.** A report with no findings means these checks raised nothing in the code they were given. It does not mean the code is lawful, licensed, accessible or secure.
- **Authorities are named, not verified.** Each finding carries the law or licence the model named for it. Unless a report says otherwise, that authority and any link to it come from the model and have not been checked against the official text. A finding that names no authority, or does not say where it applies, is sent to a human.
- **An incomplete report says so.** If the model returned a finding that could not be read, the report is marked incomplete and needs a human; it is not a clean result.

## Limitations

- lawmode uses AI models that may produce errors or incomplete analysis
- Legal requirements vary by jurisdiction and change over time
- Compliance requirements depend on your specific business context
- Automated analysis cannot replace human legal judgment

## Where your code goes

The code under review is sent as a prompt to whichever model provider answers in the configured `LLM_PROVIDER_CHAIN`. The hosted tiers are third parties. For code that must not leave the machine, pin the chain to the local tier (`LLM_PROVIDER_CHAIN=ollama`).

## Your Responsibility

You are solely responsible for:

- Consulting with qualified legal counsel for legal matters
- Verifying the accuracy and applicability of any legal information
- Ensuring compliance with all applicable laws and regulations
- Making informed decisions based on professional legal advice

## No Warranty

lawmode is provided "as is" without warranty of any kind, express or implied, including but not limited to warranties of merchantability, fitness for a particular purpose, or non-infringement.

## Limitation of Liability

To the maximum extent permitted by law, lawmode and its operators shall not be liable for any direct, indirect, incidental, special, consequential, or punitive damages arising from your use of this software.

---

**By using lawmode, you acknowledge that you have read, understood, and agree to this disclaimer.**
