---
description: Architecture decisions for the MCP server standard — merge architecture, document type, testing/security integration, annotation system
doc_id: decision.002-mcp-standard-decisions
type: decision
status: accepted
rigor_tier: L3
ttl_days: 0
version: 1.2.0
stability: stable
ai_scope: review_only
source_of_truth: true
tags: ["adr", "mcp", "standards", "architecture"]
upstream:
  - ref.documentation-standard
  - ref.mcp-server-standards
  - ref.ci-cd-standard
supersedes: null
superseded_by: null
last_verified: 2026-05-20
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

**Rationale:** Testing is a first-class concern of MCP server development, not an optional companion topic. MCP tools are consumed by AI agents — incorrect responses are not only bugs but operating errors. Coverage targets and CI rules define the expected quality bar.

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
- `updated: 2026-05-12` — v1.1.0: Write Guard, manifest fields, risk table expansion (see CHANGELOG)

### 10. Write Guard — Server-Level Enable Flag (v1.1.0)

**Problem:** The standard had no rule requiring write or destructive tools to be gated behind a server-level enable flag. Implementations could expose write tools that execute without any authorization check. The existing `requires_confirmation` manifest field was an agent-level hint (asking the AI to confirm), but there was no server-level mechanism to prevent execution entirely.

**Decision:** Add a new `Write Guard` subsection under `Security and Operational Safety` with three rules:
1. [L2+] Write/destructive tools MUST be gated behind an explicit server-level enable flag (e.g., `ENABLE_WRITE_OPERATIONS`), defaulting to `false`. When `false`, the tool MUST return a structured error before any I/O.
2. [L3+] The enable flag check MUST run before any I/O operation, raising `ValidationError` (or equivalent) when disabled.
3. [L2+] Distinguish between the enable flag (server authorization) and `requires_confirmation` (agent consent hint). Both are required for defense in depth.

**Rationale:** The enable flag is a server-level authorization check — the admin decides whether write tools can execute at all. `requires_confirmation` is an agent-level consent hint — the AI agent asks the user. They are complementary layers:
- `ENABLE_WRITE_OPERATIONS=false`: server returns error — agent never asks.
- `ENABLE_WRITE_OPERATIONS=true` + `requires_confirmation=false`: agent MAY call directly.
- `ENABLE_WRITE_OPERATIONS=true` + `requires_confirmation=true`: agent MUST request user confirmation.

This pattern was validated in the openwrt-mcp project where `check_write_enabled()` runs before any SSH execution, returning a structured `INVALID_PARAM` error when write operations are disabled.

### 11. Manifest Schema — 3 New Optional Fields (v1.1.0)

**Problem:** The 12-field manifest schema lacked metadata for operational impact (`impact`), data privacy sensitivity (`privacy`), and effect reversibility (`reversible`). AI agents evaluating whether to call a write tool had no machine-readable way to assess the consequence.

**Decision:** Add three new optional L3+ fields to the manifest schema:
- `impact: "none" | "transient" | "persistent" | "service_outage"` — describes operational impact on system availability
- `privacy: "none" | "metadata" | "personal"` — describes whether tool accesses personally identifiable or sensitive data
- `reversible: bool` — whether tool's effects can be reversed or undone at the application level

**Rationale:** KISS principle — no new risk prefixes, only extended capability descriptors. These fields are optional and backward-compatible (agents ignore unknown fields per L1+ rule).

### 12. Risk Table Expansion — When-to-Use and Examples (v1.1.0)

**Problem:** The risk prefix table had only a single-column meaning description. Authors choosing between `[WRITE]` and `[DESTRUCTIVE]` for borderline tools (e.g., `reboot_device`) had no guidance. AI agents parsing the table had no example tool names to anchor against.

