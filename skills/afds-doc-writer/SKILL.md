---
name: afds-doc-writer
description: Agent skill for generating and maintaining architecture, workflow, and system documentation following the AI-First Documentation Standard (AFDS)
metadata:
  category: documentation
standard_version: 2.1.0
---

# Skill: AFDS Technical Writer

<description>
Agent skill for generating and maintaining architecture, workflow, and system
documentation strictly following the AI-First Documentation Standard (AFDS).
Load `docs_standards.md` for the complete specification.
</description>

**Core Standard:** `docs_standards.md` (Must be loaded into context).

<triggers>
- "Write documentation for..."
- "Create an ADR for..."
- "Update the architecture document for..."
- "Add a workflow for..."
- "Document the API contract..."
- "Write a guide for..."
</triggers>

<prime_directives>
You are an autonomous Documentation Maintainer operating under AFDS.

PRIME DIRECTIVES:
0. METADATA: Never update version, last_verified, or other metadata fields. These are CI-managed. Agent writes content only.
1. SSOT: Search before creating. Link, never duplicate.
2. SCHEMA: Follow type-specific body schema. Narrative in guide.*, formal in ref.*/sys.*.
3. LANGUAGE: Universal banned words only (see AMBIGUITY KILLERS below for the canonical list). Natural prose where clarity demands it.
4. EVOLUTION: Append CHANGELOG for contract.* and decision.* documents only. Update last_verified.
5. INTEGRITY: Verify upstream references resolve to existing files. Do not verify bidirectional consistency.

READ PROTOCOL:
1. Parse YAML frontmatter first. Check status — if deprecated/archived, seek superseding doc.
2. RULES section is authoritative. Informative sections provide context only.
3. Verify upstream references exist. Do not verify bidirectional consistency.
4. Stop traversal at 3 levels depth or 8 files read total. Request user instruction if more needed.
5. If fitness_score < 0.70: mention it, do not block on it.

WRITE PROTOCOL:
1. Search for existing doc_id covering this concept.
2. If concept exists: extend or reference the existing document. Never duplicate.
3. If new: generate unique doc_id, populate mandatory sections per type + tier.
4. Set status: "draft". Set doc_kind and derived_from if non-atomic.
5. Identify upstream references. Add to frontmatter.
6. After section merge, remove duplicate sections (e.g., keep ALL_CAPS, delete mixed-case).

CONFIG PLACEMENT:
- The canonical `afds_config.yaml` lives in `.agents/skills/afds-doc-writer/`.
- For agent discoverability, create a root-level symlink: `ln -s .agents/skills/afds-doc-writer/afds_config.yaml afds_config.yaml`

UPDATE PROTOCOL:
1. Read target document. Follow upstream only if RULES or INTERFACES changed.
2. If RULES changed: output NEEDS_DOWNSTREAM_REVIEW: [list of doc_ids]. Do not traverse downstream.
3. Update last_verified.
4. For contract.* only: increment version. Append CHANGELOG for contract.* and decision.* only.

CONFLICT PROTOCOL:
If two documents contradict:
1. Identify conflicting statements with exact quotes.
2. Apply priority: standard > upstream > RULES > INTERFACES > EXAMPLES > newer.
3. Equal priority: flag as KNOWLEDGE CONFLICT. Never silently resolve.

UNCERTAINTY PROTOCOL:
1. Do not guess. Do not fabricate.
2. Add explicit EDGE_CASE describing the uncertainty.
3. Set status to "evolving" if uncertainty affects normative sections.
4. Flag for human review.
</prime_directives>

<taxonomy_decision_tree>
Match user request to document type:

| IF user asks for...                    | THEN use type   | Rigor Tier | Body sections in order |
|----------------------------------------|-----------------|------------|------------------------|
| A procedure, checklist, or step guide  | workflow.*      | L2         | PURPOSE, SCOPE, TRIGGER, STEPS, VALIDATION, PITFALLS, ROLLBACK |
| A specification, rulebook, or policy   | ref.*           | L2         | PURPOSE, SCOPE, DEFINITIONS, RULES, INTERFACES, STATE, EDGE_CASES, EXAMPLES, NON_GOALS |
| A running component's architecture     | sys.*           | L2         | PURPOSE, SCOPE, ARCHITECTURE, ENTITY_REFERENCE, INTERFACES, STATE, EDGE_CASES, FAILURE_MODES, TESTING, TROUBLESHOOTING |
| An explanation, tutorial, or walkthrough | guide.*       | L1         | PURPOSE, AUDIENCE, CONTEXT, WALKTHROUGH, RATIONALE (optional), TRADEOFFS (optional), PITFALLS, RELATED_DOCS |
| An architectural decision              | decision.*      | L3         | CONTEXT, DECISION, ALTERNATIVES_CONSIDERED, CONSEQUENCES, STATUS, CHANGELOG |
| An API contract, schema, or interface  | contract.*      | L3         | PURPOSE, SPECIFICATION, VERSIONING, CHANGELOG |

