---
description: Architecture decisions for the AFDS documentation standard — taxonomy, rigor model, metadata policy, language, CI, adoption
doc_id: decision.001-docs-standard-decisions
type: decision
status: accepted
rigor_tier: L3
ttl_days: 0
version: 1.0.0
stability: stable
ai_scope: review_only
source_of_truth: true
tags: ["adr", "afds", "docs-standards", "architecture"]
upstream:
  - ref.documentation-standard
supersedes: decision.001-agent-native-metadata-decoupling
superseded_by: null
last_verified: 2026-05-08
owners: ["docs-maintainers"]
verification_status:
  - human_reviewed
doc_kind: atomic
glossary_terms: []
ttl_policy: permanent
---

# ADR: AFDS Documentation Standard Architecture Decisions

> [!NOTE]
> Architecture Decision Record — immutable after acceptance. Supersedes `decision.001-agent-native-metadata-decoupling` whose content is absorbed into the Metadata category below.

## CONTEXT

The AI-First Documentation Standard (AFDS) evolved through multiple audit cycles to become a production-ready documentation governance framework. This record documents the key architectural decisions made during that evolution. Each decision category below captures the problem, the chosen approach, alternatives considered, and consequences.

## DECISION

### 1. Document Taxonomy — Six Base Types

**Problem:** AFDS needed document types that serve different epistemic roles (specification, knowledge, process, learning) while supporting deterministic AI agent retrieval.

**Decision:** Define six base types with distinct body schemas:
- `workflow.*` — executable procedures with TRIGGER and STEPS sections
- `ref.*` — authoritative specifications with RULES, INTERFACES, EDGE_CASES
- `sys.*` — system documentation with ARCHITECTURE, FAILURE_MODES, TROUBLESHOOTING
- `guide.*` — narrative learning materials with AUDIENCE, CONTEXT, WALKTHROUGH; permits conversational tone
- `decision.*` — immutable architecture decision records (ADR) with CONTEXT, CONSEQUENCES, STATUS
- `contract.*` — API contracts and schemas with SPECIFICATION, VERSIONING

**Rationale:** Each type maps to a Diátaxis quadrant (Tutorial, How-to, Reference, Explanation) plus extensions for ADR and API contracts. The separation prevents mixing specification prose with explanatory narrative — a source of AI hallucination in RAG retrieval.

**Alternatives considered:**
- Single unconstrained type with toggled sections: rejected because AI agents need deterministic structure expectations
- Four types matching Diátaxis only: rejected because ADRs and API contracts are essential for engineering teams
- Two types (narrative + formal): rejected — too coarse, causes overloading within each type

### 2. Composite Documents

**Problem:** Atomic documents provide SSOT for AI retrieval but create excessive file count and context-switching for human readers.

**Decision:** Allow composite documents (`doc_kind: composite`) as read-only aggregations of atomic sources. Atomic sources remain authoritative. Composite docs link to atomics — never the reverse. Max retrieval depth is 3 levels, max 12 files per query.

**Rationale:** Preserves SSOT integrity while providing human-readable narrative continuity. Composite documents are derived views, not additional sources of truth.

### 3. Rigor Model — L0 Through L3

**Problem:** All documents should not require the same level of maintenance rigor. A scratchpad note should not need the same enforcement as a security policy.

**Decision:** Define four rigor tiers:
- **L0 (scratch):** No enforcement. Free-form body. No mandatory fields except description.
- **L1 (human-first):** Lightweight. CHANGELOG optional. US/DS optional. No fitness. No mutation gate. Advisory CI.
- **L2 (structured):** Full schema enforcement. CHANGELOG required but git history suffices. Fitness computed as CI telemetry. Links validated.
- **L3 (compliance):** Hard gates on all mechanisms. Human review required for merges. Tier-dependent banned words enforced.

**Rationale:** Gradient of cognitive cost proportional to document criticality. Prevents overformalization of low-rigor content (Metric Gaming anti-pattern). Default tier is L2 for most documents.

### 4. Metadata Architecture — Separation of Concerns

