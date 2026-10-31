# Epic: Foundational Legal & AI Governance Framework

> The epic for a global, machine-readable framework of law, governance, policy and procedure — including the in-force and emerging legal regime for AI models — with a build-vs-adopt survey of rules-as-code, legal-LLM and open-data prior art and the bamr87 fleet's governance-as-code as a worked example.

- **Status**: proposed (design/docs only — no code in this epic's first PR)
- **Owner**: @bamr87
- **Created**: 2026-10-30
- **Features**: LAWAI-011 … LAWAI-017 ([features/features.yml](../features/features.yml))
- **PRD requirements**: §5.6.1 … §5.6.8 ([prd.md](prd.md) §5.6)
- **Constitution compliance**: checked against [constitution.md](constitution.md) — §1 (open source first), §4 provenance, HITL gates, §13 jurisprudential honesty. Every phase below becomes its own `specs/NNN-*` package before implementation.

## 1. Goal

Give Law AI a **foundational, comprehensive and global model of law** — every kind of binding and non-binding norm (constitutions, treaties, statutes, regulations, case law, customary and religious law where codified, administrative guidance, standards, organisational policies and procedures) — represented as provenance-carrying, versioned, machine-readable data in the knowledge graph, and, on top of it, a **first-class register of the legal and governance regime for AI models**: what is in force today, what is pending, and what is emerging, across all jurisdictions and international bodies. The framework must explain *who issued each norm, where it binds, when, and how strongly* (constitution §13), and must be honest about coverage gaps.

## 2. Scope

- **Global norm taxonomy & ontology** — sources of law and their hierarchy across legal families (common law, civil law, mixed, religious, customary), international and supranational law, soft law, technical standards, and private ordering (corporate policy, procedure, contract).
- **Open legal corpora** — adopt existing open datasets and identifiers (ELI, ECLI, Akoma Ntoso) before building any ingester.
- **AI governance register (in force)** — e.g. EU AI Act (Reg. (EU) 2024/1689), Council of Europe Framework Convention on AI, China's generative-AI / algorithm / deep-synthesis measures, Korea's AI Basic Act, Japan's AI Promotion Act, Brazil PL 2338/2023, Canada (AIDA history), India and Singapore frameworks, African Union Continental AI Strategy, US federal executive actions and state laws (Colorado SB24-205, California SB 53, Texas TRAIGA, NYC LL 144), plus NIST AI RMF, ISO/IEC 42001/23894, OECD AI Principles, UNESCO Recommendation, G7 Hiroshima Process, UN GA resolutions.
- **Obligation & control crosswalk** — normalise obligations (actor, trigger, duty, deadline, sanction) and map them across instruments (EU AI Act ↔ NIST AI RMF ↔ ISO/IEC 42001 ↔ national laws).
- **Rules-as-code layer** — a narrow, adopt-first path to executable norms (Catala / OpenFisca / LegalRuleML) for well-defined provisions, always traceable to the source text.
- **Horizon scanning** — bills, consultations, draft standards and court challenges with a temporal (as-of / in-force-from / sunset) model.
- **Governance-as-code worked example** — the bamr87 fleet's own constitution, amendments, traceability and review gates modelled as an instance of the framework (§6).
- **Interpretation guardrails** — AI interpretation of law always grounded, cited, verifiable and human-reviewed; known failure modes are design inputs.

## 3. Out of scope

- Legal advice or compliance certification; the framework informs, it never attests that anyone is compliant.
- Proprietary corpora or closed rule engines in the codebase (constitution §1); Harvey, CoCounsel, Lexis+ AI are surveyed, not integrated.
- Complete coverage of every jurisdiction in v1 — coverage is measured and labelled, not claimed.
- Translating whole legal systems into code; rules-as-code is limited to bounded, test-backed provisions.
- Fleet Project 14 board tracking (token lacks project scope — tracked by the GitHub issue only).

## 4. Landscape & prior art (build-vs-adopt, per fleet prior-art rule, bamr87/bamr87#480)

### 4.1 Legal document & rule standards

| Prior art | What it is | Decision |
| --- | --- | --- |
| [Akoma Ntoso / OASIS LegalDocML](https://www.oasis-open.org/committees/legaldocml/) | XML standard for parliamentary, legislative and judicial documents, used by UN, EU (AKN4EU) and national parliaments | **Adopt** as the document-structure vocabulary for norm nodes |
| [OASIS LegalRuleML](https://www.oasis-open.org/standard/legalruleml/) | Rule interchange for deontic norms (obligation, permission, prohibition), defeasibility, temporal validity | **Adopt** its concepts for the obligation model (§5.6.4) |
| [LKIF-Core](https://github.com/RinkeHoekstra/lkif-core) | OWL legal core ontology (norms, roles, actions) from the ESTRELLA project | **Adopt/align** as the upper ontology; do not invent one |
| ELI / ECLI (via [EUR-Lex](https://eur-lex.europa.eu)) | European Legislation / Case Law Identifiers | **Adopt** as canonical IDs where available |

### 4.2 Rules-as-code & computational law

| Prior art | Notes | Decision |
| --- | --- | --- |
| [Catala](https://catala-lang.org) ([repo](https://github.com/CatalaLang/catala)) | Literate DSL mirroring statute structure and default logic; used for French tax/benefits | **Adopt** for bounded executable provisions (Phase 5) |
| [OpenFisca](https://openfisca.org) ([core](https://github.com/openfisca/openfisca-core)) | Open rules-as-code engine for tax-benefit systems (FR, NZ, AU, others) | **Adopt** where a country package exists |
| [Blawx](https://www.blawx.com) | Visual, s(CASP)-based rules-as-code with explanations | **Evaluate** for explainable reasoning UX |
| [Stanford CodeX](https://law.stanford.edu/codex-the-stanford-center-for-legal-informatics/) | Computational-law research center (legal DSLs, smart-contract law) | **Reference** for research direction |

Finding: rules-as-code works where law is quantitative and closed (benefits, tax, eligibility) and breaks down on open-textured standards ("reasonable", "high-risk"). → Phase 5 is limited to bounded provisions and every coded rule links to its source paragraph and a test set.

### 4.3 Legal LLMs, benchmarks and commercial tools

| Prior art | Notes | Shaped |
| --- | --- | --- |
| [LegalBench](https://github.com/HazyResearch/legalbench) ([paper](https://arxiv.org/abs/2308.11462)) | 162 legal-reasoning tasks; already Law AI's regression harness (LAWAI-008) | Interpretation outputs are evaluated against it (§5.6.7) |
| [CaseHOLD](https://github.com/reglab/casehold) ([paper](https://arxiv.org/abs/2104.08671)) | 53k holding multiple-choice questions | Candidate added benchmark for holding extraction |
| [Harvey](https://www.harvey.ai), [CoCounsel](https://legal.thomsonreuters.com/en/products/cocounsel), [Lexis+ AI](https://www.lexisnexis.com/en-us/products/lexis-plus-ai.page) | Proprietary RAG-based legal assistants | Surveyed only (constitution §1); set the feature bar |
| Magesh et al., *Hallucination-Free?* ([arXiv:2405.20362](https://arxiv.org/abs/2405.20362)) | Stanford RegLab/HAI found leading commercial legal RAG tools still hallucinate in roughly 17–33% of queries | "RAG" is not a guarantee → mandatory citation verification |

### 4.4 Known failure modes

- **Hallucinated citations and court sanctions** — *Mata v. Avianca* (S.D.N.Y. 2023, [summary](https://en.wikipedia.org/wiki/Mata_v._Avianca,_Inc.)) sanctioned lawyers for fabricated ChatGPT citations; the [AI Hallucination Cases database](https://www.damiencharlotin.com/hallucinations/) tracks hundreds of such decisions worldwide. → every interpreted proposition must resolve to a retrieved, existing authority before display (§5.6.7).
- **Staleness / temporal error** — repealed or amended provisions cited as current. → bitemporal model (§5.6.5).
- **Coverage bias** — absence of a result read as absence of law (AGENTS.md power-aware output). → coverage labels per jurisdiction (§5.6.1).
- **Jurisdiction conflation** — persuasive authority presented as binding. → issuer/binding-force attributes are mandatory.

### 4.5 Open corpora (adopt before ingest)

[CourtListener](https://www.courtlistener.com) and [Caselaw Access Project](https://case.law) (already used, see [data-sources.md](data-sources.md)), [Pile of Law](https://huggingface.co/datasets/pile-of-law/pile-of-law), [EUR-Lex](https://eur-lex.europa.eu), [legislation.gov.uk](https://www.legislation.gov.uk) ([API](https://www.legislation.gov.uk/developer)), [Federal Register of Legislation (AU)](https://www.legislation.gov.au), [Korea Law Information Center](https://www.law.go.kr), [Laws of India](https://www.lawsofindia.org), [GovInfo (US)](https://www.govinfo.gov), [Open Legal Data (DE)](https://github.com/openlegaldata).

### 4.6 AI-governance instruments (sources for the register)

[EU AI Act](https://artificialintelligenceact.eu) · [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) · [ISO/IEC 42001](https://www.iso.org/standard/81230.html) · [OECD AI Principles](https://oecd.ai/en/ai-principles) · [UNESCO Recommendation on the Ethics of AI](https://www.unesco.org/en/artificial-intelligence/recommendation-ethics) · [Council of Europe Framework Convention](https://www.coe.int/en/web/artificial-intelligence/the-framework-convention-on-artificial-intelligence) · [China Interim Measures for Generative AI](https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm) · [Brazil PL 2338/2023](https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=2487262) · [Singapore Model AI Governance Framework](https://www.pdpc.gov.sg/help-and-resources/2020/01/model-ai-governance-framework) · [African Union Continental AI Strategy](https://au.int/en/documents/20240809/continental-artificial-intelligence-strategy) · [US presidential actions](https://www.whitehouse.gov/presidential-actions/) · Colorado SB24-205, California SB 53. Each register entry records its status *as of* a date — this list is a seed, not a claim of currency.

**Build-vs-adopt summary**: adopt standards (Akoma Ntoso, LegalRuleML, LKIF, ELI/ECLI), corpora, rules engines (Catala/OpenFisca) and benchmarks (LegalBench, CaseHOLD); **build** only the glue Law AI uniquely needs — the graph mapping, the cross-instrument obligation crosswalk, the temporal register, power-aware labels and the verification guardrail.

## 5. Phases (ordered)

Each phase becomes a spec package (`specs/NNN-*`) and passes `make lint-specs` before implementation.

### Phase 1 — Global norm taxonomy & ontology (LAWAI-011, §5.6.1)
- **Scope**: node/edge types for sources of law, issuers, jurisdictions (incl. international/supranational), binding force, legal family; alignment to LKIF-Core and Akoma Ntoso; coverage metadata.
- **Acceptance**: ontology doc + `data-model.md` delta; ≥1 worked instance per legal family and per norm tier (treaty → constitution → statute → regulation → guidance → standard → policy → procedure); every node type has issuer, jurisdiction, date, binding-force fields.
- **Guardrails**: no US/EU default jurisdiction; "not in corpus" ≠ "no law"; adopt ontology terms before coining new ones.

### Phase 2 — Open-corpus adoption plan (LAWAI-012, §5.6.2)
- **Scope**: licence/coverage matrix for corpora in §4.5 across every inhabited continent; ELI/ECLI identifier mapping.
- **Acceptance**: `data-sources.md` extended with licence, API, coverage and status per source; ≥1 source per continent identified; each ingester proposal has a HITL quarantine path.
- **Guardrails**: licence must be compatible (constitution §1); ingestion stays behind the quarantine gate.

### Phase 3 — AI governance register (LAWAI-013, §5.6.3)
- **Scope**: structured register of binding AI laws, executive actions, standards and principles (§4.6), each with issuer, jurisdiction, legal status, effective dates, scope (provider/deployer/model/GPAI), source link.
- **Acceptance**: register covers EU, CoE, UN/OECD/UNESCO/G7, US federal + leading states, China, Korea, Japan, India, Singapore, Brazil, Canada, UK, AU (African Union) at minimum; each entry has an as-of date and verified source URL.
- **Guardrails**: binding vs. voluntary always labelled; pending bills never shown as law.

### Phase 4 — Obligation & control crosswalk (LAWAI-014, §5.6.4)
- **Scope**: LegalRuleML-style obligation model (actor, trigger, deontic modality, deadline, sanction, exceptions) and crosswalk EU AI Act ↔ NIST AI RMF ↔ ISO/IEC 42001 ↔ national laws.
- **Acceptance**: crosswalk for ≥3 instruments with every mapping cited to article/clause; mappings carry a confidence and a reviewer.
- **Guardrails**: mappings are HITL-approved; equivalence is labelled as interpretation, not law.

### Phase 5 — Bounded rules-as-code (LAWAI-015, §5.6.5 part)
- **Scope**: pilot executable encodings of closed provisions (e.g. an AI Act risk-tier classifier, an eligibility rule) in Catala/OpenFisca.
- **Acceptance**: each encoding links paragraph-by-paragraph to its source, ships a test suite drawn from official examples, and declares the open-textured terms it does not decide.
- **Guardrails**: outputs are advisory, explained, and never present an open-textured judgement as computed fact.

### Phase 6 — Horizon scanning & temporal model (LAWAI-016, §5.6.5)
- **Scope**: bitemporal validity (valid-time, as-known-time) on every norm; tracked pipeline of bills, consultations, draft standards and litigation.
- **Acceptance**: any query can be answered "as of date D"; emerging items carry stage and expected date; amendments/repeals propagate.
- **Guardrails**: forecasts labelled as forecasts; sources re-verified on a schedule.

### Phase 7 — Governance-as-code worked example (LAWAI-017, §5.6.6)
- **Scope**: model the bamr87 fleet (§6) as an instance of the framework.
- **Acceptance**: the fleet constitution, amendments and gates are represented as norm nodes with issuer, ratification event and enforcement mechanism; a walkthrough doc traces one PR from spec → review gate → merge.
- **Guardrails**: read-only representation; Law AI never merges or ratifies anything itself.

### Cross-cutting — Grounded interpretation guardrail (§5.6.7) and evaluation (§5.6.8)
Applies to all phases: AI interpretation of any norm must cite retrieved, existing sources, pass citation verification, carry jurisdiction/as-of labels, and route high-stakes outputs through HITL; LegalBench (and CaseHOLD where relevant) gate regressions.

## 6. Worked example: governance-as-code in the bamr87 agent fleet

The fleet hub [bamr87/bamr87](https://github.com/bamr87/bamr87) already runs an AI-agent fleet under codified governance; it maps cleanly onto this framework's norm tiers:

| Framework tier | Fleet artefact |
| --- | --- |
| Constitution | hub `docs/constitution.md`; this repo's [constitution.md](constitution.md) |
| Constitutional amendment (ratified by an act) | [amendments](amendments/README.md) — a proposed amendment is ratified **only by Amr merging its PR**; agents never merge amendments |
| Legislation → requirements | PRD requirements (`§n`, `FRn`) with a generated reverse trace |
| Implementing acts / register | `features/features.yml` feature catalog, each id tracing to PRD requirements (`governance_lint.py`) |
| Procedure | the spec-driven loop (`/specify → /clarify → /plan → /tasks → /implement`), hub [SPEC-DRIVEN.md](https://github.com/bamr87/bamr87/blob/main/docs/SPEC-DRIVEN.md) |
| Due-process / review | review gate and merge authority ([bamr87/bamr87#481](https://github.com/bamr87/bamr87/pull/481)): mergeable-PR checklist, merge commits only, gated categories, `needs-amr` escalation |
| Impact-assessment duty | prior-art rule ([bamr87/bamr87#480](https://github.com/bamr87/bamr87/pull/480)): needs assessment + build-vs-adopt before new harness/loop design |
| Supervisory authority / monitoring | overseer harness (hub [HARNESS.md](https://github.com/bamr87/bamr87/blob/main/docs/HARNESS.md), [HARNESS-OPS.md](https://github.com/bamr87/bamr87/blob/main/docs/HARNESS-OPS.md)) and CI spec gate |
| Records / audit | AGENTS.md as single source of truth; provenance log (LAWAI-007); append-only BACKLOG |

The example shows how the same obligations an AI regulator imposes (human oversight, documentation, risk management, traceability — e.g. EU AI Act Arts. 9–14, NIST AI RMF *Govern*, ISO/IEC 42001 clause 5–9) can be satisfied *by construction* in an agent fleet. Phase 7 makes this mapping explicit in the crosswalk.

## 7. Review question (constitution §13)

This epic ranks nothing by default, but the register and crosswalk *summarise* authority. **Who is the stronger here?** Jurisdictions and firms with the most published, English-language, machine-readable law, and the standards bodies whose documents are paywalled. **What does the design do for them?** Without care it would make their law look like "the" law. Mitigations: global-coverage targets, explicit coverage gaps, binding vs. voluntary labels, paywalled standards represented by public metadata with the gap disclosed.

## 8. Open questions

- Licensing of ISO/IEC standards text (metadata-only?).
- Translation and authoritative-language handling for non-English sources.
- Whether Phase 5 targets the AI Act risk-tier logic or a benefits rule first.
