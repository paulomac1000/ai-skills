---
description: Cross-skill dependency map for ai-skills — template-to-standard relationships, SKILL.md upstream convention, CI/CD-to-AFDS config dependency, and MCP consumer-to-architect contract chain
doc_id: decision.004-skill-dependencies
type: decision
status: accepted
rigor_tier: L2
stability: stable
ai_scope: review_only
source_of_truth: true
upstream:
  - ref.ci-cd-standard
  - std.afds-docs-v3
last_verified: 2026-06-05
owners: ["ai-skills-maintainer"]
---

# Skill Dependencies and Cross-References Map

## CONTEXT

The ai-skills repository contains four skills (AFDS doc-writer, MCP architect, MCP consumer, CI/CD architect), each with a standard and (optionally) templates. Skills reference each other through frontmatter `upstream` fields, Jinja2 template dependencies, and standard-to-standard contract links. These relationships were documented ad hoc across multiple decision records but never consolidated into a single map. Without an explicit map, adding a new skill or updating a standard can silently break cross-references.

## DECISION

### 1. Template-to-Standard Ownership

Each Jinja2 template in `skills/ci-cd-architect/templates/` has a one-to-one relationship with `ref.ci-cd-standard`. The standard defines the structure, action versions, and quality gates; the template implements them as executable YAML. Every template MUST be maintainable by reading only the standard. No template contains configurable values that are not documented in the standard.

### 2. CI/CD Architect Depends on AFDS Doc-Writer

`docs-validation.yml.j2` consumes `docs_validate.py` and `afds_config.yaml` from `afds-doc-writer`. This is a runtime dependency: the CI pipeline calls the validator script with the config file. If the AFDS skill changes its validation script path or config schema, the CI/CD template must be updated in lockstep. The `upstream` field in `ref.ci-cd-standard` does not currently list `afds-doc-writer`; this is a gap tracked as decision.004 upstream gap.

### 3. SKILL.md `upstream` Field Convention

Every SKILL.md file SHOULD list its core standard(s) in the `upstream` frontmatter field using the `ref.<doc_id>` convention. Examples:
- `mcp-server-architect/SKILL.md` -> `ref.mcp-server-standards`
- `mcp-server-consumer/SKILL.md` -> `ref.mcp-consumer-standards` (and `ref.mcp-server-standards` for the consumed contract)
- `ci-cd-architect/SKILL.md` -> `ref.ci-cd-standard`
- `afds-doc-writer/SKILL.md` -> `ref.documentation-standard`

The `upstream` field on skill frontmatter is advisory (the skill's `<description>` or system prompt loads the standard directly). It exists for machine parsing and graph traversal, not for runtime behavior.

### 4. MCP Consumer Upstream References MCP Architect

`mcp-consumer-standards.md` lists `ref.mcp-server-standards` in its `upstream` field. This expresses a contract relationship: the consumer standard defines how to invoke tools whose shape is defined by the architect standard. Changes to the architect standard (e.g., new risk prefix levels or tool response schemas) must be checked against the consumer standard for compatibility.

### 5. Standard-to-AFDS Dependency Chain

Every standard (MCP architect, MCP consumer, CI/CD) references `ref.documentation-standard` (or `std.afds-docs-v3`) in its `upstream`. This ensures frontmatter schema, section structure, and controlled language rules are consistent across all standards. This is the root dependency: no standard can be valid without AFDS.

## ALTERNATIVES_CONSIDERED

- **Single dependency graph file instead of inline upstream fields:** Rejected — inline fields keep relationships co-located with the owning document, matching AFDS SSOT principles. A separate graph file would drift out of sync.
- **Bidirectional downstream fields (`downstream`):** Rejected — AFDS forbids `downstream` in `forbidden_fields`. Dependencies are expressed as `upstream` on the dependent document, not as reverse links on the source.
- **Automated cross-reference validation in CI:** Deferred — the current pattern of manual upstream fields with periodic test coverage (see `test_cross_refs.py`) is adequate for the current scale. A full dependency graph validator is deferred to a future phase.

## CONSEQUENCES

**Positive:** Cross-skill dependencies are explicit and machine-checkable. Adding a new skill requires only adding its `upstream` references. Template changes can be traced to their governing standards.

**Negative:** Upstream fields are currently maintained manually. A standard rename (e.g., `ref.documentation-standard` to `std.afds-docs-v3`) requires updating every dependent file. The CI/CD-to-AFDS dependency gap (missing `afds-doc-writer` in `ci-cd-standard.md` upstream) means a breaking change in the validator could silently break docs-validation workflows.

**Mitigations:** The `test_cross_refs.py` test suite catches doc_id mismatches. CI pipelines validate frontmatter schema at commit time. The CI/CD-to-AFDS upstream gap serves as a reminder to formalize the relationship.

## STATUS

`accepted: 2026-06-05`

## CHANGELOG

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-06-05 | Initial release — cross-skill dependency map covering template-to-standard ownership, CI/CD-to-AFDS config dependency, SKILL.md upstream convention, MCP consumer-to-architect contract chain, and standard-to-AFDS root chain | opencode |
