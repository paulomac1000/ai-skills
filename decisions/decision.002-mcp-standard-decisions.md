---
description: Architecture decisions for the MCP server standard — merge architecture, document type, testing/security integration, annotation system
doc_id: decision.002-mcp-standard-decisions
type: decision
status: accepted
rigor_tier: L3
ttl_days: 0
version: 1.0.0
stability: stable
ai_scope: review_only
source_of_truth: true
tags: ["adr", "mcp", "standards", "architecture"]
upstream:
  - ref.documentation-standard
  - ref.mcp-server-standards
supersedes: null
superseded_by: null
last_verified: 2026-05-08
owners: ["backend-team"]
verification_status:
  - human_reviewed
doc_kind: atomic
glossary_terms: []
ttl_policy: permanent
---

# ADR: MCP Server Standard Architecture Decisions

> [!NOTE]
> Architecture Decision Record — immutable after acceptance. See `ref.mcp-server-standards` for the current MCP standard and `decision.001-docs-standard-decisions` for AFDS documentation standard decisions.

## CONTEXT

The MCP Server Core Standard (ref.mcp-server-standards) documents canonical templates and rules for building MCP (Model Context Protocol) servers. Through multiple iterations it evolved from a single monolithic document into a merged standard that also covers testing, security, and framework-specific implementation notes. This record documents the key architectural decisions made in shaping this standard.

## DECISION

### 1. Merge Architecture — Single File

**Problem:** The MCP standard was originally split into four files: core (`mcp_standards.md`), testing (`mcp_testing_standards.md`), security (`mcp_security_standards.md`), and FastMCP notes (`mcp_fastmcp_notes.md`). Each had overlapping upstream references, custom section structures, and legacy frontmatter incompatible with AFDS 1.0.0. Cross-file navigation increased cognitive load.

**Decision:** Merge all four files into a single `mcp_standards.md`. Testing, security, and FastMCP content become H3 subsections under `## RULES`, preserving all rules, tables, code examples, and annotation levels (`[L1+]`, `[L2+]`, `[L3+]`, `[L4]`, `[SHOULD]`).

**Rationale:** Atomicity (one file = one concept) must be balanced against locality (one file = coherent operational chunk). All MCP content describes one system — building MCP servers. Splitting into companion docs created retrieval overhead without proportional benefit. The merged document is ~1100 lines, well below the 1550-line docs_standards.md.

**Alternatives considered:**
- Keep separate files: rejected due to legacy frontmatter and non-standard sections; maintaining cross-file alignment costs more than one file
- Keep only core + testing, exclude security: rejected — security is integral to MCP server design
- Keep all separate, fix section structures per AFDS ref schema: rejected — three independent ref docs with overlapping content creates retrieval redundancy

### 2. Document Type and Scope

**Problem:** The MCP standard must be discoverable by AFDS-compatible tooling while accurately describing its content — it defines rules and contracts, not runtime system architecture.

**Decision:** Assign `type: ref` with sections matching the ref schema (PURPOSE, SCOPE, DEFINITIONS, RULES, INTERFACES, STATE, EDGE_CASES, EXAMPLES, NON_GOALS). SCOPE includes MCP server tool design, response contracts, maturity levels, testing, security, and framework implementation.

**Rationale:** The MCP standard is a reference document — it defines what tools MUST return, how versioning SHOULD work, what security rules MUST be followed. It is NOT a system description (which uses `sys.*`) — there is no runtime behavior to document.

### 3. Section Organization — H2 to H3 Demotion

**Problem:** The original MCP standard used custom H2 sections (DESIGN_PHILOSOPHY, MATURITY_LEVELS, TOOL_CAPABILITY_MODEL, RESPONSE_CONTRACT, PITFALLS, PATTERNS) that did not match the AFDS ref schema. These sections contain essential content but are invisible to the section-order validator.

**Decision:** Demote all custom sections from H2 to H3 under the correct AFDS parent:

