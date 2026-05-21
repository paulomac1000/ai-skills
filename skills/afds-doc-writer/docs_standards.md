---
description: Authoritative documentation standard — read this before writing, updating, or reviewing any documentation file
doc_id: ref.documentation-standard
type: ref                         # workflow | ref | system | guide | decision | contract
status: active
rigor_tier: L3
ttl_days: 365
stability: frozen
ai_scope: review_only
source_of_truth: true
tags: ["markdown", "frontmatter", "standards"]
upstream: []
supersedes: null
superseded_by: null
last_verified: 2026-05-08
owners: ["docs-maintainers"]
verification_status:
  - human_reviewed
doc_kind: atomic
glossary_terms: []
ttl_policy: permanent
---

# AI-First Documentation Standard (AFDS)

> [!IMPORTANT]
> This document is the single authoritative source of truth for how documentation is written, structured, and maintained in any project adopting this standard. All documentation files MUST conform to these rules.
>
> If any other file (including older docs) contradicts this standard, **this file takes precedence**. Update the conflicting file to match.

## PURPOSE

Define the AI-First Documentation Standard (AFDS) — a framework for writing, structuring, validating, and maintaining documentation in AI-assisted engineering environments. The core axioms are defined in Section 1 below.

## SCOPE

- INCLUDED: All documentation files in projects adopting AFDS. Covers taxonomy (Section 2), YAML frontmatter schema (Section 3), body structure (Section 4), controlled language rules (Section 5), fitness telemetry (Section 6), autonomic maintenance processes (Section 7), conflict resolution (Section 8), repository layout (Section 9), AI agent protocol (Section 10), CI/CD validation (Section 11), deprecation workflow (Section 12), anti-pattern catalog (Section 13), mutation rules (Section 14), schema amendment (Section 15), adoption phases (Section 16), testing strategy (Section 17), security and access control (Section 18), and metrics (Section 19).
- EXCLUDED: Source code, build artifacts, infrastructure configuration, non-documentation project files, wire protocols, API formats, deployment infrastructure.

## DEFINITIONS

Domain terms are defined in the project glossary (`docs/meta/glossary.md`). Per-type term definitions appear in Section 2 (document taxonomy), Section 3 (frontmatter fields), and Section 4 (body sections). Document-type-specific terms (workflow, ref, sys, guide, decision, contract) are defined in Section 2.1.

## RULES

Sections 1 through 19 define all rules. Section 1 (Core Axioms) establishes foundational invariants. Section 4 (Body Schema), Section 5 (Controlled Language), Section 8 (Conflict Resolution), and Section 14 (Mutation Rules) define the primary enforceable constraints. Each rule in this document is authoritative within its scope; conflicts between sections are resolved using the hierarchy defined in Section 8.

## INTERFACES

- INPUT: Markdown files with YAML frontmatter per the schema defined in Section 3. CI tooling reads frontmatter fields (doc_id, type, status, rigor_tier) for validation and enforcement.
- OUTPUT: Validated documents, fitness telemetry published to `docs/meta/health-report.md`, CI validation reports, knowledge conflict annotations.
- SIDE_EFFECTS: CI blocks non-conforming documents at L2+ per Section 11 tier matrix. Mutation gates (Section 14) require human approval for specific operations.

## STATE

- Assumptions: Project has adopted AFDS at Phase 0 or higher (Section 16). Repository uses Git with pre-commit hooks.
- Constraints: Maximum one H1 per file. Sections appear in exact order per document type. Banned words excluded from normative sections at L3.
- Known_Limitations: Phase 2 features (auto-discovery, runtime verification) require dedicated platform tooling. Semantic duplication scanning is advisory only.

## EDGE_CASES

- CASE: Document has no upstream references → EXPECTED: Valid for root standards and composite documents (Section 2.6). Root docs define authoritative facts and do not require upstream dependencies.
- CASE: `ttl_days: 0` → EXPECTED: Freshness score is 1.0; permanent documents (decision.*, contract.*) do not auto-decay.
- CASE: `doc_kind` is composite or translation (not atomic) → EXPECTED: `source_of_truth` MUST be `false` and `derived_from` MUST list source document IDs.

## EXAMPLES

Full worked examples appear inline in each section:
- See Section 3.2 for standard frontmatter template.
- See Section 4.1 for body schema template.
- See Section 2.5 for valid doc_id patterns.
- See `decision.001-docs-standard-decisions.md` for a complete architecture decision record.

## NON_GOALS

- Does not specify wire protocols, API serialization formats, or data transfer methods.
- Does not replace project-specific AGENTS.md files (complements them for agent operational context).
- Does not define CI platform configuration, deployment infrastructure, or monitoring stack.
- Does not cover MCP protocol specification, client implementation, or testing frameworks.

## CHANGELOG

See the CHANGELOG at the end of this document for the full version history.

---

## Table of Contents

