# Changelog

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