| Original H2 | New H3 Under | Reason |
|------------|--------------|--------|
| DESIGN_PHILOSOPHY | RULES > Design Philosophy | Principles inform the rules |
| MATURITY_LEVELS | RULES > Maturity Levels | Maturity defines enforcement levels |
| TOOL_CAPABILITY_MODEL | RULES > Tool Capability Model | Capability is a design rule |
| TOOL_MANIFEST_SCHEMA | RULES > Tool Manifest Schema | Manifest format is a specification rule |
| TOOL_VERSIONING | RULES > Tool Versioning | Versioning policy is a rule |
| VERSION_COMPATIBILITY | RULES > Version Compatibility | Compatibility contract is a rule |
| RESPONSE_CONTRACT | RULES > Response Contract | Response format is a design rule |
| LOGGING_STANDARDS | RULES > Logging Standards | Logging is an implementation rule |
| SECRET_MANAGEMENT | RULES > Secret Management | Secret handling is a security rule |
| TOOL_PARAMETER_DESIGN | RULES > Tool Parameter Design | Parameter design is a rule |
| CODE_QUALITY_STACK | RULES > Code Quality Stack | Code quality is a project rule |
| PACKAGE_LAYOUT | RULES > Package Layout | Project structure is a rule |
| RESPONSE_HELPERS | RULES > Response Helpers | Helper design is a rule |
| PITFALLS | EDGE_CASES > Pitfalls | Pitfalls describe failure conditions |
| PATTERNS | EXAMPLES > Patterns | Patterns are implementation examples |
| Testing content | RULES > Testing Standards | New H3 subsection |
| Security content | RULES > Security and Operational Safety | New H3 subsection |
| FastMCP content | RULES > Python/FastMCP Implementation Notes | New H3 subsection |

**Rationale:** H3 sections are invisible to the AFDS section validator (which checks only H2). The validator sees the ref schema sequence (PURPOSE → NON_GOALS) and passes. All content preserved, no H2-level section structure violations.

### 4. Maturity Annotation System — L1-L4 vs rigor_tier

**Problem:** The MCP standard uses its own maturity level system (L1-L4) inherited from earlier versions, annotated inline as `[L1+]`, `[L2+]`, `[L3+]`, `[L4]`, `[SHOULD]`, `[MAY]`. AFDS uses `rigor_tier` (L0-L3) in frontmatter. Both systems exist in the same document.

**Decision:** Keep BOTH systems:
- `rigor_tier: L2` in frontmatter defines the document's AFDS maintenance tier
- Inline `[L1+]`, `[L2+]`, `[L3+]`, `[L4]` annotations define each rule's MCP maturity requirement

**Rationale:** The two systems serve different purposes. AFDS `rigor_tier` controls document-level maintenance burden (CHANGELOG, fitness, CI enforcement). MCP maturity levels control tool-level implementation rigor (unit tests only at L1, full compliance suite at L4). They are orthogonal and both useful.

### 5. Testing Integration

**Problem:** Testing patterns were originally in a separate `mcp_testing_standards.md`. The core standard recommends implementation patterns but the testing rules (coverage targets, CI pipeline, mock patterns) are essential to the complete MCP server design.

**Decision:** Merge testing content as `### Testing Standards` under RULES with four sub-sections: Registration Functions, Test Hierarchy, Skip Patterns, Coverage Requirements, CI Pipeline. The existing examples from testing are merged as Canonical Templates 8-17 under EXAMPLES. Testing rules use `**[RULE: TEST-*]**` semantic anchor format — each rule has a unique ID (e.g., `[RULE: TEST-SKIP-1]`) enabling CI logs to reference specific rules. Coverage policy mandates ≥80% line coverage; 100% reachable path coverage is explicitly prohibited as an anti-pattern.

**Rationale:** Testing is a first-class concern of MCP server development, not an optional companion topic. MCP tools are consumed by AI agents — incorrect responses are not just bugs but operating errors. Coverage targets and CI rules define the expected quality bar.

### 6. Security Integration

**Problem:** Security rules were in a separate `mcp_security_standards.md`. The core standard references transport security, blocked data, and secret management but existential threats (public SSE binding, unprotected cancellation, unvalidated filesystem access) need to be part of the same document so developers encounter them together.

**Decision:** Merge seven security subsections under `### Security and Operational Safety` under RULES: SSE Transport Security, Cancellation and Timeouts, Concurrency Model, Blocked Data Sources, Filesystem Access Control, Secret Management, Observability.

**Rationale:** Co-location of security rules with tool design rules ensures developers see both when implementing MCP servers. The security rules reference the same maturity levels (`[L1+]`-`[L4]`) as the rest of the standard.

### 7. FastMCP Integration

**Problem:** FastMCP-specific implementation notes were in a separate `mcp_fastmcp_notes.md`. Much of this content was already covered by the testing canonical templates (MCPWrapper, Mock MCP Fixture, REST Bridge), but some was unique — tool storage internals, call_tool API differences, upgrade compatibility table, framework-agnostic practices.

**Decision:** Merge only unique content as `### Python/FastMCP Implementation Notes` under RULES: Tool Storage Internals, call_tool API (two API signatures), Common Upgrade Issues table, Framework-Agnostic Practices. Content already covered by existing canonical templates (decorator syntax, ContentBlock extraction, lifespan timing, context mocking, REST Bridge integration) is NOT duplicated.