1. [Core Axioms](#1-core-axioms)
2. [Document Taxonomy](#2-document-taxonomy)
3. [YAML Frontmatter Schema](#3-yaml-frontmatter-schema)
4. [Body Schema](#4-body-schema)
5. [Controlled Language](#5-controlled-language)
6. [Fitness Function](#6-fitness-function)
7. [Autonomic Processes](#7-autonomic-processes)
8. [Conflict Resolution](#8-conflict-resolution)
9. [Repository Structure](#9-repository-structure)
10. [AI Agent Protocol](#10-ai-agent-protocol)
11. [CI/CD Validation](#11-cicd-validation)
12. [Deprecation Workflow](#12-deprecation-workflow)
13. [Anti-Pattern Catalog](#13-anti-pattern-catalog)
14. [Mutation Rules](#14-mutation-rules)
15. [Schema Amendment Process](#15-schema-amendment-process)
16. [Adoption Phases](#16-adoption-phases)
17. [Testing and Validation Strategy](#17-testing-and-validation-strategy)
18. [Security and Access Control](#18-security-and-access-control)
19. [Documentation Metrics and Observability](#19-documentation-metrics-and-observability)

---

## 1. Core Axioms

These axioms are non-negotiable. Every rule in this standard derives from them.

```
AXIOM 1: SINGLE SOURCE OF TRUTH (SSOT)
  Every fact MUST exist in exactly one location.
  All other references MUST link, NEVER duplicate.

GUIDELINE: PREFER ATOMICITY, ACCEPT LOCALITY
  Prefer one file per independent concept.
  One section = one responsibility.
  One paragraph = one idea.

  Composite documents are an equal citizen — aggregate when
  locality improves understanding. Splitting a file requires
  human approval. No document is auto-split.

  For AI retrieval:
    - Retrieval boundaries prevent graph traversal explosions (see 9.2)
    - Context budgets enforce bounded reads (max 8 files per query)

AXIOM 3: DETERMINISTIC STRUCTURE
  AI MUST NOT invent document layout.
  AI MUST only populate predefined schemas.

AXIOM 4: MACHINE-FIRST, HUMAN-READABLE SECOND
  Priority order:
    1. AI parseability
    2. Internal consistency
    3. Human readability

  AI-first does not mean human-hostile. Documentation MUST remain readable
  by humans. Human readability is degraded only when it directly conflicts
  with AI parseability, and such tradeoffs MUST be documented.

AXIOM 5: EXPLICIT OVER IMPLICIT
  Undefined behavior MUST NOT exist in normative sections.
  Operationally relevant boundary conditions MUST be documented.
  Exhaustive edge-case enumeration is not required —
  prioritize conditions that affect system behavior in production.

AXIOM 6: EVOLUTIONARY INTEGRITY
  Documentation MUST self-assess, self-repair, and self-prune
  through defined automated loops.

AXIOM 7: CANONICAL LANGUAGE
  Structural elements (frontmatter, section headers, field names, doc_id) MUST be in English.
  Body content SHOULD be in English. The English version is the canonical source of truth.

  Translations are permitted as derived documents:
    - `doc_kind: translation`, `derived_from: <canonical doc_id>`
    - `source_of_truth: false` (enforced)
    - CI flags stale translations when canonical doc is updated

  Multilingual projects MUST designate the English version as `source_of_truth: true`.
  Translated versions link to canonical via `derived_from`. Canonical lists translations
  in the `translations` array.

AXIOM 8: KNOWLEDGE TRANSFER
  Documentation exists to optimize accurate operational understanding
  transfer between humans and agents.
  Schema compliance MUST NOT reduce knowledge clarity.
  A document that scores 1.0 on fitness but transfers zero
  operational understanding is a failure.

HUMAN OVERRIDE:
  Human operational judgment overrides automated fitness scoring,
  linting, banned-word checks, and structural recommendations.
  This standard describes what the system SHOULD enforce.
  Human review determines what it ACTUALLY enforces.
```

---

## 2. Document Taxonomy

AFDS defines **6 base document types**. Projects MAY extend this list with additional types.

### 2.1 Base Types

| Type | ID Prefix | Required Body Sections | TTL (days) |
|------|-----------|----------------------|------------|
| **Workflow** | `workflow.*` | PURPOSE, SCOPE, TRIGGER, STEPS, VALIDATION, PITFALLS, ROLLBACK | 90 |
| **Reference** | `ref.*` | PURPOSE, SCOPE, DEFINITIONS, RULES, INTERFACES, STATE, EDGE_CASES, EXAMPLES, NON_GOALS | 180 |
| **System** | `sys.*` | PURPOSE, SCOPE, ARCHITECTURE, ENTITY_REFERENCE, INTERFACES, STATE, EDGE_CASES, FAILURE_MODES, TESTING, TROUBLESHOOTING | 90 |
| **Guide** | `guide.*` | PURPOSE, AUDIENCE, CONTEXT, WALKTHROUGH, PITFALLS, RELATED_DOCS | 180 |
| **Decision** | `decision.*` | CONTEXT, DECISION, CONSEQUENCES, STATUS, CHANGELOG | 0 |
| **Contract** | `contract.*` | PURPOSE, SPECIFICATION, VERSIONING, CHANGELOG | 0 |

AFDS types map to knowledge roles. No single document type serves all four roles. A healthy repository contains all four, linked through `upstream` / `downstream`:

| Role | Types | Purpose |
|------|-------|---------|
| **Specification** | `ref.*`, `sys.*` | What the system IS — deterministic, formal, authoritative |
| **Knowledge** | `guide.*`, `ref.*` | What we KNOW about it — rationale, tradeoffs, context |
| **Process** | `workflow.*` | What we DO with it — procedures, triggers, validation |
| **Learning** | `guide.*`, L0 documents | How we TEACH it — onboarding, walkthroughs, examples |

### 2.1b Mapping to Diataxis

AFDS types align with the Diataxis framework for documentation classification. Use this table to select the correct AFDS type for your content.

| Diataxis Quadrant | AFDS Type | Example |
|-------------------|-----------|---------|
| **Tutorial** (learning-oriented) | `guide.*` L1 | "Getting Started with Auth Service" |
| **How-to Guide** (task-oriented) | `workflow.*` | "How to Rotate API Keys" |
| **Reference** (information-oriented) | `ref.*` | "Security Policy Reference" |
| **Explanation** (understanding-oriented) | `guide.*` L1 | "Why We Chose OAuth 2.1" |
| **Decision** | `decision.*` | "ADR: Use PostgreSQL for Auth DB" |
| **Contract** | `contract.*` | "Auth API v2 Specification" |

### 2.1c AI Persona Matrix

When generating or editing content, agents adopt a behavioral persona matching the document type. This ensures consistent tone without over-explaining the taxonomy.

| AFDS Type | Diataxis | Persona | Tone | Focus |
|-----------|----------|---------|------|-------|
| `guide.*` (L0-L1) | Tutorial | **The Teacher** | Patient, step-by-step, natural language, direct address ("You will see...") | Learning success |
| `workflow.*` | How-to | **The Coach** | Goal-oriented, imperative, concise, action-focused, zero theory | Task completion |
| `guide.*` (L1-L2) | Explanation | **The Architect** | Analytical, objective, causal ("Why", tradeoffs, system topology) | Deep understanding |
| `ref.*`, `sys.*` | Reference | **The Machine** | Hyper-formal, deterministic, robotic, zero conversational filler | Absolute accuracy |

Note: Diataxis is a content taxonomy, not a rigor model. AFDS `rigor_tier` (L0–L3) controls enforcement independently of Diataxis type. A how-to guide (`workflow.*`) can be L1 or L2 depending on operational criticality.

### 2.1a Choosing Between Types

| Question | Answer |
|----------|--------|
| Does it describe a running component, its failures, and operational behavior? | `sys.*` |
| Does it describe a contract, format, rules, or API without runtime behavior? | `ref.*` |
| Does it walk through a sequence of steps a human or agent executes? | `workflow.*` |
| Does it explain concepts, rationale, or guide learning? | `guide.*` |
| Does it record an architectural decision with context and consequences? | `decision.*` |
| Does it specify an API contract, data schema, or service interface? | `contract.*` |

Examples:
- `sys.auth` — auth service: how it runs, failure modes, health checks, troubleshooting
- `ref.security-policy` — password rules, token format, session timeout (no runtime info)
- `contract.api-auth-v2` — OpenAPI-linked spec: endpoints, request/response schemas
- `decision.001-use-postgres` — why PostgreSQL was chosen, alternatives, consequences

### 2.2 Filename Conventions

All documentation filenames MUST use `kebab-case.md`. The filename slug MUST match the `doc_id` slug.

```text
doc_id: ref.code-style  → code-style.md     ✅
doc_id: ref.code-style  → CODE_STYLE.md     ❌
doc_id: ref.code-style  → code_style.md     ❌
```

Root-level project files that are NOT AFDS documents (permanently excluded from validation):

| File | Convention |
|------|-----------|
| `README.md` | **Human-first project overview.** Not an AFDS document — no frontmatter, no rigor tier, no AI-oriented sections. Written for humans discovering the project. Structure is free-form but SHOULD include: project name, badges (CI, Docker, Python, License), one-line description, requirements, quick start, available features/tools, configuration reference, development/testing instructions, and license. |
| `AGENTS.md` | Agent command index |
| `CHANGELOG.md` | Project changelog |

### 2.3 Extending Types

Projects MAY define additional document types (e.g., `integration.*`, `api.*`, `guide.*`). When adding a type:

1. Define the ID prefix (e.g., `int.*`, `api.*`)
2. Define required body sections in a fixed order
3. Assign a TTL value (0–365)
4. Document the type in the project's local standard or README
5. Ensure all new types appear in the document registry

No project-defined type may conflict with the base types listed above.

**Example — Architecture Decision Record (`adr.*`):**

A common project-defined type is the Architecture Decision Record (ADR), following the pattern described by Michael Nygard. When adopting ADRs, the project defines:

```yaml
# Type definition
doc_id: adr.<NNN>-<slug>              # e.g., adr.001-use-postgres
type: decision                         # project-defined type
status: proposed                       # proposed | accepted | deprecated | superseded
ttl_days: 0                            # ADRs are permanent records
```

Required body sections for `adr.*`:

```markdown
## CONTEXT
## DECISION
## ALTERNATIVES_CONSIDERED
## CONSEQUENCES
## STATUS
## CHANGELOG
```

### 2.4 Archive

Documents that are no longer active move to an archive directory. Archived documents:

- Use `status: deprecated` or `status: archived`
- MUST NOT be deleted from the repository
- MUST include a deprecation notice pointing to the replacement

### 2.5 Document ID Schema

```yaml
# Format: <type>.<name>
# Base types:
doc_id: workflow.pre-commit-check      # ✅
doc_id: ref.python-code-style          # ✅
doc_id: sys.auth                       # ✅
doc_id: guide.onboarding-new-devs      # ✅
doc_id: decision.001-use-postgres      # ✅
doc_id: contract.api-auth-v2           # ✅

# Project-defined types:
doc_id: integration.slack              # ✅

# Invalid:
doc_id: pre-commit-check               # ❌ Missing type prefix
doc_id: workflow/pre-commit            # ❌ Slash instead of dot
doc_id: WORKFLOW.check                 # ❌ Must be lowercase
doc_id: auth-service                   # ❌ Missing type prefix
```

### 2.6 Composite Documents

Atomic documentation enables SSOT for AI retrieval but creates a readability cost for humans. Composite documents aggregate facts from multiple atomic sources for human navigation and narrative continuity.

**Summary documents** (`ref.*`, `rigor_tier: L1`):
- Read-only aggregations of key facts from multiple atomic sources
- Example: `ref.system-overview` listing endpoint URLs, key entities, and service boundaries
- Atomic sources remain authoritative; composite docs link to atomic — atomic docs never depend on composite docs

**Conceptual overviews** (`guide.*`, `rigor_tier: L1`):
- Narrative maps of system topology, data flow, and component relationships
- Designed for onboarding and architecture understanding
- Link to `ref.*` and `sys.*` for formal specification

**Rules:**
- Composite documents are read-only derivations — the atomic source is always authoritative
- Composite docs MUST list all source documents in `upstream`
- Atomic docs MUST NOT list composite docs in `downstream` (composites are consumers, not dependencies)
- See Section 9.2 for retrieval budget rules related to composite documents

---

## 3. YAML Frontmatter Schema

### 3.1 Minimal Frontmatter (ALL files)

```yaml
---
description: One sentence — what this document covers. No trailing period
---
```

### 3.2 Standard Frontmatter (Workflow, Reference, System)

```yaml
---
description: Authentication service handling OAuth2 token exchange and session management
doc_id: sys.auth
type: system          # workflow | ref | system | guide | decision | contract
status: active                    # active | draft | deprecated | evolving
rigor_tier: L2                    # L0 | L1 | L2 | L3 — controls required maintenance burden
doc_kind: atomic                   # atomic | composite | translation
ttl_days: 90
stability: stable                 # experimental | stable | frozen
ai_scope: editable                # editable | review_only | restricted
domain: backend                   # Optional: project-specific domain
tags: ["auth", "oauth2"]          # Optional: discovery labels — lowercase strings
upstream:
  - ref.security-policy
supersedes: null                  # doc_id this document replaces (null if none)
superseded_by: null               # doc_id that replaces this document (null if none)
source_of_truth: true             # true = this file defines authoritative facts for its domain
last_verified: 2026-05-08         # ISO date, auto-updated by validation
owners: ["backend-team"]          # Optional: team ownership label
verification_status:
  - human_reviewed                # human_reviewed | runtime_verified | ai_generated | partially_verified
evidence:                         # Optional: provenance of facts
  rules:
    - type: code
      path: src/auth/*
---
```

### 3.3 Workflow-Specific Frontmatter

```yaml
---
description: GO/NO-GO check before commits — runs tests, scans logs, validates docs
doc_id: workflow.pre-commit-check
type: workflow
trigger:                          # Required for workflows
  user: ["pre-commit-check", "validate commit"]
  event: pre-commit
scope: read-only
timeout: 60                       # seconds
output:                           # Structured output schema
  verdict: "GO" | "NO-GO"
  failures: list[string]
  warnings: list[string]
---
```

### 3.4 Field Reference Table

| Field | Required | Type | Valid Values | Default |
|-------|----------|------|--------------|---------|
| `description` | Always | string | 1 sentence, no period | — |
| `doc_id` | Type≠archive | string | `<type>.<name>` | — |
| `type` | Type≠archive | enum | `workflow` \| `ref` \| `system` \| `guide` \| `decision` \| `contract` (+ project-defined) | — |
| `status` | Type≠archive | enum | `active` \| `draft` \| `deprecated` \| `evolving` \| `archived` | `active` |
| `rigor_tier` | Type≠archive | enum | `L0` \| `L1` \| `L2` \| `L3` | `L2` |
| `version` | Optional (contract.* only) | string | SemVer (e.g. `1.0.0`), for API contracts | — |
| `ttl_days` | Type≠archive | integer | 0–365, `0` = deprecated | 90 |
| `ttl_policy` | Optional (L2+ Recommended) | enum | `standard` \| `extended` \| `permanent` \| `event_driven` | `standard` |
| `doc_kind` | Optional (L2+ Recommended) | enum | `atomic` \| `composite` \| `translation` | `atomic` |
| `stability` | Optional | enum | `experimental` \| `stable` \| `frozen` | `stable` |
| `ai_scope` | Optional | enum | `editable` \| `review_only` \| `restricted` | `editable` |
| `upstream` | Optional | list | Valid `doc_id` values | `[]` |
| `trigger` | Workflow only | object | See 3.3 | — |
| `timeout` | Workflow only | integer | seconds | 120 |
| `supersedes` | Optional | string | Valid `doc_id` or `null` | `null` |
| `superseded_by` | Optional | string | Valid `doc_id` or `null` | `null` |
| `derived_from` | Required if doc_kind != atomic | list | Valid `doc_id` values | `[]` |
| `source_of_truth` | Optional | boolean | `true` \| `false` | `true` |
| `domain` | Optional | string | lowercase identifier (project-defined) | — |
| `tags` | Optional | list | lowercase strings | `[]` |
| `owners` | Optional | list | team/role identifiers | `[]` |
| `verification_status` | Optional | list | `human_reviewed` \| `runtime_verified` \| `ai_generated` \| `partially_verified` | `[]` |
| `evidence` | Optional | object | Per-section provenance: `code` \| `test` \| `runtime` \| `human` \| `external` | — |
| `verified_against` | Optional | list | Paths to runtime artifacts (e.g. `docker-compose.yml`, `openapi.yaml`) | `[]` |
| `generated_by` | Optional | list | Agent name + version (e.g. `opencode v0.9`) | `[]` |
| `last_verified` | Type≠archive | date | ISO 8601, updated on content change | — |
| `fitness_score` | CI-only | float | 0.0–1.0, computed by homeostasis scan, stored in `docs/meta/health-report.md` | Not stored in frontmatter. |

### 3.5 `ai_scope` Semantics

| Value | AI Permissions | Use Case |
|-------|----------------|----------|
| `editable` (default) | MAY read, modify, update frontmatter | Standard workflows, refs |
| `review_only` | MAY read, flag issues; MUST NOT modify | `DOCUMENTATION_STANDARD.md`, `AGENTS.md` core rules |
| `restricted` | MUST NOT access (policy label, not a security boundary) | Security runbooks, API keys, crisis patterns |

> **Note:** `ai_scope: restricted` is a policy label, not a security boundary. Files in a repository are readable by anyone with repo access. For actual access control, store sensitive documents in a separate repository with restricted permissions, or use encryption (git-crypt / SOPS).

### 3.6 `status` Semantics

| Status | Meaning | AI Behavior |
|--------|---------|-------------|
| `active` | Accurately reflects current system | Follow without question |
| `draft` | Work in progress | Do not cite as authoritative |
| `evolving` | System actively changing; may lag by 1 sprint | Check `last_verified`; warn if >30 days |
| `deprecated` | Replaced or removed | Do not follow; link to replacement |
| `archived` | Moved to archive, no longer active | Read for historical reference only; link to replacement |

### 3.7 `rigor_tier` Semantics

`rigor_tier` controls the operational cost of maintaining a document. Higher tiers impose greater maintenance burden, review rigor, and validation requirements.

| Tier | Use Case | Narrative | Default Type |
|------|----------|-----------|---------------|
| **L0** | Scratchpad, research, temporary notes | Permitted | — |
| **L1** | Human-first operational docs, guides, runbooks | Permitted | `guide.*` |
| **L2** | Structured production knowledge, authoritative specs | Prohibited | `ref.*`, `sys.*`, `workflow.*` |
| **L3** | Compliance, safety, critical infrastructure | Prohibited | — |

**Tier-Dependent Mechanism Table:**

| Mechanism | L0 | L1 | L2 | L3 |
|-----------|----|----|----|----|
| CHANGELOG | Optional | Optional (single-line OK) | Required | Strict (append-only, versioned) |
| `upstream` links | Optional | Optional | Required | Required |

---

## 4. Body Schema

### 4.1 Mandatory Section Order

```markdown
# <TITLE>

## PURPOSE
<1-3 sentences. Active voice. No filler.>

## SCOPE
- INCLUDED: <explicit list>
- EXCLUDED: <explicit list>

## DEFINITIONS
- `term`: <precise, non-circular definition>

## RULES
1. System MUST ...
2. System MUST NOT ...
3. IF <condition> THEN <action>

## INTERFACES
- INPUT: <param>: <type> | <constraints>
- OUTPUT: <param>: <type> | <guarantees>
- SIDE_EFFECTS: <list or N/A>

## STATE
- Assumptions: <list>
- Constraints: <list>
- Known_Limitations: <list>

## EDGE_CASES
- CASE: <condition> → EXPECTED: <deterministic behavior>

## EXAMPLES
- EXAMPLE 1:
  - INPUT: <value>
  - OUTPUT: <value>
  - RATIONALE: <why this matches RULES>

## NON_GOALS
- <what this document intentionally does not cover>

```

### 4.1a SSOT for Definitions

`docs/meta/glossary.md` is the SSOT for global/domain terms. Per-document `DEFINITIONS` sections contain only:
- Terms specific to that document (not used elsewhere)
- References to global glossary entries: `- term: See docs/meta/glossary.md#term`

A document MAY declare which glossary terms it depends on via the optional `glossary_terms` frontmatter field (list of term keys). This enables CI to detect when glossary definitions change and flag affected documents for review.

### 4.2 Section Rules

| Rule | Enforcement |
|------|-------------|
| Sections appear in exact order for workflow.* and contract.* | CI validation blocks on reorder |
| Sections must be present for ref.*, sys.*, guide.*, decision.*; order is flexible | CI warns on reorder |
| Empty sections contain `N/A` — never omit the header | CI validation |
| CHANGELOG is append-only — never delete entries | Pre-commit hook |
| EXAMPLES never override RULES — RULES win in conflict | Conflict resolution protocol |
| One H1 per file | CI validation |
| No version numbers or dates in body (except CHANGELOG) | Banned pattern detection |

### 4.3 Type-Specific Required Sections

Each document type has its own required section set. The base schema (Section 4.1) applies to `ref.*` documents. Other types use the schemas below. Required sections vary by `rigor_tier` (Section 3.7).

**Section Requirements by Tier:**

| Section | L0 | L1 | L2 | L3 |
|---------|----|----|----|----|
| `PURPOSE` | Recommended | Required | Required | Required |
| `SCOPE` | Optional | Required | Required | Required |
| All other type-specific sections | Not enforced | Recommended | Required | Strict (no `N/A` without justification) |

**`workflow.*` — Agent Procedure**

```markdown
## PURPOSE
## SCOPE
## TRIGGER
## STEPS
## VALIDATION
## PITFALLS
## ROLLBACK
```

**`sys.*` — System Documentation**

```markdown
## PURPOSE
## SCOPE
## ARCHITECTURE
## ENTITY_REFERENCE
## INTERFACES
## STATE
## EDGE_CASES
## FAILURE_MODES
## TESTING
## TROUBLESHOOTING
```

`FAILURE_MODES` — what the system does under failure conditions (input perspective): `WHEN <condition> THEN <system response>`.
`TROUBLESHOOTING` — how an operator diagnoses and resolves failures (operator perspective).

**`ref.*` — Reference (default)**

Uses the base schema from Section 4.1 (`PURPOSE → SCOPE → DEFINITIONS → RULES → INTERFACES → STATE → EDGE_CASES → EXAMPLES → NON_GOALS`).

**`guide.*` — Narrative Guide**

`guide.*` documents are designed for onboarding, architecture rationale, postmortems, ADR context, incident timelines, and debugging stories. Narrative prose is permitted in all sections — guides prioritize knowledge transfer over formal specification. Guide documents permit a conversational, teaching-oriented tone. Junior developers must be able to follow the narrative. AXIOM 8 (Knowledge Transfer) takes priority over formal rigidity. Formal constraints (banned words, sentence length, active voice) are not enforced in guide.*. Default `rigor_tier: L1`.

```markdown
## PURPOSE
## AUDIENCE
## CONTEXT
## WALKTHROUGH
## RATIONALE (optional)
## TRADEOFFS (optional)
## PITFALLS
## RELATED_DOCS
```

`AUDIENCE` — who this guide is written for (role, experience level).
`CONTEXT` — background, motivation, and causality (narrative permitted).
`WALKTHROUGH` — step-by-step explanation with examples (narrative permitted).
`RATIONALE` — why specific decisions were made, what alternatives existed (narrative permitted).
`TRADEOFFS` — costs, risks, and consequences of the chosen approach (narrative permitted).
`RELATED_DOCS` — links to authoritative `ref.*`, `sys.*`, or `workflow.*` that provide the formal specification. Guides link to specs — never the reverse.

**`decision.*` — Architecture Decision Record**

`decision.*` documents record significant architectural decisions. Based on Michael Nygard's ADR pattern. Immutable after acceptance. Default `rigor_tier: L3`. `ttl_days: 0` (permanent records).

```markdown
## CONTEXT
## DECISION
## ALTERNATIVES_CONSIDERED
## CONSEQUENCES
## STATUS
## CHANGELOG
```

`CONTEXT` — Problem statement, forces, constraints, stakeholders.
`DECISION` — What was decided and why (brief).
`ALTERNATIVES_CONSIDERED` — Options evaluated with pros/cons.
`CONSEQUENCES` — Positive, negative, risks, mitigations.
`STATUS` — Lifecycle: `proposed` → `accepted` | `rejected` → `deprecated` → `superseded` (with dates).

**`contract.*` — API Contract / Schema**

`contract.*` documents specify API contracts, data schemas, and service interfaces. Linked to actual specification files (OpenAPI, GraphQL schema, Protobuf). Default `rigor_tier: L3`. `ttl_days: 0` (versioned, not expired).

```markdown
## PURPOSE
## SPECIFICATION
## VERSIONING
## CHANGELOG
```

`SPECIFICATION` — Link to specification file (OpenAPI YAML, GraphQL schema, .proto) plus inline critical schemas.
`VERSIONING` — Current version, compatibility matrix, migration guide reference.

### 4.3a Normative vs Informative Sections

Sections carry different authority in conflict resolution, fitness computation, and CI enforcement.

| Category | Sections | Authority | Banned Words | Examples |
|----------|----------|-----------|--------------|----------|
| **Normative** | RULES, INTERFACES, VALIDATION, SPECIFICATION | Defines requirements; binding in CI | Enforced at L3 only | "Token MUST expire after 1 hour" |
| **Informative** | PURPOSE, CONTEXT, RATIONALE, EXAMPLES, PITFALLS, WALKTHROUGH, AUDIENCE | Provides context; not binding | Not enforced | "This guide explains the token flow" |
| **Hybrid** | ARCHITECTURE, STATE, FAILURE_MODES | Normative at L3; informative at L1-L2 | Enforced at L3 only | Varies by tier |

Conflict resolution: when an informative section contradicts a normative section, the normative section wins. When two normative sections contradict across documents, apply the Conflict Resolution hierarchy (Section 8).

**Project-Defined Types**

Projects that define additional document types MUST specify the required body sections in their project-level configuration. The section order for any project-defined type MUST be documented and enforced by CI. New types MUST declare a default `rigor_tier`.

**Rules:**

- Sections not in the type's schema MUST NOT appear (keeps documents atomic)
- If a document requires a section from a different type's schema, it belongs to a different type
- At L2 and L3: each type MUST include all sections listed above in the exact order shown
- At L2 and L3: empty sections contain `N/A` — never omit the header
- At L1: `PURPOSE` and `SCOPE` are required; remaining sections are recommended
- At L0: only `description` in frontmatter is required; body is free-form

### 4.4 Pattern Templates

Concrete fill-in-the-blank templates for common documentation tasks. Agents MUST use these templates when writing structured content inside body sections.

**Template A — Behavior Description** (use in INTERFACES, STEPS, ARCHITECTURE sections)

```text
INPUT:
- <param>: <type> | <constraints>

PROCESSING:
1. <step>
2. <step>

OUTPUT:
- <param>: <type> | <guarantees>

FAILURE MODES:
- WHEN <condition> THEN <system response>
```

**Template B — Rule Definition** (use in RULES section when rule needs justification or has non-obvious violation)

```text
RULE: <rule_id>
CONDITION: <when this rule applies>
ACTION: System MUST <required behavior>
RATIONALE: <why this rule exists>
VIOLATION: <what happens if broken>
```

Usage guidance:

- Simple rules remain as `System MUST <behavior>` bullets — Template B is OPTIONAL
- Template B is REQUIRED when RATIONALE or VIOLATION is non-obvious
- Template A is REQUIRED when documenting multi-step behavior with failure paths

---

## 5. Controlled Language

### 5.1 Banned Words (Regex for Linter)

> **Agent note:** Banned-word enforcement is a linter concern (Phase 0, pre-commit hooks), not an AI generation directive. Agents write for clarity; linters flag violations post-hoc. Do not constrain natural language generation during content creation.

Lowercase ambiguous words are banned. Uppercase RFC 2119 modals (`SHOULD`, `SHOULD NOT`) are permitted — see Section 5.3.

Banned words are ambiguity killers — words that mask vagueness and harm AI parseability regardless of context. They MUST NOT appear in any document at any tier.

Linting scope: banned-word checks run on prose body text in RULES, INTERFACES, and VALIDATION sections only. The linter MUST exclude:
- Fenced code blocks
- Inline code
- Link URLs
- Frontmatter YAML
- Table headers and pipe-delimited cells (except descriptive text columns)

This prevents false positives in code examples, configuration snippets, and reference URLs.

```regex
\b(might|maybe|possibly|probably|often|sometimes|usually|generally|typically|etc|simply|just)\b
```

### 5.2 Project-Specific Banned Words

Each project MUST define its own table of domain-specific terms that are ambiguous in that project's context. Use this format:

| Banned | Replace With | Rationale |
|--------|--------------|-----------|
| `<ambiguous term>` | `<specific replacement>` | `<why ambiguous in this project>` |

This section MUST be customized per project. Delete this paragraph and the example table, then fill the table with your project's terms.

### 5.3 Allowed Modals (RFC 2119)

Lowercase `should` is banned (see Section 5.1). Only uppercase RFC 2119 modals are permitted.

| Modal | Meaning |
|-------|---------|
| `MUST` | Absolute requirement — no exceptions |
| `MUST NOT` | Absolute prohibition |
| `SHOULD` | Recommended; deviation requires documented justification |
| `SHOULD NOT` | Not recommended; adherence is preferred |
| `MAY` | Optional, permitted |
| `ALWAYS` | Invariant behavior in all conditions |
| `NEVER` | Prohibited behavior in all conditions |

`MUST` and `MUST NOT` are the preferred modals for requirements. `ALWAYS` and `NEVER` are reserved for pure invariants that hold under all conditions without exception (e.g., "The doc_id format is ALWAYS `<type>.<name>`"). In distributed systems and operational documentation, prefer `MUST`/`MUST NOT` — they carry the same weight but acknowledge that environmental failures may prevent compliance.

**Correct usage (rule or agent instruction):**
```markdown
Agents MUST read this standard before writing any documentation file.
Agents MUST NOT add version numbers or dates to document bodies.
```

**Incorrect usage (describing system behavior):**
```markdown
❌ "The sensor MUST return a float value."
✅ "The sensor returns a float value."
```

### 5.4 Syntax Rules

| Rule | Example |
|------|---------|
| Active voice only | `System validates input` — not `Input is validated` |
| Prefer bulleted lists for complex conditions | Linter: Warn |
| One thought per sentence | No compound sentences with `;` |
| No rhetorical questions | — |
| Normative sections use strict controlled language | RULES, INTERFACES, VALIDATION require formal, deterministic prose |
| Descriptive sections prioritize clarity over formal rigidity | CONTEXT, WALKTHROUGH, RATIONALE, TRADEOFFS allow natural language |
| `guide.*` type permits narrative in all sections, plus optional `RATIONALE` and `TRADEOFFS` | Rule waived for guide |
| No explanatory parentheses | Use separate bullet or DEFINITION |

### 5.5 Formatting Rules

**Prohibited formatting — MUST NOT use:**

- Tables with more than 4 columns MUST NOT exist in non-ref documents. `ref.*` standards MAY exceed 4 columns when displaying field definitions, compatibility matrices, or status matrices. Normative logic in wide tables MUST have equivalent bullet rules.
- Nested lists deeper than 3 levels
- Bold (`**text**`) for emphasis within sentences — use RFC 2119 modals instead
- HTML tags anywhere in document body (except `<!-- -->` comments permitted)
- Horizontal rules (`---`) within sections — only between top-level sections
- Emoji in document body text

**Tables — MAY use for:**

- Field definitions: parameter name, type, valid values, default
- Compatibility matrices
- Status matrices
- Version mapping tables

Tables MUST NOT contain normative logic that is not also expressible as bullet rules.

**Stable section labels:**

Section names MUST be stable across all documents of the same type. MUST NOT alternate between synonyms within the same type schema.

```text
❌  FAILURES / ERRORS / KNOWN ISSUES  (pick one per type)
✅  FAILURE_MODES  (consistent label in sys.* schema)
```

---

## 6. Fitness Function

### 6.1 Computation Algorithm

Fitness score is **advisory telemetry, not a gating criterion**. Agents MUST NOT optimize for score at the expense of real quality. Human judgment overrides fitness score. Score thresholds differ by `rigor_tier` (see Section 3.7). At L0, fitness is not computed.

```python
def calculate_fitness(doc, graph):
    """Advisory only. Score is informational telemetry, never a gating criterion."""

    if doc.rigor_tier in (None, "L0"):
        return None

    if ttl_days == 0:
        freshness = 1.0  # Permanent documents do not decay
    else:
        freshness = max(0, 1 - (days_since_verified / ttl_days))

    clarity = (
        0.40 * banned_word_absence(doc) +
        0.30 * sentence_length_compliance(doc) +    # <=25 words
        0.30 * definition_coverage(doc)              # all terms defined
    )

    consistency = (
        0.40 * schema_section_order(doc) +
        0.30 * terminology_uniformity(doc, graph) +
        0.30 * link_integrity(doc, graph)            # upstream resolve
    )

    completeness = (
        0.60 * mandatory_sections_present(doc) +
        0.40 * link_coverage(doc, graph)
    )

    raw = (
        clarity      * 0.30 +
        consistency  * 0.25 +
        completeness * 0.20 +
        freshness    * 0.25
    )

    penalties = (
        orphan_penalty(doc, graph) * 0.10
    )

    return max(0.0, min(1.0, raw - penalties))
```

`ttl_days == 0` means permanent document (decisions, contracts). Freshness is 1.0 — these documents do not auto-decay.

### 6.2 Decision Thresholds

| Score | Status | Action |
|-------|--------|--------|
| ≥ 0.85 | Healthy | No action |
| 0.70–0.84 | Degraded | Optional review |
| 0.50–0.69 | Poor | Advisory flag |
| < 0.50 | Low | Advisory flag |

> **Important:** Fitness score is advisory telemetry. It MUST NOT block merges, CI validation, or document acceptance. Scores exist in `docs/meta/health-report.md` for trend analysis, not governance. Human judgment overrides all score-based recommendations.

### 6.3 Mutation Gate

A change is accepted when:
```text
schema_valid(new_doc) == true
AND banned_words(new_doc, tier_independent_only=true) == 0
AND all_upstream_links_resolve(new_doc, graph) == true
```

**Exception:** Breaking change MAY temporarily lower fitness if accompanied by a downstream migration plan.

---

## 7. Autonomic Processes

### 7.1 Homeostasis (Scheduled Scan)

```text
TRIGGER: Daily cron (or on-commit)

1. FOR each doc in /docs:
   a. IF days_since(last_verified) > ttl_days:
      → SET status = "evolving"
      → CREATE review task
   b. COMPUTE fitness_score
      → IF < 0.50: FLAG as Low
      → IF < 0.70: FLAG as Poor
2. VALIDATE upstream links
   → IF broken: FLAG both endpoints
3. SCAN semantic similarity across all docs (advisory always)
   → Similarity >0.85 flags the pair for human review. Never blocks CI.
   → Shared concepts (e.g., "user", "token") naturally co-occur.
     Human review determines whether consolidation is needed.
4. OUTPUT: health-report.md
```

### 7.2 Mitosis (File Splitting) — Advisory

File splitting is never automatic. Consider splitting when ALL of the following are true:
- File describes two or more independent entities (e.g., two services, two unrelated APIs)
- File mixes specification with narrative content (different types — use `ref.*` + `guide.*` instead)
- One section exceeds 200 lines while others remain under 50 (unbalanced structure)
- Each resulting file is at least 30 lines (splits below this threshold degrade navigation without benefit)

DO NOT SPLIT when ANY of the following is true:
- Concepts are tightly coupled (e.g., request schema + response schema for the same endpoint)
- All sections contribute to a single operational understanding
- The concept is a single logical entity with multiple facets (e.g., auth service: token flow + session management + role mapping)
- Splitting creates more than 3 new `upstream` references per downstream consumer

```text
1. Human identifies concept boundaries using heuristics above
2. Human creates new files with new doc_ids
3. Human distributes content to correct new files
4. Human updates upstream references in affected files
5. Set original status = "deprecated", add superseded_by
6. Update registry
```

### 7.3 Apoptosis (Programmed Deprecation)

```text
TRIGGER: fitness < 0.50 for 30 days
         OR status "deprecated" > 90 days
         OR superseded_by is set AND downstream migrated

1. VERIFY no active docs list this in upstream
2. IF upstream refs exist: UPDATE those docs first
3. SET status = "archived"
4. MOVE to /archived
5. APPEND final CHANGELOG entry
6. NEVER delete from repository
```

---

## 8. Conflict Resolution

```text
Priority (highest to lowest):
1. docs/DOCUMENTATION_STANDARD.md (this file)
2. AGENTS.md "Non-Negotiable Rules" section
3. RULES section in any document
4. INTERFACES section
5. EXAMPLES section
6. Upstream document > downstream document
7. Newer version > older version (by CHANGELOG date)
8. Explicit statement > implicit assumption

Resolution Process:
1. Quote conflicting statements with exact file paths
2. Apply priority order above
3. Modify lower-priority document
4. If equal priority: HALT, create Decision Record
5. NEVER silently resolve security-related conflicts
```

---

## 9. Repository Structure

AFDS imposes minimum structure requirements. Projects adapt paths to their conventions.

```text
<project-root>/
├── docs/
│   ├── <standard-file>.md          # This standard (single source of truth)
│   ├── meta/
│   │   ├── glossary.md             # SSOT for all term definitions
│   │   ├── doc-registry.md         # Index of all doc_ids
│   │   └── health-report.md        # Generated by homeostasis
│   ├── workflows/                  # workflow.* documents
│   ├── systems/                    # sys.* documents (optional)
│   ├── reference/                  # ref.* documents (optional)
│   ├── templates/
│   │   └── document-template.md
│   └── archived/                   # Deprecated docs (never delete)
│
└── AGENTS.md                       # Agent command index (optional)
```

### 9.1 Structure Rules

| Rule | Enforcement |
|------|-------------|
| Max 1 nesting level in categories | CI validation |
| Filenames MUST equal `doc_id` in kebab-case + `.md` | Pre-commit hook |
| `docs/meta/doc-registry.md` updated on every create/move/deprecate | CI validation |
| `docs/archived/` is append-only — never delete | Pre-commit blocker |

### 9.2 Context Budget and Retrieval Boundaries

Atomic documentation enables SSOT but creates a retrieval cost that grows with document count. Agents MUST observe context budget rules to prevent reading excessive files before forming an answer.

**Retrieval depth limits:**

| Parameter | Limit | Rationale |
|-----------|-------|-----------|
| Max `upstream` depth traversal | 3 levels | Prevents infinite chain traversal |
| Max files read per query | 12 | Bounded by typical context window |
| Max dependency graph subgraph | 15 nodes | Total docs in any single retrieval tree |

**Summary documents:**

A project MAY define one or more **summary documents** (type `ref.*`, `rigor_tier: L1`) that aggregate key facts from multiple atomic sources. See Section 2.6 for composite document rules. Summary documents are read-only derivations — the atomic sources remain authoritative. Example: `ref.system-overview` listing endpoint URLs, key entities, and service boundaries without duplicating detail.

**Retrieval strategy for agents:**

1. Check `docs/meta/doc-registry.md` for relevant `doc_id`
2. Read the matched document; follow `upstream` only if needed
3. Stop traversal when `upstream` depth exceeds 3 or file count exceeds 12
4. If more context is needed, request explicit instruction from the user

### 9.3 Automatic Reference Discovery (Phase 2)

When Phase 2 tooling is available, these reference patterns are auto-discovered as link suggestions. Suggestions are presented to the author — they are not automatically applied.

| Reference Pattern | Maps To | Example |
|-------------------|---------|---------|
| `doc_id` mention in body text (e.g., `ref.auth-service`) | `upstream` suggestion | Body references another document by ID |
| Cross-file Markdown link `[text](./file.md)` | `upstream` / `downstream` | Standard Markdown internal links |
| Entity/endpoint name matching another document's SCOPE | `upstream` suggestion | `POST /auth/login` mentioned in `sys.gateway` |
| `@owner:team-name` mention in body text | `owners` suggestion | `Contact @owner:backend-team for updates` |

Auto-discovered suggestions are advisory only. Human review determines whether to accept, reject, or override each suggestion. Full automation of link creation is not available — graph authority remains with human maintainers.

### 9.4 Graph Safety Limits

The dependency graph grows with each atomic document. Unchecked growth degrades retrieval performance and creates unmaintainable dependency chains. CI enforces these limits at L2+.

| Limit | Threshold | L1 Action | L2+ Action |
|-------|-----------|-----------|------------|
| Cycle detection | Any cycle | Advisory | Block |
| Max direct upstream per document | 10 | Advisory | Warn |
| Max total downstream (fan-out) | 50 | Advisory | Warn |
| Max graph depth (upstream chain) | 5 | Advisory | Warn |
| Max subgraph size (total nodes reachable) | 30 | Advisory | Warn |

When a graph limit is exceeded, the recommended action is to:
1. Check if the document can be split (see Section 7.2 Granularity Heuristics)
2. Introduce an intermediary abstraction document
3. Consolidate tightly-coupled documents into a composite (see Section 2.6)
4. Review whether all `upstream` references are truly required

Graph metrics are computed by tooling and reported in `docs/meta/health-report.md`.

---

## 10. AI Agent Protocol

```text
You are an autonomous Documentation Maintainer operating under AFDS.

PRIME DIRECTIVES:
0. METADATA: Never update version, last_verified, fitness_score, or other metadata fields. These are CI-managed. Agent writes content only. CI/post-commit hooks update metadata.
1. SSOT: Search before creating. Link, never duplicate.
2. SCHEMA: Follow type-specific body schema. Narrative in guide.*, formal in ref.*/sys.*.
3. LANGUAGE: Tier-independent banned words only. Natural prose where clarity demands it.
4. EVOLUTION: Update last_verified. Append CHANGELOG for contract.* and decision.* documents only.
5. INTEGRITY: Verify upstream references resolve to existing files. Bidirectional consistency is not required.

READ PROTOCOL:
1. Parse YAML frontmatter first.
2. Check status — if deprecated/archived, seek superseding doc.
3. RULES section is authoritative. Informative sections provide context only.
4. Verify the target of each upstream reference exists. Do not verify bidirectional consistency.
5. Stop traversal at 3 levels depth or 8 files read total. Request user instruction if more needed.
6. If fitness_score < 0.70: mention it, do not block on it.

WRITE PROTOCOL:
1. Search for existing doc_id covering this concept.
2. If concept exists: extend or reference the existing document. Never duplicate.
3. If new: generate unique doc_id, populate mandatory sections per type + tier.
4. Set status: "draft". Set doc_kind and derived_from if non-atomic.
5. Identify upstream references. Add to frontmatter.

UPDATE PROTOCOL:
1. Read target document. Follow upstream only if RULES or INTERFACES changed.
2. If RULES changed: output `NEEDS_DOWNSTREAM_REVIEW: [list of doc_ids]` at end of response. Do not traverse or modify downstream files. CI/event bus opens review issues.
3. Update last_verified.
4. For contract.* only: increment version. Append CHANGELOG for contract.* and decision.* documents only.

CONFLICT PROTOCOL:
If two documents contradict:
1. Identify conflicting statements with exact quotes.
2. Apply priority hierarchy: standard > upstream > RULES > INTERFACES > EXAMPLES > newer.
3. If equal priority: flag as KNOWLEDGE CONFLICT. Never silently resolve.
4. Output conflict using the KNOWLEDGE CONFLICT format below.

KNOWLEDGE CONFLICT OUTPUT FORMAT:
When conflict is detected, output exactly:

  ## KNOWLEDGE CONFLICT
  - conflict_type: semantic | structural | temporal | authority
  - source_a: <file path>
  - source_b: <file path>
  - statement_a: "<exact quote from source_a>"
  - statement_b: "<exact quote from source_b>"
  - priority_verdict: <which wins per hierarchy, or "equal">
  - recommended_action: update_source_b | update_source_a | escalate_to_human | create_decision_record

UNCERTAINTY PROTOCOL:
1. Do not guess. Do not fabricate.
2. Add explicit EDGE_CASE describing the uncertainty.
3. Set status to "evolving" if uncertainty affects normative sections.
4. Flag for human review.

OUTPUT FORMAT:
Raw Markdown with YAML frontmatter only.
No conversational text. No meta-commentary.
No "Here is the documentation" preamble.
```

---

## 11. CI/CD Validation

CI validation scales with rigor_tier. Only 6 checks block merges. L0 documents are exempt from all checks.

| Check | L1 Action | L2 Action | L3 Action |
|-------|-----------|-----------|-----------|
| YAML valid + required fields | Warn | Block | Block |
| Frontmatter present (even if minimal) | Warn | Block | Block |
| Mandatory sections present (per tier) | Warn | Block | Block |
| No duplicate section headings (case-normalized) | Warn | Warn | Block |
| Sections match declared type schema | Info | Info | Warn |
| Tier-independent banned words | Skipped | Warn | Block |
| doc_id unique across repo | Block | Block | Block |
| Upstream links resolve | Skipped | Block | Block |
| CHANGELOG updated (contract.* + decision.* only) | Skipped | Skipped | Block |
| `version` field correct (contract.* only) | Skipped | Skipped | Block |

---

## 12. Deprecation Workflow

### 12.1 When to Deprecate

```yaml
deprecate_when:
  - System component removed (e.g., service deleted from docker-compose.yml)
  - Workflow replaced by new version (e.g., workflow.v2.*)
  - Feature flag permanently disabled
  - Migration completed (e.g., Python → .NET)

do_not_deprecate_for:
  - Stale content (update instead)
  - Incomplete sections (complete instead)
  - Minor inaccuracies (correct instead)
```

### 12.2 Deprecation Steps

```markdown
1. Set frontmatter:
   ```yaml
   status: deprecated
   ttl_days: 0
   ai_scope: review_only
   description: Old description — superseded by <replacement_doc_id>
   ```

2. Add callout after H1:
   ```markdown
   > [!WARNING]
   > This document is deprecated. Use [Replacement Name](./replacement.md) instead.
   ```

3. Update `AGENTS.md` entry with `[DEPRECATED]` prefix

4. After 90 days:
   ```bash
   git mv docs/old.md docs/archived/YYYY-MM/old.md
   ```

5. Add to `docs/archived/INDEX.md`
```

---

## 13. Anti-Pattern Catalog

| Anti-Pattern | Symptom | Fix |
|--------------|---------|-----|
| **Zombie Workflow** | `workflow.*` with `last_verified > 180 days` | Flag for review; deprecate if obsolete |
| **Knowledge Duplication** | Same fact in multiple files as authoritative | Consolidate to one location; replace others with links |
| **Hallucination Cascade** | AI generates content not in existing docs | Enforce doc search before creation; use `upstream` |
| **Structural Drift** | Documents deviate from template | CI schema validation blocks commit |
| **Knowledge Decay** | `ttl_days` exceeded; AI treats stale info as current | Flag `status: evolving` when TTL exceeded |
| **Implicit Rules** | Expected behavior only in EXAMPLES | Extract explicit rule to RULES section |
| **Narrative Prose** | Storytelling in normative sections of non-guide documents | Rescope as `guide.*` or move content to CONTEXT/WALKTHROUGH |
| **Hidden Assumptions** | Behavior implied but not stated | State explicitly; add `> [!NOTE]` callout |
| **Circular Dependencies** | File A lists File B in `upstream`; File B lists File A in `upstream` | Extract shared concept to a third file; both files depend on it |
| **Unversioned Changes** | Content changed but no CHANGELOG entry; `last_verified` not updated | Enforce CI CHECK-06 and CHECK-07; flag file for correction |
| **Orphan Workflow** | Workflow not referenced by any other doc | Link from relevant docs or deprecate |
| **Mega-Workflow** | Single workflow exceeds configured line limit | Split into sub-workflows |
| **Protocol Drift** | Document does not match actual code or system behavior | Regenerate from source; add `upstream` link |
| **Security Bypass** | Document suggests skipping security checks | Flag as security violation; escalate |
| **Ambiguous Reference** | Document uses vague terms like "the service", "the agent" without qualifier | Use full qualified name; add to Project-Specific Banned Words (5.2) |
| **Metric Gaming** | Agent adds artificial definitions, splits sentences, or generates low-value edge cases to inflate fitness score | Fitness is advisory only; human judgment overrides; flag artificially inflated documents for review |
| **Overformalization** | L0 scratch notes forced into full L3 schema, killing iteration speed | Use `rigor_tier` correctly; do not escalate tier without justification |
| **Atomization Death Spiral** | Files split until dependency graph is unreadable and context retrieval exceeds budget | Apply anti-overfragmentation heuristics (Section 7.2); prefer composite documents (Section 2.6) |
| **Document Explosion** | Atomic files multiply unchecked, making the dependency graph unreadable | Apply aggregate docs (Axiom 2); enforce retrieval boundaries (Section 9.2) |

---

## 14. Mutation Rules

Defines what AI agents MAY and MUST NOT do per operation type. The `ai_scope` field governs access at the file level; this section governs per-action permissions within an accessible file.

### 14.1 Permitted Autonomously (MAY perform without explicit instruction)

- Add frontmatter to files that lack it
- Fix banned-word violations in prose
- Remove inline metadata patterns (dates, version blocks in body)
- Add content to EDGE_CASES, EXAMPLES sections
- Add cross-reference links
- Update `description` field for clarity when meaning is unchanged
- Add `> [!NOTE]` or `> [!WARNING]` callouts
- Update `last_verified` after verification

### 14.2 Requires Explicit User Instruction

- Change the meaning of any factual claim or behavioral description
- Split or merge files (mitosis)
- Mark a document as `deprecated` or `archived`
- Change `ai_scope`, `stability`, or `doc_id`
- Delete any section content (metadata blocks or body text)
- Set `superseded_by` or `supersedes`

### 14.3 Prohibited (MUST NOT perform, ever)

- Delete files from the repository
- Modify files in `docs/archived/`
- Modify files where `ai_scope: restricted`
- Change the meaning of RULES sections without explicit user approval
- Remove or reorder CHANGELOG entries
- Modify a document with `stability: frozen` without explicit instruction
- Silently resolve a detected conflict — ALWAYS flag it

### 14.4 Mutation Gate

A change passes only when:

```text
schema_valid(new_doc) == true
AND banned_words(new_doc, tier_independent_only=true) == 0
AND all_upstream_links_resolve(new_doc, graph) == true
```

---

## 15. Schema Amendment Process

This standard is subject to evolution. Amendments follow a defined process to prevent undocumented drift.

### 15.1 When to Amend

Amend this standard when:

- A new document type is needed
- A required frontmatter field changes (add, rename, remove)
- A body schema section is added or renamed
- A banned word list changes
- A fitness function weight changes

Do NOT amend for: adding new documents, updating existing docs, migrating content.

### 15.2 Amendment Steps

```text
1. IDENTIFY the change: quote exact old text and proposed new text
2. LIST all downstream docs affected by the change
3. IF new required frontmatter fields: migrate ALL existing docs in the same commit
4. IF body schema changes: update docs/templates/document-template.md first
5. UPDATE docs/meta/doc-registry.md if doc types change
6. APPEND to this document's CHANGELOG with version increment:
   - Major: breaking change to required fields or section order
   - Minor: new optional field, new section type, new anti-pattern
   - Patch: clarification, example update, wording fix
7. SET last_verified to amendment date
```

### 15.3 Amendment Authority

- AI agents MAY propose amendments via CHANGELOG entry marked `[PROPOSED]`
- Human MUST confirm before `[PROPOSED]` becomes effective
- Amendments to Core Axioms 1, 3–8 (Section 1) require human decision record in `docs/decisions/`. Guideline amendments do not require a decision record.

---

## 16. Adoption Phases

AFDS is an incremental standard. Projects adopt the phase that matches their tooling maturity. Projects MAY remain permanently at Phase 0 or Phase 1 — Phase 2 is an optimization layer, not a validity requirement. No phase is "incomplete"; each is a complete, valid operational mode.

### 16.1 Phase Overview

| Phase | Name | Tooling | Capabilities |
|-------|------|---------|--------------|
| **Phase 0** | Manual | Markdown linter + YAML validator | Frontmatter validation, banned words regex, section order check. Operates via pre-commit hooks and CI linters — no custom tooling required. |
| **Phase 1** | CI-Governed | Phase 0 + CI pipeline + graph resolver | Upstream link validation, registry auto-update, mutation gate enforcement. Custom CI scripts or open-source AFDS-compatible tooling. |
| **Phase 2** | Full Platform | Phase 1 + docs platform | Fitness computation, duplication scanning, runtime verification hooks, auto-discovery of references. Requires dedicated infrastructure. |

### 16.2 Per-Phase Feature Matrix

| Feature | Phase 0 | Phase 1 | Phase 2 |
|---------|---------|---------|---------|
| YAML frontmatter validation | ✅ | ✅ | ✅ |
| Banned words (tier-independent) | ✅ | ✅ | ✅ |
| Section order check | ✅ (L2+) | ✅ | ✅ |
| Banned words (tier-dependent) | ❌ | ❌ | ✅ |
| `upstream` link validation | ❌ | ✅ | ✅ |
| CHANGELOG + version sync (contract.* + decision.*) | ❌ | ✅ | ✅ |
| Registry <-> file system sync | ❌ | Warn | ✅ |
| Mutation gate enforcement | ❌ | ✅ (L2+) | ✅ |
| Semantic duplication scan | ❌ | ❌ | Advisory |
| Fitness computation | ❌ | ❌ | ✅ |
| Runtime verification (`verified_against`) | ❌ | ❌ | ✅ |
| Auto-discovery of references (9.3) | ❌ | ❌ | ✅ |

### 16.3 Graph Validation Grace Period

Newly created documents are exempt from `upstream` link validation for a configurable grace period. The grace period value is set in the project's local configuration (`docs/meta/config.yaml`).

```yaml
# docs/meta/config.yaml
graph_validation_grace_period_days: 30  # 0 = immediate, 90 = extended
```

If `config.yaml` does not exist, the default is 30 days. During the grace period, missing links produce CI warnings only, not blocks.

### 16.4 Upgrading Between Phases

1. Phase 0 → Phase 1: Implement graph resolver and CI validation scripts. All existing documents are subject to link validation after the configured grace period.
2. Phase 1 → Phase 2: Deploy docs platform infrastructure. Historical documents receive initial fitness scores on first scan.

### 16.5 Cost-Benefit Analysis

| Factor | Phase 0 | Phase 1 | Phase 2 |
|--------|---------|---------|---------|
| Team size | < 10 | 10–50 | 50+ |
| Repositories | 1–2 | 3–10 | 10+ |
| Document count | < 100 | 100–1,000 | 1,000+ |
| Changes per week | < 10 | 10–50 | 50+ |
| Compliance needs | Low | Medium | High |
| AI integration | None | Some | Heavy |
| Implementation time | Days | Weeks | Months |
| Maintenance cost | Low | Medium | High |
| Key benefit | Consistent structure, low barrier | Link validation, change tracking | Full observability, drift detection |

### 16.6 Success Metrics by Phase

**Phase 0:**
- 100% documents have valid YAML frontmatter
- Zero tier-independent banned words in L2+ normative sections
- 100% documents follow section order for their type
- CI blocks under 5% of PRs (low false positive rate)

**Phase 1:**
- 100% upstream links resolve to existing documents
- CHANGELOG updated on 95%+ of content changes
- Registry drift under 24 hours
- Mean time to detect broken link: under 1 day

**Phase 2:**
- Semantic duplication rate under 5% of document pairs
- Auto-discovery accuracy above 85%

**Tooling ecosystem (Phase 0–1):**
```bash
npm install -g markdownlint-cli    # Markdown linting
pip install yamllint                # YAML validation
pip install afds-lint               # AFDS-specific frontmatter + section validation
```

**Tooling ecosystem (Phase 2):**
- Sentence-transformers for embedding-based similarity detection
- PostgreSQL for document graph and metadata storage
- Grafana for health dashboards and alerting

---

## 17. Testing and Validation Strategy

Documentation requires testing to ensure accuracy and maintainability, analogous to code testing.

### 17.1 Test Types

| Test Type | Purpose | Frequency | Phase |
|-----------|---------|-----------|-------|
| **Schema validation** | Ensure frontmatter + body structure correct | Every commit | Phase 0 |
| **Link integrity** | Ensure all internal links resolve | Every commit | Phase 1 |
| **Executable docs** | Validate code examples run against the system | On PR / daily | Phase 2 |
| **Runtime verification** | Validate doc matches actual system behavior | On artifact change | Phase 2 |
| **Fitness regression** | Ensure changes do not degrade quality | Every PR | Phase 2 |

### 17.2 Executable Documentation

For `sys.*`, `workflow.*`, and `contract.*` documents, tests listed in `verified_against` validate that documented behavior matches actual behavior.

**Example — API contract test:**

```python
# tests/integration/test_auth_api.py — linked via verified_against in contract.api-auth-v2
def test_login_success():
    response = client.post("/auth/login", json={
        "username": "alice", "password": "secret"
    })
    assert response.status_code == 200
    assert "token" in response.json()
    assert "expires_at" in response.json()
```

CI gates at Phase 2:

```bash
pytest tests/ -k "test_auth"
# If tests fail → flag linked docs as "needs update"
# If doc references non-existent test → warn
```

### 17.3 Verification Adapters

Phase 2 tooling integrates with standard specification formats:

| Format | Adapter | Validates |
|--------|---------|-----------|
| OpenAPI / Swagger | Spectral + contract tests | `contract.*` — request/response schemas match implementation |
| AsyncAPI | Spectral (AsyncAPI ruleset) | `contract.*` — event schemas match broker messages |
| GraphQL | Schema diff + persisted queries | `contract.*` — schema matches deployed version |
| Protobuf | buf breaking change detector | `contract.*` — no backward-incompatible changes |
| Docker Compose | `docker compose config` | `sys.*` — documented ports, volumes, env vars match config |
| OPA / Conftest | Policy-as-code validation | `ref.*` — documented policies match enforced rules |

---

## 18. Security and Access Control

### 18.1 Access Tiers

| Tier | Audience | Examples | Storage |
|------|----------|----------|---------|
| **Public** | Anyone | API docs, guides, architecture overviews | Public repo, docs site |
| **Internal** | Company employees | System architecture, workflows, runbooks | Private repo, intranet |
| **Confidential** | Team only | Database schemas, security runbooks | Private repo, encrypted storage |
| **Restricted** | Named individuals | Incident response, vulnerability details, legal | Separate repo with restricted permissions, encrypted at rest |

### 18.2 Frontmatter for Access Control

```yaml
---
doc_id: sys.payment-gateway
access_tier: internal
allowed_roles: ["backend-team", "sre-team"]
audit_log: true
---

# For confidential docs
---
doc_id: ref.database-credentials
access_tier: confidential
allowed_roles: ["sre-team"]
audit_log: true
ai_scope: restricted
---
```

Note: `ai_scope: restricted` is a policy label, not a security boundary. For actual access control, store sensitive documents in a separate repository with restricted permissions, or use encryption (git-crypt / SOPS) with decryption in trusted CI pipelines only.

### 18.3 Agent Access Rules

| Access Tier | Agent Permissions | Requirement |
|-------------|-------------------|-------------|
| Public | Read, edit (unless `ai_scope: restricted`) | None |
| Internal | Read, edit (unless `ai_scope: restricted`) | Agent authenticated as internal user |
| Confidential | Read-only (`review_only`) | Agent has specific role membership |
| Restricted | MUST NOT access | Always denied without content leak |

---

## 19. Documentation Metrics and Observability

> [!NOTE]
> Phase 2 and Enterprise Only. This section describes observability tooling available at full platform deployment (see Section 16). Phase 0 and Phase 1 projects can skip these metrics — they are optimizations, not prerequisites. The core value of AFDS is available without any metrics infrastructure.

### 19.1 Key Metrics

| Metric | Definition | Target |
|--------|------------|--------|
| **Staleness rate** | Percentage of docs exceeding TTL | < 10% |
| **Link integrity rate** | Percentage of resolved internal links | > 99% |
| **Update frequency** | Mean days between document updates | < TTL |
| **Review latency** | Mean time from change to human review | < 48h at L2+ |

### 19.2 Health Dashboard Queries

Example queries for dashboarding tools (Grafana, Metabase):

```sql
-- Mean fitness by tier
SELECT rigor_tier, AVG(fitness_score) AS mean_fitness
FROM docs_metadata GROUP BY rigor_tier;

-- Stale documents exceeding TTL
SELECT doc_id, days_since(last_verified) AS days_stale, ttl_days
FROM docs_metadata
WHERE days_since(last_verified) > ttl_days;

-- Unresolved outgoing links
SELECT source_doc, target_doc
FROM doc_links WHERE resolved = false;
```

### 19.3 Alerting Rules

```yaml
- alert: HighStalenessRate
  expr: (count(docs_stale) / count(docs_total)) > 0.10
  severity: warning
  message: "More than 10% of documents are stale"

- alert: LowFitnessScore
  expr: avg(fitness_score{rigor_tier="L3"}) < 0.60
  severity: critical
  message: "L3 document fitness score below 0.60"

- alert: BrokenLinksDetected
  expr: count(broken_links) > 0
  severity: warning
  message: "Broken internal links detected"
```

### 19.4 User Analytics Events

Track document consumption to identify high-value and low-value content:

```yaml
events:
  doc_view:
    doc_id: sys.auth
    user: alice@example.com
    source: search | link | direct

  doc_search:
    query: "authentication flow"
    results_count: 5
    clicked: sys.auth

  doc_feedback:
    doc_id: guide.onboarding
    rating: 1-5
    comment: "Clear and helpful"
```

Derived metrics: most-viewed documents, search success rate, average rating by document.

---

## CHANGELOG

| Version | Date | Change | Author |
| ------- | ---- | ------ | ------ |
| 1.0.0 | 2026-05-08 | Initial release — AFDS: AI-First Documentation Standard. Document taxonomy (workflow, ref, sys, guide, decision, contract), rigor tiers (L0-L3), deterministic section schemas, SSOT + upstream references, controlled language, fitness telemetry, CI validation, security tiers, testing strategy, adoption phases, AI protocol | opencode |

---

## External Links

- [RFC 2119](https://www.ietf.org/rfc/rfc2119.txt)
- [CommonMark Specification](https://spec.commonmark.org/)