**Problem:** Earlier AFDS versions required AI agents to maintain deterministic metadata fields (semantic_hash, fitness_score, version, downstream, verified_by) directly in frontmatter. LLMs are probabilistic text generators — they cannot reliably compute hashes or maintain bidirectional dependency graphs.

**Decision:** Move ALL metadata maintenance to CI tooling (homeostasis scan, pre-commit hooks). Agent responsibilities limited to content generation and `upstream` references. Specific changes:

| Field | Previous Responsibility | Current Status |
|-------|------------------------|-----------------|
| `fitness_score` | Agent-computed, stored in frontmatter | CI-only telemetry in health-report.md; NOT in frontmatter |
| `semantic_hash` | Agent-computed | Removed entirely |
| `version` | Agent-maintained SemVer | CI-maintained; contract.* only |
| `CHANGELOG` | All document types | contract.* + decision.* only |
| `downstream` | Manual bidirectional field | Removed from frontmatter; advisory only |
| `verified_by` | Agent stamp | Removed — git author suffices |
| `cascade propagation` | Agent traverses graph | Removed — replaced by `NEEDS_DOWNSTREAM_REVIEW` annotation |

**Rationale:** Separation of Concerns between AI agents (content + reasoning) and CI tooling (deterministic computation). Drastically reduces token consumption (~30-40%), eliminates mathematical errors from agents, and prevents version-related merge conflicts.

**Alternatives considered:**
- Function calling for deterministic operations: rejected — latency, complexity, fragility
- Remove all enforcement: rejected — destroys SSOT value proposition
- Separate database: rejected — violates self-contained document principle

### 5. Language Policy — Banned Words, Canonical Language, Narrative

**Problem:** Initial universal banned word list was too aggressive including architectural anchors (robust, graceful, flexible, handle) that are legitimate technical terms. Banning them forced verbose paraphrases that inflated token count without improving clarity. English-only axiom blocked international teams. Complete narrative ban killed knowledge transfer in learning materials.

**Decision:**
- Define a single universal banned word list of ambiguity killers only — words like ambiguous qualifiers that mask vagueness. Remove all tier-dependent words (should, would, handle, support, robust, graceful, flexible, and similar architectural terms) — these are architectural anchors that require context-specific definitions, not blanket bans.
- Change AXIOM 7 from "English Only" to **Canonical Language**: structural elements (frontmatter, headers) MUST be English; body SHOULD be English; translations permitted as `doc_kind: translation` with `source_of_truth: false`
- **Narrative permitted** in `guide.*` types (CONTEXT, WALKTHROUGH, RATIONALE sections) and as informational content in other types
- Banned-word enforcement delegated to linters (Phase 0), not AI generation constraints
- **Max 25 words per sentence** rule removed; replaced with "prefer bulleted lists for complex conditions" as advisory only

**Rationale:** Language rules should serve knowledge transfer (AXIOM 8), not fight natural expression. LLMs write natural prose better than artificially constrained text. Architectural anchors (robust, graceful, handle) are precise technical concepts — requiring paraphrases for them inflates documentation volume without improving machine parseability. International teams need bilingual pathways with clear canonical source of truth.

### 6. CI and Validation — Six Checks Only

**Problem:** Earlier versions had 10+ CI checks including fitness computation, bidirectional link validation, and semantic duplication scanning — causing PR noise and false positives.

**Decision:** Reduce to 6 checks; tier-dependent enforcement:

| Check | L1 | L2 | L3 |
|-------|----|----|-----|
| YAML valid + required fields | Warn | Block | Block |
| Mandatory sections present | Warn | Block | Block |
| Tier-independent banned words | Warn | Block | Block |
| doc_id unique | Block | Block | Block |
| Upstream links resolve | Skipped | Block | Block |
| CHANGELOG (contract.*+decision.*) | Skipped | Skipped | Block |

Fitness score is NOT computed by the validator — it runs in CI cron (homeostasis scan). Semantic duplication is advisory only.

**Rationale:** Simpler CI reduces false positives and PR friction. The validator catches structural errors; semantic quality heuristics run asynchronously.