**Rationale:** Preserving only unique content prevents redundancy while ensuring all valuable knowledge is captured. The canonical templates (Canonical Template 1 MCPWrapper, Canonical Template 2 Mock MCP Fixture, Canonical Template 9 REST Bridge, Canonical Template 10 Test Budget) already abstract over the framework internals.

### 8. Frontmatter Migration — Legacy to 1.0.0

**Problem:** The original MCP files used frontmatter fields that became forbidden in AFDS 1.0.0: `downstream`, `verified_by`, `fitness_score`. They also lacked `rigor_tier` and `owners`.

**Decision:** Remove all legacy fields from the merged frontmatter. Add `rigor_tier: L2` and `owners: ["backend-team"]`.

**Rationale:** L2 is suitable for production standards — full schema enforcement but no L3 hard gates. The backend team owns MCP server development and the standard that governs it.

### 9. MCP Standard Optimization

**Problem:** The merged standard inherited legacy content that created unnecessary overhead for AI agents. The testing section used 100% reachable-path coverage (a known anti-pattern per Microsoft Research "Aiko" and Google testing studies), risk annotations duplicated capability data already in the tool manifest, patterns were named loosely as "Patterns" instead of mandatory templates, and deep H4 nesting made RAG retrieval fragile per "Lost in the Middle" research (Liu et al., 2023).

**Decision:** Apply four targeted optimizations:
- **Coverage policy:** 100% reachable paths → ≥80% line coverage with explicit success/error path validation. 100% reachable coverage is an anti-pattern and is explicitly prohibited.
- **Risk annotations SSOT:** Tool Manifest becomes authoritative source for capability metadata. Manual risk prefix in docstrings is required only at L1 (no manifest exists). At L2+, frameworks inject annotations from manifest data.
- **Semantic anchoring:** All testing rules use `**[RULE: TEST-*]**` format with unique IDs (TEST-HIERARCHY-1 through TEST-CI-4). This enables CI logs and AI agents to reference specific rules by identifier rather than fuzzy text matching.
- **Canonical Templates:** All 17 section headers renamed from `#### Pattern X` to `#### Canonical Template X`. Added AI agent note requiring exact copy-and-modify rather than loose "follow this style" interpretation.

**Rationale:** Studies demonstrate that 100% coverage targets produce assertion-free testing without quality gains — Microsoft Research found returns diminish after 80-85%. Duplicated state between manifest JSON and docstring text creates drift where agents update one but not the other — manifest-as-SSOT eliminates this. Deep Markdown nesting reduces LLM retrieval accuracy per "Lost in the Middle" — semantic anchors enable flat rule lookup regardless of document hierarchy depth.

## ALTERNATIVES_CONSIDERED

**Separate companion docs with AFDS compliance:** Rejected because each requires its own full AFDS ref schema (PURPOSE → NON_GOALS), tripling the maintenance surface. Cross-file links require updating on every section change.

**Single doc with no sub-sections (monolithic):** Rejected because a single flat H2 list with 21 sections exceeds the ref schema and makes navigation impossible. The H3 under RULES approach provides structure within the AFDS schema.

**Merge only testing, not security or FastMCP:** Rejected for consistency — if testing is integral, so are security and framework notes. Incomplete merging leaves orphans.

## CONSEQUENCES

**Positive:**
- Single file for all MCP server knowledge — no cross-file navigation
- Full AFDS ref schema compliance — passes validator and tests
- Testing, security, and FastMCP content preserved without duplication
- `[L1+]`-`[L4]` maturity annotations coexist with AFDS `rigor_tier` for complementary purposes
- File size (~1100 lines) is manageable and below docs_standards.md

**Negative:**
- Framework-agnostic readers must skim Python-specific sections
- H3 nesting reaches 4 levels in some sections (RULES > Testing > Skip Patterns); partially mitigated by `**[RULE: TEST-*]**` semantic anchors which enable flat retrieval of rules regardless of nesting depth
- FastMCP upgrade table will need periodic updates as the framework evolves

**Risks:**
- `[L4]` rules (blocked data, filesystem access) apply to very few projects but are in the main standard
- `stability: volatile` from the original FastMCP notes is lost — merged content is now `rigor_tier: L2` with no version-pinning note
- Maturity annotations `[L1+]`-`[L4]` may be confused with AFDS `rigor_tier` L0-L3

**Mitigations:**
- FastMCP upgrade table includes version ranges and mitigation steps
- All security rules clearly annotated with their maturity level
- `decision.001-docs-standard-decisions` documents the relationship between annotation systems

## STATUS

- `proposed: 2026-05-08` — Consolidated from MCP standard audit, restructuring, and merge sessions
- `accepted: 2026-05-08` — Approved after full validation of merged mcp_standards.md against AFDS rules

## CHANGELOG

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-05-08 | Initial ADR documenting all architecture decisions for the MCP server standard | opencode |