**Decision:** Expand the risk prefix table with two new columns: `When to use` (guidance for authors) and `Examples` (concrete tool name patterns). `[DESTRUCTIVE]` reordered before `[DANGEROUS]` for severity progression: READ → WRITE → DESTRUCTIVE → DANGEROUS → SENSITIVE.

**Rationale:** Examples reduce classification errors. Explicit ordering prevents ambiguity about which risk is higher.

### 13. CI/CD Delegation to ci-cd-architect (v1.2.0)

**Problem:** The MCP standard defines CI requirements (`[TEST-CI-1]` through `[TEST-CI-4]`) — linting before tests, unit tests in CI, Docker build with tool count verification, Docker smoke test. However, it does not define *how* these requirements are implemented in GitHub Actions. Each MCP server project independently implemented its own CI/CD pipeline with divergent action versions, job structures, and trigger chains. Three of four projects were missing `auto-tag.yml`; one used `docker-publish.yml` instead of `publish.yml`; one had a hardcoded Docker version tag; action versions ranged from `checkout@v4` to `checkout@v6` across projects.

**Decision:** The MCP standard delegates CI/CD implementation to `ref.ci-cd-standard`. The MCP standard retains the WHAT — test hierarchy requirements, coverage targets, smoke test expectations. The CI/CD standard defines the HOW — workflow file structure, action versions, job ordering, Docker publish triggers, auto-tag mechanism, and now Semgrep security scanning, Dependabot dependency management, and PR feedback patterns.

The `upstream` field in `ci-cd-standard.md` references `ref.mcp-server-standards`. The CI/CD standard's Rule 15 (`[CI-CDW-34]`) explicitly maps each `[TEST-CI-N]` requirement to its CI/CD implementation. The relationship is documented in `SKILL.md` under "Integration with Other Standards".

**Rationale:** Separation of concerns — MCP defines server design (tool contracts, testing, security); CI/CD defines pipeline automation (workflows, Docker, releases). Mixing them would bloat both standards and create confusing maintenance boundaries. The CI/CD standard serves all Python + Docker projects, not only MCP servers; MCP-specific smoke test behavior is controlled by the `is_mcp` flag in the project configuration contract, not by the MCP standard itself.

**Alternatives considered:**
- Embed CI/CD rules in MCP standard: rejected — creates coupling; every CI/CD change (action version bump, new security scanner) would require updating the MCP standard
- No standard at all, per-project CI freedom: rejected — was the status quo; produced the divergence that motivated the CI/CD standard
- MCP standard references CI/CD standard as a SHOULD: rejected — projects adopted it as L1+ mandatory; a SHOULD would not have driven the unification

### 14. Frontmatter Rename — mcp_standards.md to mcp-server-standards.md (v1.2.0)

**Problem:** The filename `mcp_standards.md` was ambiguous — it could refer to the MCP protocol specification, an MCP client standard, or the MCP server standard. The `doc_id` field in frontmatter was `ref.mcp-server-standards`, creating a mismatch between the file path and the doc_id.

**Decision:** Rename the file from `mcp_standards.md` to `mcp-server-standards.md` to match the `doc_id` (`ref.mcp-server-standards`). Update the skill file (`skill.md`) to reference the new name. Update `ci-cd-standard.md` upstream reference to use `ref.mcp-server-standards`.

**Rationale:** Filename-doc_id alignment is a discoverability concern — AI agents and humans should find a document at the path implied by its doc_id. The `ref.mcp-server-standards` doc_id implies `mcp-server-standards.md`. The rename closes this gap.

## CHANGELOG

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-05-08 | Initial ADR documenting all architecture decisions for the MCP server standard | opencode |
| 1.1.0 | 2026-05-12 | Added Write Guard rules (decisions 10-12), manifest fields expansion, risk table column additions, requires_confirmation clarification | opencode |
| 1.2.0 | 2026-05-20 | Added §13 (CI/CD delegation to ci-cd-architect) and §14 (frontmatter rename mcp_standards.md → mcp-server-standards.md) | opencode |
