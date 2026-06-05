# Changelog

## 2026-06-05

### v2.1.0 — Frontmatter standardization, template hardening, version policy

**afds-doc-writer:**
- `docs_validate.py`: Added `--json`, `--check-links`, `check_skill_frontmatter()`, `check_relative_links()`
- `afds_config.yaml`: Added `name`, `metadata` to allowed_fields, `action-version-matrix.md` to exempt_files
- All SKILL.md files now have YAML frontmatter (name, description, metadata)

**mcp-server-architect + mcp-server-consumer:**
- SKILL.md naming standardized (skill.md → SKILL.md)

**ci-cd-architect:**
- Version policy table: Python 3.14 (recommended/pre-release) through 3.11 (minimum), .NET 8.0.x LTS
- New rules: CI-CDW-79 (persist-credentials), CI-CDW-80 (workflow_run guard), CI-CDW-81 (cache:pip guard)
- All 8 workflow templates: SHA-pinned actions, persist-credentials: false, FORCE_JAVASCRIPT_ACTIONS_TO_NODE24
- Template headers: v1.0.0 → v2.0.0
- `action-version-matrix.md`: YAML frontmatter added, all 18 SHAs verified via git ls-remote

**Cross-skill:**
- `SKILL.md` naming standardized across all 4 skills
- New: decision.004-skill-dependencies.md, decision.005-ai-review-integration.md

**Tests:** 393 pass, no regressions

## 2026-06-01

### mcp-server-consumer: new skill — safe and efficient MCP tool operator

New counterpart to `mcp-server-architect`, teaching AI agents how to consume MCP servers.

**New skill:**
- `skill.md` — persona with 6 directives: decide before invoking, manifest/prefix fallback, token efficiency, fail safely, defense-in-depth, contract obedience. 4-phase workflow (Establish Capability Profile → Analyze Efficiently → Decide Safely → Execute → Verify). Decision policy quick reference (20-row table including unknown risk defer), error strategy matrix (14 codes), code review checklist.
- `mcp-consumer-standards.md` — core standard (ref, L2+), 793 lines. 9 rule sections: Tool Discovery, Token-Aware Invocation (batch/composite preference, minimal detail first, progressive disclosure, pagination awareness, negative capability, parameter carry-forward, cross-server workflows), Manifest Intelligence, Capability Reasoning, Response Contract, Error Recovery, Workflow Orchestration, Observability, Version Compatibility. 10 canonical templates (C1–C10).
- `tools/decision_engine.py` — reference implementation (722 lines): `evaluate_decision()`, `should_retry()`, `get_error_strategy()`, `get_retry_decision()`, `get_http_error_strategy()`, `infer_capability_profile()`, `prefer_batch_tool()`, `select_efficient_tool()`, `choose_initial_detail_params()`, `get_pagination_decision()`, `is_meaningful_empty_success()`, and more.

**Key design decisions:**
- Capability profile fallback: manifest → risk prefix annotation (`[READ]`, `[WRITE]`, etc.) → safe default (treat as `READ`). Supports L1 servers without full manifests.
- Decision policy as a testable table: every `(risk, requires_confirmation, user_intent)` combination mapped to a deterministic outcome. Unknown risk values fall back to `defer`, never `invoke`. DANGEROUS tools reject unless user explicitly requests them by name.
- Token efficiency as first-class directive: batch/composite before N individual calls, minimal detail first, progressive disclosure, pagination awareness, negative capability (empty `data` is meaningful, not error).
- Compound error checking: retry requires agreement from manifest `retryable`, error response `retryable`, and error strategy matrix. HTTP errors distinguish 4xx (escalate) from 5xx (retry once).

**Tests:** `test_consumer_standards.py` (32), `test_consumer_helpers.py` (58), `test_consumer_decisions.py` (26), `test_consumer_efficiency.py` (73). 131 total new tests — all pass with 0 warnings.

### mcp-server-architect: Consumer Ergonomics section added

Server standard updated to support efficient AI consumption.