### 7. Self-Validation

**Problem:** The standard defines rules that it does not follow itself — it was exempted from its own `ref.*` body schema.

**Decision:** Add the ref.* mandatory sections (PURPOSE, SCOPE, DEFINITIONS, RULES, INTERFACES, STATE, EDGE_CASES, EXAMPLES, NON_GOALS) as a compact mapping layer before the Table of Contents. Remove `docs_standards.md` from exempt_files in both the config and the validator. Fix banned words in the standard's own prose.

**Rationale:** The standard must follow its own rules to be credible. The mapping layer references existing sections rather than duplicating content.

### 8. Adoption Phases — Incremental Implementation

**Problem:** Full AFDS implementation requires significant tooling. Small teams cannot adopt.

**Decision:** Define three adoption phases with downgrade safety:
- **Phase 0 (Manual):** Markdown linter + YAML validator. Pre-commit hooks. Immediate for any repo.
- **Phase 1 (CI-Governed):** Graph resolver, CHANGELOG validation, registry auto-update, mutation gates.
- **Phase 2 (Full Platform):** Fitness computation, duplication scanning, runtime verification, auto-discovery.

Projects MAY remain at Phase 0 or Phase 1 permanently. Higher phases are optimization layers, not validity requirements.

**Rationale:** Eliminates all-or-nothing adoption barrier. Small teams get value from Phase 0 immediately.

### 9. Extended Sections

**Decision:** Add three content sections to the standard:

- **Testing Strategy (Section 17):** Executable documentation — tests listed in `verified_against` validate documented behavior. Verification adapters for OpenAPI, AsyncAPI, GraphQL, Protobuf, Docker Compose, OPA/Conftest.
- **Security and Access Control (Section 18):** Access tiers (Public/Internal/Confidential/Restricted), frontmatter fields for access control, agent access rules per tier.
- **Metrics and Observability (Section 19):** Key metrics dashboard queries, alerting rules, user analytics events.

## ALTERNATIVES_CONSIDERED

The alternative considered for each sub-decision is documented within the category above. Across all categories, the consistent rejection pattern was:

- **Over-engineering (too much automation):** Rejected when the mechanism's cost exceeds its benefit (cascade propagation, fitness-score gating, bidirectional links)
- **Under-engineering (no governance):** Rejected when the lack of structure reduces knowledge quality (no taxonomy, no SSOT, no validation)
- **Wrong abstraction layer:** Rejected when the mechanism fights the nature of LLMs (agents computing hashes) or fights human cognition (no narrative, English-only)

## CONSEQUENCES

**Positive:**
- Document taxonomy provides deterministic retrieval paths for AI agents
- Rigor tiers make adoption cost proportional to criticality
- Metadata separation eliminates agent math errors and merge conflicts
- Language rules serve knowledge transfer, not fight expression
- Six-check CI provides high-value structural validation with low PR friction
- Adoption phases enable incremental rollout from day 1

**Negative:**
- `upstream` references remain manual — auto-discovery requires Phase 2
- Without CI (Phase 0 only), metadata freshness depends on human discipline
- Composite documents require judgment calls about when to aggregate vs keep atomic

**Risks:**
- Projects may remain at Phase 0 indefinitely with stale metadata
- Guide.* narrative may be used as a loophole for poorly structured formal documents
- Translation pathway may be used to create multiple sources of truth if `source_of_truth` policy is not enforced

**Mitigations:**
- Phase 1 is strongly recommended for teams with >3 documents
- Guide.* has `rigor_tier L1` default and MUST list authoritative sources in `RELATED_DOCS`
- CI enforces `source_of_truth: false` for non-atomic documents; canonical English document is identified

## STATUS

- `proposed: 2026-05-08` — Consolidated from all audit cycles and implementation sessions
- `accepted: 2026-05-08` — Approved after full validation of docs_standards.md against AFDS rules

## CHANGELOG

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-05-08 | Initial ADR consolidating all architecture decisions for AFDS docs_standards.md | opencode |