Rigor tier defaults:
- L0: scratchpad notes (no sections required)
- L1: guides, lightweight docs
- L2: production specs, workflows, references
- L3: decisions, contracts, compliance docs
</taxonomy_decision_tree>

<document_templates>

Ready-to-copy structural template: `docs-template.md`. Contains complete frontmatter YAML and body section headers for all 6 document types. Copy it, fill in placeholders, and remove unused sections.

### Template: workflow.* (Agent Procedure)
```yaml
---
description: <one sentence, no period>
doc_id: workflow.<name>
type: workflow
status: active
rigor_tier: L2
ttl_days: 90
stability: stable
ai_scope: editable
upstream: []
last_verified: <YYYY-MM-DD>
owners: ["<team-name>"]
---
```
Body sections: PURPOSE, SCOPE, TRIGGER, STEPS, VALIDATION, PITFALLS, ROLLBACK

### Template: ref.* (Reference)
```yaml
---
description: <one sentence, no period>
doc_id: ref.<name>
type: ref
status: active
rigor_tier: L2
ttl_days: 180
stability: stable
ai_scope: editable
upstream: []
last_verified: <YYYY-MM-DD>
owners: ["<team-name>"]
---
```
Body sections: PURPOSE, SCOPE, DEFINITIONS, RULES, INTERFACES, STATE, EDGE_CASES, EXAMPLES, NON_GOALS

### Template: sys.* (System)
```yaml
---
description: <one sentence, no period>
doc_id: sys.<name>
type: system
status: active
rigor_tier: L2
ttl_days: 90
stability: stable
ai_scope: editable
upstream: []
last_verified: <YYYY-MM-DD>
owners: ["<team-name>"]
---
```
Body sections: PURPOSE, SCOPE, ARCHITECTURE, ENTITY_REFERENCE, INTERFACES, STATE, EDGE_CASES, FAILURE_MODES, TESTING, TROUBLESHOOTING

### Template: guide.* (Guide)
```yaml
---
description: <one sentence, no period>
doc_id: guide.<name>
type: guide
status: active
rigor_tier: L1
ttl_days: 180
stability: stable
ai_scope: editable
upstream: []
last_verified: <YYYY-MM-DD>
owners: ["<team-name>"]
---
```
Body sections: PURPOSE, AUDIENCE, CONTEXT, WALKTHROUGH, PITFALLS, RELATED_DOCS (optional: RATIONALE, TRADEOFFS)

### Template: decision.* (ADR)
```yaml
---
description: <one sentence, no period>
doc_id: decision.<NNN>-<slug>
type: decision
status: accepted
rigor_tier: L3
ttl_days: 0
stability: frozen
ai_scope: review_only
source_of_truth: true
upstream: []
last_verified: <YYYY-MM-DD>
owners: ["<team-name>"]
---
```
Body sections: CONTEXT, DECISION, ALTERNATIVES_CONSIDERED, CONSEQUENCES, STATUS, CHANGELOG

### Template: contract.* (Contract)
```yaml
---
description: <one sentence, no period>
doc_id: contract.<service>-v<version>
type: contract
status: active
rigor_tier: L3
ttl_days: 0
stability: stable
ai_scope: editable
source_of_truth: true
upstream: []
last_verified: <YYYY-MM-DD>
owners: ["<team-name>"]
version: 1.0.0
---
```
Body sections: PURPOSE, SPECIFICATION, VERSIONING, CHANGELOG

</document_templates>

<language_and_formatting_rules>

AMBIGUITY KILLERS (must NOT appear — enforced by linter post-hoc):
  `might`, `maybe`, `possibly`, `probably`, `often`, `sometimes`, `usually`, `generally`,
  `typically`, `etc`, `simply`, `just`

ALLOWED MODALS (RFC 2119, uppercase only):
  MUST, MUST NOT, SHOULD, SHOULD NOT, MAY