**`mcp-server-standards.md`:**
- New section: *Consumer Ergonomics* (6 rules L1+/L2+) — list/summary before detail tools, minimal-detail parameters (`detail_level`, `compact`, `summary`), pagination metadata (`has_more`, `next_offset`, `next_cursor`), batch/composite READ tools, stable identifier carry-forward, empty-success contracts.
- Added `ref.mcp-consumer-standards` to `upstream` frontmatter.
- SCOPE extended to include consumer ergonomics.

**`skill.md`:**
- New directive 6: *Consumer Ergonomics*
- New workflow step 2b: *Design Consumer-Friendly Shape*
- Code review checklist: 6 new consumer ergonomics items
- Description updated

**Tests:** 0 regressions. Existing 232 tests still pass.

## 2026-05-23

### ci-cd-architect: standard v2.0.0 — security hardening + version bumps + bug fixes

Major update driven by deployment feedback from 5 projects (4 MCP servers + hand-codec .NET).

**BREAKING changes:**
- All action references now follow full commit SHA format (`owner/repo@<sha>  # vX`)
- **NOTE:** `semgrep/semgrep-action@v1` remains the canonical action — `semgrep/semgrep` does NOT exist as a GitHub Action (migration attempted via hybrid-therapist, reverted). Archived repo still resolves tags.

**Action version bumps:**
- `actions/upload-artifact` v4 → v7
- `actions/download-artifact` v4 → v8
- .NET SDK 8.0.x → 10.0.x

**New rules:**
- `CI-CDW-73,74,75` (Rule 23): Full commit SHA pinning for GitHub Actions — mutable tags replaced with immutable SHAs + version comments
- `CI-CDW-76,76a,76b` (Rule 6): Auto-tag → publish chain — `gh workflow run` bypasses GITHUB_TOKEN event suppression

**Bug fixes (templates):**
- `dotnet-ci.yml.j2`: Added `tags: ["v*"]` to push trigger — `pack-publish` job was unreachable without tag trigger (discovered in hand-codec)
- `dotnet-ci.yml.j2`: Added `Directory.Build.props` to NuGet cache key — version bumps didn't invalidate cache
- `docs-validation.yml.j2`: Removed `cache: pip` from `setup-python` — failed on pure .NET repos with no pip deps

**Template improvements:**
- `auto-tag.yml.j2`: Added `workflow_dispatch` trigger for manual tag creation from GitHub UI
- `auto-tag.yml.j2`: Added `gh workflow run` step to trigger publish after tag push
- `auto-tag.yml.j2`: Added `actions: write` permission for workflow dispatch

**Deployment fixes (all 4 MCP repos):**
- Semgrep PR scan: Added `SEMGREP_BASELINE_REF` for diff-aware scanning
- Semgrep PR scan: Added `publishToken` for Semgrep dashboard integration
- Semgrep scheduled: Added `hashFiles('semgrep.sarif')` guard + `id: upload-sarif`
- Dependabot: Added `docker` ecosystem to `package_ecosystems`
- mikrus-mcp: Fixed `[tool.mypy].python_version` 3.11 → 3.14