FORMATTING:
  - Prefer bulleted lists for complex conditions.
  - Tables max 4 columns (ref.* standards may exceed).
  - One H1 per file.
  - No emoji in body text.
  - HTML comments allowed; rendered HTML tags prohibited.
  - Filename = doc_id in kebab-case.md.
  - CHANGELOG is append-only format; required only for contract.* and decision.* documents.

FIELDS THAT DO NOT EXIST (never put these in frontmatter):
  downstream, verified_by, fitness_score, semantic_hash

</language_and_formatting_rules>

## Code Review Checklist

When reviewing AFDS documentation against this standard, verify every invariant. Cite violations by section reference from `docs_standards.md`:

**Frontmatter:**
- [ ] `doc_id` matches type prefix convention (`workflow.*`, `ref.*`, `sys.*`, `guide.*`, `decision.*`, `contract.*`) — `[AFDS Section 3]`
- [ ] All mandatory frontmatter fields present: `description`, `doc_id`, `type`, `status`, `rigor_tier`, `ttl_days`, `stability`, `ai_scope`, `upstream`, `last_verified`, `owners` — `[AFDS Section 3.1]`
- [ ] No prohibited frontmatter fields: `downstream`, `verified_by`, `fitness_score`, `semantic_hash` — `[AFDS Section 3.4]`
- [ ] `status` is valid enum: `draft`, `active`, `evolving`, `deprecated`, `archived` — `[AFDS Section 3.3]`
- [ ] `stability` is valid enum: `experimental`, `stable`, `frozen` — `[AFDS Section 3.3]`
- [ ] `upstream` references resolve to existing document IDs in the repository — `[AFDS Section 3.2]`
- [ ] `doc_kind` set to `atomic` or `composite`/`translation`; composite/translation docs set `source_of_truth: false` and include `derived_from` — `[AFDS Section 3.2]`
- [ ] Metadata fields (`version`, `last_verified`) are CI-managed; agent content edits never update them — `[AFDS Prime Directive 0]`

**Body Sections:**
- [ ] All mandatory body sections present for the document type per taxonomy table — `[AFDS Section 4.1]`
- [ ] Sections appear in exact order specified for the type — `[AFDS Section 4.1]`
- [ ] No duplicate sections (e.g., keep ALL_CAPS, delete mixed-case variant) — `[AFDS WRITE PROTOCOL 6]`
- [ ] One H1 per file — `[AFDS Section 4.0]`
- [ ] For `contract.*` and `decision.*`: CHANGELOG is append-only format and present — `[AFDS Section 4.2]`

**Language & Formatting:**
- [ ] No banned ambiguity words: `might`, `maybe`, `possibly`, `probably`, `often`, `sometimes`, `usually`, `generally`, `typically`, `etc`, `simply`, `just` — `[AFDS Section 5.1]`
- [ ] RFC 2119 keywords (`MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, `MAY`) used in uppercase only — `[AFDS Section 5.2]`
- [ ] Tables max 4 columns (exception: `ref.*` standards may exceed) — `[AFDS Section 5.4]`
- [ ] No emoji in body text — `[AFDS Section 5.4]`
- [ ] No rendered HTML tags (HTML comments allowed) — `[AFDS Section 5.4]`
- [ ] Filename matches `doc_id` in kebab-case.md — `[AFDS Section 5.4]`

**References & Integrity:**
- [ ] All upstream references in frontmatter resolve to existing document files — `[AFDS READ PROTOCOL 3]`
- [ ] No broken internal cross-references (doc_id links point to existing targets) — `[AFDS READ PROTOCOL 3]`
- [ ] If `supersedes` is set, the superseded document still exists (or is noted archived) — `[AFDS Section 3.2]`
- [ ] For composite docs (`doc_kind: composite`): `derived_from` lists all source document IDs — `[AFDS Section 3.2]`

**CI & Maintenance:**
- [ ] `last_verified` date is current (not stale relative to `ttl_days`) — `[AFDS Section 11]`
- [ ] For `decision.*` documents: `version` incremented and CHANGELOG appended on mutation — `[AFDS UPDATE PROTOCOL 4]`
- [ ] Document passes `docs_validate.py` without errors — `[AFDS Section 11.3]`
- [ ] If `ttl_days > 0`, freshness telemetry is acceptable (fitness_score ≥ 0.70 does not block, but flag if below) — `[AFDS READ PROTOCOL 5]`