**New project onboarded:**
- hand-codec (.NET C#): Updated to .NET 10.0.x, Semgrep v2.0.0 compliance, docs-validation with AFDS integration

**Skill:**
- Added YAML frontmatter (`name`, `description`, `standard_version`) to SKILL.md

### hybrid-therapist deployment patches (merged into v2.0.0)

- **semgrep revert:** `semgrep/semgrep` does not exist — kept `semgrep/semgrep-action@v1` (archived but functional)
- **auto-tag.j2:** `gh workflow run` uses filename (`publish.yml`) not display name → CI-CDW-76c
- **auto-tag.j2:** Job condition supports `workflow_dispatch` standalone → CI-CDW-76d
- **auto-tag.j2:** SKIP_TAG env var pattern replaces `exit 0` — enables conditional downstream trigger skip
- **docs-validation:** `--strict` must be configurable, should default to off → CI-CDW-77
- **AFDS:** `CHANGELOG.md` MUST be exempt from validation → CI-CDW-78
- **Rule 23:** Dependabot auto-pinning guidance added (tags auto-converted to SHAs)

## 2026-05-21

### ci-cd-architect: standard v1.0.1

Updated `ci-cd-standard.md`, `SKILL.md`, and three Jinja2 templates based on real-world deployment feedback from ha-mcp-readonly PR #12.

- **Fixed:** Rule ID collision — Dependabot CI-CDW-52/53 overlapped with Semgrep CI-CDW-52/53. Renumbered Dependabot →54-57, Docs →58-60, Concurrency →61-62, .NET →63-67, PR Feedback →68-69. Total: 72 rules.
- **Added `[CI-CDW-52]` (L1+):** `SEMGREP_BASELINE_REF` for diff-aware Semgrep scanning — prevents pre-existing findings from blocking main-branch CI.
- **Added `[CI-CDW-53]` (L2+):** `hashFiles('semgrep.sarif')` guard on SARIF upload — prevents spurious `Path does not exist` failures.
- **Added `[CI-CDW-53a]` (SHOULD):** `.semgrep.yml` triage file for accepted unfixable findings.
- **Added `[CI-CDW-70,71,72]` (Rule 22):** pyproject.toml classifier consistency, mypy config completeness, cross-source Python version agreement.
- **Added edge cases:** `# nosemgrep` in Dockerfiles must be on a separate line (inline `#` is part of directive argument); direct push to main without PR requires manual tag creation.
- **Template fixes:** `semgrep.yml.j2` — added `SEMGREP_BASELINE_REF`, `hashFiles` guard, `SEMGREP_EXIT_CODE`→`SEMGREP_OUTCOME`. `semgrep-scheduled.yml.j2` — added `hashFiles` guard.

## 2026-05-13

### Validator: 3 new checks

Added three new validation checks to `docs_validate.py`:

- **frontmatter_minimal** (error): flags files without any YAML frontmatter — previously silent for files without `---`
- **duplicate_sections** (warning): detects sections with same normalized name but different casing (e.g. `## Architecture` + `## ARCHITECTURE`)
- **unknown_sections** (warning, tier-dependent): L1 — silent (body sections expected). L2 — single count line. L3 — lists all unknown section names

These checks were added to the check registry and documented in the `docs_standards.md` §11 CI/CD validation table.

### Validator: tier-aware `check_unknown_sections`

Made `check_unknown_sections` respect the document's `rigor_tier`:
- L1: returns silently — body sections are expected narrative content
- L2: single summary line (count of non-schema sections)
- L3: lists all unknown section names for audit

### Config: `exempt_files` expanded

Added `docs_standards.md` and `docs-template.md` to `exempt_files` — these documents have intentional narrative sections outside the type schema. Exemption only applies to section-related checks (mandatory_sections, section_order, unknown_sections). All other validation (frontmatter, banned words, doc_id, etc.) still runs.

### Validator: walking-speed fix for Magda tracker

Rule 6 in `check_transit_detection` logic pattern: changed `geo_stable < DEBOUNCE → "W trasie"` to `geo_stable < DEBOUNCE AND speed > TRANSIT_SPEED → "W trasie"`. Walking (speed ≤ 5 m/s) now falls through to show street name immediately instead of waiting 10 minutes for geo stability.

Tested 8 scenarios via `ha_eval_template` — all pass.

### Standard: `docs_standards.md` §11 table

Added 3 rows to the CI/CD validation table:

| Check | L1 Action | L2 Action | L3 Action |
|-------|-----------|-----------|-----------|
| Frontmatter present (even if minimal) | Warn | Block | Block |
| No duplicate section headings (case-normalized) | Warn | Warn | Block |
| Sections match declared type schema | Info | Info | Warn |

### Config: `afds_config.yaml` — `integration` type expanded

Extended the `integration` type from 6 sections (PURPOSE, SCOPE, SETUP, CONFIGURATION, DEBUG_TRIGGERS, TESTING) to 10 sections matching the glossary definition:

PURPOSE, SCOPE, ARCHITECTURE, CONFIGURATION, ENTITIES_CREATED, INTERFACES, TESTING, TROUBLESHOOTING, SECURITY_NOTES, CHANGELOG

This resolves a mismatch between the validator config and the `int.*` type defined in the project glossary.

### Skill: `SKILL.md` — UPDATE PROTOCOL and config placement

- Added to UPDATE PROTOCOL: "After section merge, remove duplicate sections (e.g., keep ALL_CAPS, delete mixed-case)"
- Added CONFIG PLACEMENT section: recommends root-level symlink for agent discoverability

### Standard: `mcp_standards.md` v1.1.0 — Write Guard, new manifest fields, risk table expansion

Applied five changes to the MCP Server Core Standard based on review of the openwrt-mcp project:

- **Risk table expanded** (Section: Risk Annotations): Added `When to use` and `Examples` columns. `[WRITE]` clarified as "typically reversible/idempotent", `[DESTRUCTIVE]` as "typically irreversible" with `reboot_device` example.
- **Side Effects table** (Section: Side Effects): Added `Guidance` column mapping side effect classes to typical risk levels.
- **Manifest Schema** (Section: Tool Manifest Schema): Added 3 new optional fields: `impact` (none/transient/persistent/service_outage), `privacy` (none/metadata/personal), `reversible` (bool).
- **Write Guard** (Section: Security and Operational Safety): New subsection with 3 rules — L2+ enable flag defaulting to `false`, L3+ validation before I/O, L2+ distinction between enable flag (server authorization) and `requires_confirmation` (agent consent hint).
- **`requires_confirmation` field updated**: Description now explicitly distinguishes agent-level hint from server-level enable flag.

### Skill: `skill.md` — workflow and constraints updated

- Standard Workflow: Step 1 expanded to mention new manifest fields; new Step 2 added for Write Guard requirements.
- Strict Constraints: 2 new entries for write guard and flag-vs-confirmation distinction.

### Validator: `docs_validate.py` — filename check, L0 skip, CHANGELOG support, /etc/ exemption

Applied four improvements to the AFDS documentation validator:

- **`check_filename_matches_doc_id`** (warning): Validates that filename matches doc_id slug without type prefix (e.g., `doc_id: ref.code-style` → expects `code-style.md`). Root-level files (README.md, CHANGELOG.md, AGENTS.md) are exempt. Caught `ref.openwrt-mcp.md` and `document-template.md` naming issues.
- **`check_mandatory_sections`**: Now skips L0 documents (rigor_tier: L0) — body is free-form per Section 4.3. Previously would flag all ref sections as missing for glossary and doc-registry.
- **`check_unknown_sections`**: Now accepts `## CHANGELOG` as a universal trailing section (Section 3.7) in any document type — previously flagged as an unknown section for ref.* and guide.* documents.
- **`_clean_prose`**: Added `/etc/` exemption — prevents the banned-word check from matching `\betc\b` in file paths like `/etc/init.d/network reload`. Also added `_clean_prose` handling for `/etc/`.
- **Root files config**: Added `CHANGELOG.md` as exempt root-level artifact (Section 2.2). Updated `check_root_file_integrity` to skip exempt files.
- **Check registry**: Registered `check_filename_matches_doc_id` as a warning-level check.

### Template: added Integration (`int.*`) example

- Added `### Integration (int.*)` frontmatter example section after Contract
- Added `integration` to the type enum in the Quick Reference table

### Standard: `mcp_standards.md` — timeout parameter type guidance

- **`mcp_standards.md`** (Section: Tool Parameter Design): Added rule: MCP tool timeouts MUST use `int = SSH_TIMEOUT`, never `int | None = None`. JSON Schema handles plain integers but may reject `int | None` depending on the framework version, causing MCP SSE transport errors.

### Skill: `skill.md` — timeout parameter constraint

- Added Strict Constraint: "NEVER use `int | None = None` for optional timeout parameters in MCP tool signatures. Use `int = SSH_TIMEOUT` instead."
