# AI Skills — Next Version Implementation

## TL;DR

> **Quick Summary**: Fix 5 failing SKILL.md frontmatter validations, harden 8 Jinja2 CI/CD templates (SHA pinning, security), update ci-cd-standard.md (Python version policy, new rules), and create 2 decision docs. Previous agent built tooling but didn't fix files.
>
> **Deliverables**:
> - All 5 skill files pass `docs_validate.py` validation
> - 8 templates: SHA-pinned, persist-credentials, FORCE_JAVASCRIPT_ACTIONS_TO_NODE24, --break-system-packages
> - ci-cd-standard.md: version policy table, new rules (persist-credentials, workflow_run guard, cache:pip)
> - 2 new decision docs (004, 005)
> - `action-version-matrix.md`: YAML frontmatter + verified SHAs
>
> **Estimated Effort**: Medium
> **Parallel Execution**: YES — 4 waves
> **Critical Path**: Wave 1 (frontmatter fixes) → Wave 3 (standard updates) → Wave 2 (template hardening, parallel with 3) → Wave 4 (verification)

---

## Context

### Original Request
User wants to complete the implementation of TODO.md improvements started by a previous agent (session in todo2.md). The previous agent built Phase 1 tooling (docs_validate.py changes, 10 new tests) but did NOT fix the 5 failing files and did NOT start Phases 2-5.

### Interview Summary
**Key Discussions**:
- Skills must be **project-agnostic** — no goose/hassio/Cortexa/personal-agents references in deliverables
- CI/CD skill must support multiple technologies/languages
- TODO.md sections 4 (Goose), 6-7 (mcp-server P1), 8 (Hassio) are **SKIPPED** — project-specific or deferred
- Naming: `skill.md` → `SKILL.md` rename for mcp-server-* files to match convention

**Research Findings**:
- Metis discovered 3 false status claims in TODO.md: `persist-credentials` not in any template (0 matches), `SEMGREP_OUTCOME` bug already fixed (line 75 uses 'success'), `CI-CDW-72/73/74` in standard are DIFFERENT rules than what TODO.md describes (ID collision)
- `action-version-matrix.md` has NO YAML frontmatter — contrary to subagent report from previous session
- Python 3.14 referenced 11 times in standard — doesn't exist on GHA
- All 8 template headers say "v1.0.0" — standard is v2.0.0

### Metis Review
**Identified Gaps** (addressed):
- Phase order wrong: frontmatter fixes (Phase 4) must precede template work (Phase 2) — reordered
- SEMGREP_OUTCOME bug may not exist → verify, don't blindly fix
- CI-CDW rule ID collision resolved: new rules get unique IDs (24, 25, 26)
- Scope boundaries added: skip sections 4, 6, 7, 8 of TODO.md

---

## Work Objectives

### Core Objective
Complete all project-agnostic TODO.md improvements: fix failing validations, harden CI/CD templates, update standards, and create missing decision docs.

### Concrete Deliverables
1. All 5 skill/reference files passing `docs_validate.py`
2. 8 Jinja2 templates with SHA-pinned actions, security headers, pip flag
3. `ci-cd-standard.md` with version policy table + 3 new rules
4. `decision.004-skill-dependencies.md` + `decision.005-ai-review-integration.md`
5. `action-version-matrix.md` with YAML frontmatter + verified SHAs
6. `SKILL.md` naming consistency (skill.md renamed where needed)

### Definition of Done
- [ ] `python3 -m pytest tests/ -v` → all pass, no regressions
- [ ] `python3 skills/afds-doc-writer/docs_validate.py --config skills/afds-doc-writer/afds_config.yaml skills/afds-doc-writer/SKILL.md skills/mcp-server-architect/SKILL.md skills/mcp-server-consumer/SKILL.md skills/ci-cd-architect/SKILL.md skills/ci-cd-architect/references/action-version-matrix.md` → 5/5 PASS
- [ ] `python3 skills/afds-doc-writer/docs_validate.py --config skills/afds-doc-writer/afds_config.yaml skills/afds-doc-writer/docs_standards.md skills/mcp-server-architect/mcp-server-standards.md skills/mcp-server-consumer/mcp-consumer-standards.md skills/ci-cd-architect/ci-cd-standard.md decisions/` → 7/7 PASS
- [ ] `grep -c '@v[0-9]' skills/ci-cd-architect/templates/*.yml.j2` → all 0
- [ ] `grep -n '3\.14' skills/ci-cd-architect/ci-cd-standard.md` → 0 results
- [ ] `grep -rni 'goose\|hassio\|Cortexa\|personal-agents' skills/` → 0 results (TODO.md exempt)

### Must Have
- Fix all 5 failing validations (frontmatter, banned words, description period)
- SHA pinning in all 8 templates with `git ls-remote` verified SHAs
- `persist-credentials: false` in ALL checkout steps (all 7 workflow templates)
- `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` in ALL workflow templates
- `--break-system-packages` in all pip install commands
- Python version policy table in standard (replace hardcoded 3.14)
- NEW rule IDs (24-26) for persist-credentials, workflow_run guard, cache:pip (avoid ID collision)
- decision.004 + decision.005 docs

### Must NOT Have (Guardrails)
- NO project-specific references (goose/hassio/Cortexa/personal-agents) in any deliverable
- NO changes to sections 4, 6, 7, 8 of TODO.md (deferred)
- NO SEMGREP_OUTCOME fix (already correct — 'success' on line 75)
- NO composing CI-CDW-72/73/74 redefinition — use NEW IDs (24, 25, 26) instead
- NO behavior changes to templates beyond the stated fixes
- NO new template features beyond what's in core P0 list

---

## Verification Strategy (MANDATORY)

### Test Decision
- **Infrastructure exists**: YES
- **Automated tests**: Tests-after
- **Framework**: pytest (393 existing tests)
- **QA**: Agent-executed via grep/pytest/bash verification commands

### QA Policy
Every task includes agent-executed verification via exact bash commands. Evidence = terminal output.
- **Validation**: Bash (docs_validate.py) — Verify frontmatter, banned words, section structure
- **Template audit**: Bash (grep) — Count @v tags, persist-credentials, FORCE_JAVASCRIPT_ACTIONS_TO_NODE24
- **Tests**: Bash (pytest) — 393+ tests must pass after every wave

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — frontmatter fixes):
├── Task 1: Fix afds-doc-writer/SKILL.md frontmatter + banned words [quick]
├── Task 2: Fix mcp-server-architect/skill.md → SKILL.md + frontmatter [quick]
├── Task 3: Fix mcp-server-consumer/skill.md → SKILL.md + frontmatter + banned word [quick]
├── Task 4: Fix ci-cd-architect/SKILL.md description period [quick]
└── Task 5: Add frontmatter to action-version-matrix.md [quick]

Wave 2 (After Wave 1 — template hardening, MAX PARALLEL):
├── Task 6: ci.yml.j2 — SHA pinning + persist-credentials + --break-system-packages
├── Task 7: publish.yml.j2 — SHA pinning + persist-credentials + workflow_run guard
├── Task 8: semgrep.yml.j2 — SHA pinning + persist-credentials + SARIF extraction step
├── Task 9: docs-validation.yml.j2 — SHA pinning + FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 + --break-system-packages
├── Task 10: auto-tag.yml.j2 — SHA pinning + persist-credentials + FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 + workflow_dispatch input
├── Task 11: dotnet-ci.yml.j2 — SHA pinning + persist-credentials (×3) + NuGet cache key
├── Task 12: semgrep-scheduled.yml.j2 — SHA pinning (no workflow changes needed)
└── Task 13: dependabot.yml.j2 — no changes needed (config file, not workflow)

Wave 3 (After Wave 1 — standard updates, parallel with Wave 2):
├── Task 14: ci-cd-standard.md — Python version policy table (replace all 11× 3.14 refs) [quick]
├── Task 15: ci-cd-standard.md — Add Rule 24 (persist-credentials), Rule 25 (workflow_run guard), Rule 26 (cache:pip guard) [quick]
├── Task 16: Template headers: v1.0.0 → v2.0.0 (all 8 templates) [quick]
└── Task 17: action-version-matrix.md — verified SHAs + template sync [quick]

Wave 4 (After Waves 2+3 — new docs):
├── Task 18: decision.004-skill-dependencies.md [writing]
├── Task 19: decision.005-ai-review-integration.md [writing]
└── Task 20: CHANGELOG.md — v2.1.0 entry [writing]

Critical Path: Wave 1 → Waves 2+3 (parallel) → Wave 4
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 5 (Wave 1) + 8 (Wave 2) + 4 (Wave 3) + 3 (Wave 4)
```

### Dependency Matrix

- **1-5**: - - 6-17 (block nothing — all parallel)
- **6-13**: 1-5, 14-15 - 18-20 (depend on standard rules)
- **14-17**: 1-5 - 6-13, 18-20
- **18-20**: 1-17 - F1-F4

### Agent Dispatch Summary

- **Wave 1**: 5 - T1-T5 → `quick`
- **Wave 2**: 8 - T6-T13 → `quick`
- **Wave 3**: 4 - T14-T17 → `quick`
- **Wave 4**: 3 - T18-T20 → `writing`

---

## TODOs

- [x] 1. Fix `skills/afds-doc-writer/SKILL.md` — add YAML frontmatter + remove banned words

  **What to do**:
  - Add YAML frontmatter block at top: `name: afds-doc-writer`, `description: <one sentence, no period>`
  - Remove banned words from prose: "etc" (line 198), "generally" (in <triggers>), "just" (line 248), "maybe" (none found), "might" (none found)
  - Keep existing `<description>`, `<triggers>`, `<prime_directives>` etc. XML blocks — they are NOT frontmatter
  - Frontmatter fields: `name`, `description`, `metadata.category: documentation`

  **Must NOT do**:
  - Do NOT change document content, structure, or directives
  - Do NOT add AFDS-specific fields (doc_id, type, status) — skills use their own schema
  - Do NOT modify XML-based `<description>` block — it's the skill trigger description, separate from YAML frontmatter

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 1 (with Tasks 2-5), blocks nothing

  **QA Scenarios**:
  ```
  Scenario: Happy path — SKILL.md passes validation
    Tool: Bash
    Steps:
      1. Run: python3 skills/afds-doc-writer/docs_validate.py --config skills/afds-doc-writer/afds_config.yaml skills/afds-doc-writer/SKILL.md
      2. Assert: output contains "Passed: 1, Failed: 0"
    Evidence: .omo/evidence/task-1-validation-pass.txt

  Scenario: No frontmatter error — check_frontmatter_minimal passes
    Tool: Bash (grep)
    Steps:
      1. Run: head -10 skills/afds-doc-writer/SKILL.md
      2. Assert: contains "---" opening + closing + name + description fields
    Evidence: .omo/evidence/task-1-frontmatter-head.txt
  ```

- [x] 2. Fix `skills/mcp-server-architect/skill.md` → rename + add YAML frontmatter

  **What to do**:
  - Rename file: `skill.md` → `SKILL.md` (two-step on case-insensitive FS: `git mv skill.md skill-tmp.md && git mv skill-tmp.md SKILL.md`)
  - Add YAML frontmatter: `name: mcp-server-architect`, `description: <one sentence>`, `metadata.category: mcp`
  - Update README.md reference from `skill.md` to `SKILL.md`
  - Update `tests/conftest.py` if it references this file path (check fixture paths)

  **Must NOT do**:
  - Do NOT change skill content or directives
  - Do NOT add AFDS-specific fields (doc_id, type, etc.)

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 1 (with Tasks 1,3,4,5), blocks Task 14-17

  **QA Scenarios**:
  ```
  Scenario: Happy path — renamed file passes validation
    Tool: Bash
    Steps:
      1. Run: ls skills/mcp-server-architect/SKILL.md
      2. Assert: file exists (exit 0)
      3. Run: python3 skills/afds-doc-writer/docs_validate.py --config skills/afds-doc-writer/afds_config.yaml skills/mcp-server-architect/SKILL.md
      4. Assert: "Passed: 1, Failed: 0"
    Evidence: .omo/evidence/task-2-validation-pass.txt

  Scenario: No stale references to old filename
    Tool: Bash (grep)
    Steps:
      1. Run: grep -rn 'skill\.md' tests/conftest.py README.md
      2. Assert: all references now say SKILL.md (no lowercase skill.md for mcp-server-architect)
    Evidence: .omo/evidence/task-2-refs.txt
  ```

- [x] 3. Fix `skills/mcp-server-consumer/skill.md` → rename + add YAML frontmatter + remove banned word

  **What to do**:
  - Rename file: `skill.md` → `SKILL.md` (same two-step process as Task 2)
  - Add YAML frontmatter: `name: mcp-server-consumer`, `description: <one sentence>`, `metadata.category: mcp`
  - Remove banned word "etc" from prose (appears in "STANDARD WORKFLOW" section)
  - Update README.md reference from `skill.md` to `SKILL.md`
  - Update `tests/conftest.py` if it references this file path

  **Must NOT do**:
  - Do NOT change skill content or directives

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 1 (with Tasks 1,2,4,5), blocks Task 14-17

  **QA Scenarios**:
  ```
  Scenario: Happy path — passes validation + no banned words
    Tool: Bash
    Steps:
      1. Run: python3 skills/afds-doc-writer/docs_validate.py --config skills/afds-doc-writer/afds_config.yaml skills/mcp-server-consumer/SKILL.md
      2. Assert: "Passed: 1, Failed: 0"
      3. Run: grep -n '\betc\b' skills/mcp-server-consumer/SKILL.md
      4. Assert: zero results (or only in code blocks)
    Evidence: .omo/evidence/task-3-validation-pass.txt
  ```

- [x] 4. Fix `skills/ci-cd-architect/SKILL.md` — remove trailing period from description

  **What to do**:
  - Line 3: `description:` ends with "...migration)." → remove the trailing period
  - Verify: description is a single sentence WITHOUT a period at end
  - No other changes needed — frontmatter already has `name` and `standard_version`

  **Must NOT do**:
  - Do NOT change description content, only remove trailing period
  - Do NOT modify other frontmatter fields

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 1 (with Tasks 1-3,5), blocks nothing

  **QA Scenarios**:
  ```
  Scenario: Description no longer ends with period
    Tool: Bash
    Steps:
      1. Run: python3 -c "
  import yaml
  with open('skills/ci-cd-architect/SKILL.md') as f:
      content = f.read()
  fm = yaml.safe_load(content.split('---')[1])
  desc = fm['description']
  assert not desc.rstrip().endswith('.'), f'Description still ends with period: {desc[-20:]}'
  print(f'OK: description does not end with period')
  "
      2. Assert: exit 0
    Evidence: .omo/evidence/task-4-desc-check.txt

  Scenario: Full validation passes
    Tool: Bash
    Steps:
      1. Run: python3 skills/afds-doc-writer/docs_validate.py --config skills/afds-doc-writer/afds_config.yaml skills/ci-cd-architect/SKILL.md
      2. Assert: "Passed: 1, Failed: 0"
    Evidence: .omo/evidence/task-4-validation-pass.txt
  ```

- [x] 5. Add YAML frontmatter to `skills/ci-cd-architect/references/action-version-matrix.md`

  **What to do**:
  - Add YAML frontmatter block at top (before `# Action Version Matrix`):
    ```yaml
    ---
    doc_id: ref.action-version-matrix
    type: ref
    status: active
    rigor_tier: L2
    stability: stable
    ai_scope: editable
    source_of_truth: true
    upstream: [ref.ci-cd-standard]
    last_verified: 2026-06-05
    owners: ["ci-cd-maintainer"]
    ttl_days: 30
    description: Pinned GitHub Action versions with commit SHAs and upgrade policy
    ---
    ```
  - Keep existing content unchanged (just prepend frontmatter)

  **Must NOT do**:
  - Do NOT change existing content or action versions in this task
  - Do NOT add project-specific fields

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 1 (with Tasks 1-4), blocks Task 17

  **QA Scenarios**:
  ```
  Scenario: File passes validation
    Tool: Bash
    Steps:
      1. Run: python3 skills/afds-doc-writer/docs_validate.py --config skills/afds-doc-writer/afds_config.yaml skills/ci-cd-architect/references/action-version-matrix.md
      2. Assert: "Passed: 1, Failed: 0"
    Evidence: .omo/evidence/task-5-validation-pass.txt

  Scenario: Frontmatter fields are correct
    Tool: Bash
    Steps:
      1. Run: python3 -c "
  import yaml
  with open('skills/ci-cd-architect/references/action-version-matrix.md') as f:
      content = f.read()
  fm = yaml.safe_load(content.split('---')[1])
  assert fm['doc_id'] == 'ref.action-version-matrix'
  assert fm['type'] == 'ref'
  assert fm['upstream'] == ['ref.ci-cd-standard']
  print('OK: frontmatter correct')
  "
      2. Assert: exit 0
    Evidence: .omo/evidence/task-5-fm-check.txt
  ```

- [x] 6. `templates/ci.yml.j2` — SHA pinning + persist-credentials + --break-system-packages

  **What to do**:
  - Replace ALL `@v*` tags with full commit SHAs (verify via `git ls-remote`):
    - `actions/checkout@v6` → `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v6` (×3 occurrences: lines 40, 86, 133)
    - `actions/setup-python@v6` → verify SHA via `git ls-remote https://github.com/actions/setup-python.git refs/tags/v6` (×3)
    - Any other @v tags found
  - Add `persist-credentials: false` to ALL checkout steps (×3)
  - Add `--break-system-packages` to all pip install commands
  - Verify `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` already present (it is — line 12)
  - Header: `# CI Pipeline Template v1.0.0` → `# CI Pipeline Template v2.0.0`

  **Must NOT do**:
  - Do NOT change Jinja2 template logic, conditional blocks, or job structure
  - Do NOT change Python version — template uses Jinja2 variable `{{ python_version }}`
  - Do NOT modify MCP/non-MCP conditional sections

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 2 (with Tasks 7-13), depends on Tasks 14,17 (standard + action matrix)

  **QA Scenarios**:
  ```
  Scenario: Zero @v* tags remain
    Tool: Bash (grep)
    Steps:
      1. Run: grep -n '@v[0-9]' skills/ci-cd-architect/templates/ci.yml.j2
      2. Assert: zero results
    Evidence: .omo/evidence/task-6-no-vtags.txt

  Scenario: All checkout steps have persist-credentials: false
    Tool: Bash
    Steps:
      1. Run: grep -c 'actions/checkout@' skills/ci-cd-architect/templates/ci.yml.j2 → N
      2. Run: grep -c 'persist-credentials: false' skills/ci-cd-architect/templates/ci.yml.j2 → M
      3. Assert: N == M
    Evidence: .omo/evidence/task-6-persist-creds.txt
  ```

- [x] 7. `templates/publish.yml.j2` — SHA pinning + persist-credentials + workflow_run guard

  **What to do**:
  - Replace ALL `@v*` tags with verified commit SHAs:
    - `actions/checkout@v4` → `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v6` (line 38) — UPDATE version from v4→v6 to match standard
    - `docker/setup-buildx-action@v3` → verify SHA via `git ls-remote` for v4 tag
    - `docker/login-action@v3` → verify SHA for v4 tag
    - `docker/build-push-action@v6` → verify SHA for v7 tag
    - `softprops/action-gh-release@v2` → verify SHA for v3 tag
    - **NOTE**: Standard (Rule 2) specifies v4/v4/v7/v3 versions, templates use older versions
  - Add `persist-credentials: false` to checkout step
  - Add `workflow_run` trigger guard (event+branch+repo check per CI-CDW-73 intent):
    ```yaml
    on:
      workflow_run:
        workflows: ["CI"]
        types: [completed]
        branches: [main, master]
    ```
  - Header: `v1.0.0` → `v2.0.0`

  **Must NOT do**:
  - Do NOT change publish logic or Docker tag derivation
  - Do NOT change multi-arch platform settings

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 2, depends on Tasks 14,17

  **QA Scenarios**:
  ```
  Scenario: Zero @v* tags + action versions match standard
    Tool: Bash (grep)
    Steps:
      1. Run: grep -n '@v[0-9]' skills/ci-cd-architect/templates/publish.yml.j2
      2. Assert: zero results
      3. Run: grep -c 'actions/checkout@11bd71901' skills/ci-cd-architect/templates/publish.yml.j2
      4. Assert: 1
    Evidence: .omo/evidence/task-7-no-vtags.txt
  ```

- [x] 8. `templates/semgrep.yml.j2` — SHA pinning + persist-credentials + verify SEMGREP_OUTCOME

  **What to do**:
  - Replace ALL `@v*` tags with verified SHAs:
    - `actions/checkout@v4` → SHA for v6
    - `returntocorp/semgrep-action@v1` → verify SHA (archived action, tag still resolves)
    - `github/codeql-action/upload-sarif@v3` → verify SHA
    - `actions/github-script@v9` → verify SHA
  - Add `persist-credentials: false` to checkout step
  - **VERIFY**: Line 75 already has `exitCode === 'success'` (bug already fixed — do NOT change)
  - Header: `v1.0.0` → `v2.0.0`

  **Must NOT do**:
  - Do NOT change SEMGREP_OUTCOME comparison (already correct)
  - Do NOT add SARIF extraction step in this task — that's a new feature

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 2, depends on Tasks 14,17

  **QA Scenarios**:
  ```
  Scenario: Zero @v* tags
    Tool: Bash (grep)
    Steps:
      1. Run: grep -n '@v[0-9]' skills/ci-cd-architect/templates/semgrep.yml.j2
      2. Assert: zero results
    Evidence: .omo/evidence/task-8-no-vtags.txt
  ```

- [x] 9. `templates/docs-validation.yml.j2` — SHA pinning + FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 + --break-system-packages

  **What to do**:
  - Replace ALL `@v*` tags with verified SHAs:
    - `actions/checkout@v4` → SHA for v6 (line 30)
    - `actions/setup-python@v5` → SHA for v6
    - `tj-actions/changed-files@v47` → SHA: `24d32ffd492484c1d75e0c0b894501ddb9d30d62` (TODO.md verified)
    - `actions/github-script@v9` → verify SHA
  - Add `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` at workflow level (missing — line ~30 area)
  - Add `--break-system-packages` to pip install commands
  - `persist-credentials: false` already present (line 32) — verify, don't change
  - Header: `v1.0.0` → `v2.0.0`

  **Must NOT do**:
  - Do NOT remove existing `persist-credentials: false`
  - Do NOT change tj-actions/changed-files logic

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 2, depends on Tasks 14,17

  **QA Scenarios**:
  ```
  Scenario: FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 present
    Tool: Bash (grep)
    Steps:
      1. Run: grep 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24' skills/ci-cd-architect/templates/docs-validation.yml.j2
      2. Assert: match found
    Evidence: .omo/evidence/task-9-node24.txt
  ```

- [x] 10. `templates/auto-tag.yml.j2` — SHA pinning + persist-credentials + FORCE_JAVASCRIPT_ACTIONS_TO_NODE24 + workflow_dispatch input

  **What to do**:
  - Replace ALL `@v*` tags with verified SHAs:
    - `actions/checkout@v4` → SHA for v6 (line 24)
    - `actions/github-script@v9` → verify SHA (line 55)
  - Add `persist-credentials: false` to checkout step (with: block)
  - Add `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` at workflow level
  - Add `workflow_dispatch` trigger with `version` input for non-pyproject repos:
    ```yaml
    on:
      workflow_dispatch:
        inputs:
          version:
            description: 'Semantic version (e.g. 1.2.3)'
            required: true
            type: string
      pull_request:
        types: [closed]
        branches: [main, master]
    ```
  - Header: `v1.0.0` → `v2.0.0`

  **Must NOT do**:
  - Do NOT remove existing pyproject.toml version extraction logic
  - Do NOT change the gh workflow run publish trigger logic

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 2, depends on Tasks 14,17

  **QA Scenarios**:
  ```
  Scenario: Both triggers present
    Tool: Bash (grep)
    Steps:
      1. Run: grep -c 'workflow_dispatch' skills/ci-cd-architect/templates/auto-tag.yml.j2
      2. Assert: >= 1
      3. Run: grep -c 'pull_request' skills/ci-cd-architect/templates/auto-tag.yml.j2
      4. Assert: >= 1
    Evidence: .omo/evidence/task-10-triggers.txt
  ```

- [x] 11. `templates/dotnet-ci.yml.j2` — SHA pinning + persist-credentials (×3)

  **What to do**:
  - Replace ALL `@v*` tags with verified SHAs:
    - `actions/checkout@v4` → SHA for v6 (lines 38, 78, 120 — ×3 occurrences)
    - `actions/setup-dotnet@v4` → verify SHA (lines 42, 82, 124 — ×3)
    - `actions/upload-artifact@v4` → verify SHA for v7 (line 106)
  - Add `persist-credentials: false` to ALL 3 checkout steps
  - `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` already present — verify
  - Header: `v1.0.0` → `v2.0.0`

  **Must NOT do**:
  - Do NOT change .NET version or restore/build/test/pack sequence
  - Do NOT modify NuGet cache logic

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 2, depends on Tasks 14,17

  **QA Scenarios**:
  ```
  Scenario: 3 checkout steps, 3 persist-credentials
    Tool: Bash (grep)
    Steps:
      1. Run: grep -c 'actions/checkout@' skills/ci-cd-architect/templates/dotnet-ci.yml.j2
      2. Assert: 3
      3. Run: grep -c 'persist-credentials: false' skills/ci-cd-architect/templates/dotnet-ci.yml.j2
      4. Assert: 3
    Evidence: .omo/evidence/task-11-persist-creds.txt
  ```

- [x] 12. `templates/semgrep-scheduled.yml.j2` — SHA pinning only

  **What to do**:
  - Replace `@v*` tags with verified SHAs (checkout, semgrep-action, codeql-action)
  - Header: `v1.0.0` → `v2.0.0`
  - No persist-credentials/JS actions/pip changes needed (this is a scheduled scan)

  **Must NOT do**:
  - Do NOT change cron schedule or scan configuration

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 2, depends on Tasks 14,17

  **QA Scenarios**:
  ```
  Scenario: Zero @v* tags
    Tool: Bash (grep)
    Steps:
      1. Run: grep -n '@v[0-9]' skills/ci-cd-architect/templates/semgrep-scheduled.yml.j2
      2. Assert: zero results
    Evidence: .omo/evidence/task-12-no-vtags.txt
  ```

- [x] 13. `templates/dependabot.yml.j2` — header only

  **What to do**:
  - Header: `v1.0.0` → `v2.0.0`
  - No SHA pinning needed (this is a config file, not a workflow)
  - Verify package-ecosystem sections are complete (github-actions, pip, nuget, docker)

  **Must NOT do**:
  - Do NOT add workflow-level settings (this is NOT a workflow file)

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 2, independent

  **QA Scenarios**:
  ```
  Scenario: Header updated
    Tool: Bash (grep)
    Steps:
      1. Run: head -5 skills/ci-cd-architect/templates/dependabot.yml.j2
      2. Assert: contains "v2.0.0" not "v1.0.0"
    Evidence: .omo/evidence/task-13-header.txt
  ```

- [x] 14. `ci-cd-standard.md` — Replace Python 3.14 with version policy table

  **What to do**:
  - Replace ALL 11 hardcoded references to `3.14`:
    - Line 89: Rule 4 text — replace "this is `3.14`" with "see Version Policy table below"
    - Lines 114, 145, 329, 416, 469, 795, 798, 826, 857, 879: replace `3.14` with `3.13`
  - Add Version Policy table in Rule 3 (Python Version) section AFTER line ~90:
    ```markdown
    ### Python Version Policy

    | Python Version | Status | GitHub Actions | Use Case |
    |---------------|--------|---------------|----------|
    | 3.13 | **Recommended** (latest stable) | ✅ Available | New projects, CI pipelines |
    | 3.12 | Supported | ✅ Available | Active maintenance |
    | 3.11 | **Minimum Supported** (LTS) | ✅ Available | Legacy projects, maximum compatibility |

    **[RULE: CI-CDW-4a] [L1+]** All NEW projects MUST use the recommended version. Existing projects SHOULD migrate within 90 days of a new recommended version release. The minimum supported version is the oldest version with GitHub Actions runner availability.
    ```
  - Update `.NET` version references similarly: `10.0.x` → `8.0.x` (current LTS), add note about 10.0 being preview

  **Must NOT do**:
  - Do NOT change rule numbers or structure
  - Do NOT remove any existing rules

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 3 (with Tasks 15-17), depends on Task 1-5

  **QA Scenarios**:
  ```
  Scenario: Zero 3.14 references remain
    Tool: Bash (grep)
    Steps:
      1. Run: grep -n '3\.14' skills/ci-cd-architect/ci-cd-standard.md
      2. Assert: zero results
    Evidence: .omo/evidence/task-14-no-314.txt

  Scenario: Version policy table exists
    Tool: Bash (grep)
    Steps:
      1. Run: grep -c 'Recommended.*Minimum Supported' skills/ci-cd-architect/ci-cd-standard.md
      2. Assert: >= 1
    Evidence: .omo/evidence/task-14-policy-table.txt
  ```

- [x] 15. `ci-cd-standard.md` — Add formal rules for persist-credentials, workflow_run guard, cache:pip

  **UPDATE: COLLISION FIXED** — CI-CDW-24/25/26 already exist in the standard (hardcoded version strings, permissions, registry env vars). Using CI-CDW-79/80/81 instead. Rule block headings stay as Rule 24/25/26.

  **What to do**:
  - Add 3 new rules after existing Rule 23 (around line 810):
    ```markdown
    ### Rule 24: Checkout Security (`CI-CDW-79`)

    **[RULE: CI-CDW-79] [L1+]** Every `actions/checkout` step in every workflow file MUST include `persist-credentials: false`. This prevents the GITHUB_TOKEN from being persisted to subsequent steps, reducing the risk of credential leaks in third-party actions and build scripts.

    ### Rule 25: Workflow Run Trigger Guard (`CI-CDW-80`)

    **[RULE: CI-CDW-80] [L2+]** Workflows using the `workflow_run` trigger MUST guard with explicit `branches:` filter (`[main, master]`) to prevent execution on pull request CI runs. Additionally, the event type MUST be verified (`types: [completed]`) and the triggering workflow MUST have succeeded (`github.event.workflow_run.conclusion == 'success'`).

    ### Rule 26: Cache Dependency Validation (`CI-CDW-81`)

    **[RULE: CI-CDW-81] [L2+]** When using `cache: pip` in `actions/setup-python`, a dependency file (`requirements.txt` or `pyproject.toml`) MUST exist in the repository. For repositories without pip dependencies (e.g., pure documentation repos, .NET-only repos), omit the `cache: pip` option to prevent CI failures from missing cache sources.
    ```
  - Update the Code Review Checklist to reference the new rule IDs (CI-CDW-79/80/81)
  - CHANGELOG: add entry for new rules

  **Must NOT do**:
  - Do NOT renumber existing CI-CDW-24/25/26 — they stay as-is
  - Do NOT remove any existing rules

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 3, depends on Tasks 1-5

  **QA Scenarios**:
  ```
  Scenario: New rule IDs present
    Tool: Bash (grep)
    Steps:
      1. Run: grep -c 'CI-CDW-79' skills/ci-cd-architect/ci-cd-standard.md
      2. Assert: >= 1
      3. Run: grep -c 'CI-CDW-80' skills/ci-cd-architect/ci-cd-standard.md
      4. Assert: >= 1
      5. Run: grep -c 'CI-CDW-81' skills/ci-cd-architect/ci-cd-standard.md
      6. Assert: >= 1
    Evidence: .omo/evidence/task-15-new-rules.txt
  ```

- [x] 16. Template headers: `v1.0.0` → `v2.0.0` across all templates

  **What to do**:
  - Update the version header comment in ALL 9 files:
    - `templates/ci.yml.j2` line 3
    - `templates/publish.yml.j2` header
    - `templates/semgrep.yml.j2` header
    - `templates/semgrep-scheduled.yml.j2` header
    - `templates/docs-validation.yml.j2` header
    - `templates/auto-tag.yml.j2` header
    - `templates/dotnet-ci.yml.j2` header
    - `templates/dependabot.yml.j2` header
    - `templates/ci-cd-config.example.yaml` header
  - Pattern: `# Template Name v1.0.0` → `# Template Name v2.0.0`

  **Must NOT do**:
  - Do NOT change `standard_version` field in any YAML frontmatter — that's separate from template header version
  - Do NOT change template content

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 3, depends on Tasks 1-5

  **QA Scenarios**:
  ```
  Scenario: All templates reference v2.0.0
    Tool: Bash (grep)
    Steps:
      1. Run: grep -c 'v2.0.0' skills/ci-cd-architect/templates/*.{j2,yaml} 2>/dev/null
      2. Assert: all 9 files have at least 1 v2.0.0 reference
      3. Run: grep -c 'v1.0.0' skills/ci-cd-architect/templates/*.{j2,yaml} 2>/dev/null
      4. Assert: zero v1.0.0 references remain
    Evidence: .omo/evidence/task-16-headers.txt
  ```

- [x] 17. `action-version-matrix.md` — verify and update SHAs + sync with templates

  **What to do**:
  - Verify ALL existing SHAs via `git ls-remote`:
    - Each action in the table: run `git ls-remote https://github.com/{owner}/{repo}.git refs/tags/{tag}` and compare SHA
    - Update any stale SHAs
  - Add `docker/setup-buildx-action` v4 SHA (currently listed as v3):
    - Verify: `git ls-remote https://github.com/docker/setup-buildx-action.git refs/tags/v4`
    - Expected: `d7f5e7f509e45cec5c76c4d5afdd7de93d0b3df5` (per TODO.md)
  - Add `tj-actions/changed-files` v47 SHA (currently listed as v46):
    - Verify: `git ls-remote https://github.com/tj-actions/changed-files.git refs/tags/v47`
    - Expected: `24d32ffd492484c1d75e0c0b894501ddb9d30d62` (per TODO.md)
  - Update `actions/github-script`: v7→v9 (templates use v9)
  - Add "Known Problematic Actions" section flagging `docker/setup-buildx-action`

  **Must NOT do**:
  - Do NOT change the table structure
  - Do NOT add unverified SHAs

  **Recommended Agent Profile**: `quick`

  **Parallelization**: Wave 3, depends on Task 5

  **QA Scenarios**:
  ```
  Scenario: All SHAs verified
    Tool: Bash (loop)
    Steps:
      1. For each action in matrix, run: git ls-remote https://github.com/{owner}/{repo}.git refs/tags/{tag} | awk '{print $1}'
      2. Compare with SHA in matrix
      3. Assert: all match or are updated
    Evidence: .omo/evidence/task-17-sha-verify.txt

  Scenario: buildx v4 SHA correct
    Tool: Bash
    Steps:
      1. Run: git ls-remote https://github.com/docker/setup-buildx-action.git refs/tags/v4 | awk '{print $1}'
      2. Run: grep 'setup-buildx-action' skills/ci-cd-architect/references/action-version-matrix.md
      3. Assert: SHA in matrix matches git ls-remote output
    Evidence: .omo/evidence/task-17-buildx-sha.txt
  ```

- [x] 18. Create `decisions/decision.004-skill-dependencies.md`

  **What to do**:
  - Create new ADR document following AFDS decision format (pattern from decision.003)
  - Frontmatter:
    ```yaml
    ---
    doc_id: decision.004
    type: decision
    status: active
    rigor_tier: L2
    stability: stable
    ai_scope: review-only
    source_of_truth: true
    upstream: [ref.ci-cd-standard, std.afds-docs-v3]
    last_verified: 2026-06-05
    owners: ["ai-skills-maintainer"]
    description: Cross-skill dependency map and template-to-standard relationships
    ---
    ```
  - Sections: CONTEXT, DECISION, ALTERNATIVES_CONSIDERED, CONSEQUENCES, STATUS, CHANGELOG
  - Content:
    - Map which CI templates depend on which AFDS config/scripts
    - Document `upstream` field convention for SKILL.md files
    - Document `ci-cd-architect` dependency on `afds-doc-writer` (docs-validation.yml.j2 uses afds_config.yaml)
    - Document MCP consumer upstream reference to MCP architect standard

  **Must NOT do**:
  - NO project-specific references
  - Keep concise — 50-80 lines

  **Recommended Agent Profile**: `writing`

  **Parallelization**: Wave 4 (with Tasks 19-20), depends on Tasks 1-17

  **QA Scenarios**:
  ```
  Scenario: Decision doc passes validation
    Tool: Bash
    Steps:
      1. Run: python3 skills/afds-doc-writer/docs_validate.py --config skills/afds-doc-writer/afds_config.yaml decisions/decision.004-skill-dependencies.md
      2. Assert: "Passed: 1, Failed: 0"
    Evidence: .omo/evidence/task-18-validation-pass.txt

  Scenario: Decision is sequential (004)
    Tool: Bash
    Steps:
      1. Run: ls decisions/decision.004-skill-dependencies.md
      2. Assert: file exists
    Evidence: .omo/evidence/task-18-file-exists.txt
  ```

- [x] 19. Create `decisions/decision.005-ai-review-integration.md`

  **What to do**:
  - Create new ADR document following AFDS decision format
  - Frontmatter:
    ```yaml
    ---
    doc_id: decision.005
    type: decision
    status: active
    rigor_tier: L2
    stability: stable
    ai_scope: review-only
    source_of_truth: true
    upstream: [ref.ci-cd-standard]
    last_verified: 2026-06-05
    owners: ["ai-skills-maintainer"]
    description: Process for handling AI code review feedback on CI/CD workflows including SHA verification protocol
    ---
    ```
  - Sections: CONTEXT, DECISION, ALTERNATIVES_CONSIDERED, CONSEQUENCES, STATUS, CHANGELOG
  - Content:
    - Document that AI code review tools can hallucinate SHAs
    - SHA verification protocol: `git ls-remote` + `curl api.github.com` fallback
    - Dependabot PR review: verify ALL actions use pinned SHAs
    - Metis pre-planning review as gate for catching AI inconsistencies
    - Process note: AI-suggested SHAs MUST be verified before merging

  **Must NOT do**:
  - NO project-specific references
  - Do NOT name specific AI tools (CodeRabbit, Copilot) — keep generic
  - Keep concise — 50-80 lines

  **Recommended Agent Profile**: `writing`

  **Parallelization**: Wave 4 (with Tasks 18,20), depends on Tasks 1-17

  **QA Scenarios**:
  ```
  Scenario: Decision doc passes validation
    Tool: Bash
    Steps:
      1. Run: python3 skills/afds-doc-writer/docs_validate.py --config skills/afds-doc-writer/afds_config.yaml decisions/decision.005-ai-review-integration.md
      2. Assert: "Passed: 1, Failed: 0"
    Evidence: .omo/evidence/task-19-validation-pass.txt
  ```

- [x] 20. Update `CHANGELOG.md` — v2.1.0 entry

  **What to do**:
  - Add new version entry at top (after `# Changelog`, before `## 2026-06-01`):
    ```markdown
    ## 2026-06-05

    ### v2.1.0 — Frontmatter standardization, template hardening, version policy

    **afds-doc-writer:**
    - `docs_validate.py`: Added `--json`, `--check-links`, `check_skill_frontmatter()`, `check_relative_links()`
    - `afds_config.yaml`: Added `name`, `metadata` to allowed_fields
    - All SKILL.md files now have YAML frontmatter (name, description)

    **ci-cd-architect:**
    - Standard v2.0.1: Version policy table (Python 3.13 recommended, 3.11 minimum), .NET 8.0.x LTS
    - New rules: CI-CDW-24 (persist-credentials), CI-CDW-25 (workflow_run guard), CI-CDW-26 (cache:pip guard)
    - All 8 templates: SHA-pinned actions (48 occurrences replaced), persist-credentials: false, FORCE_JAVASCRIPT_ACTIONS_TO_NODE24
    - Template headers: v1.0.0 → v2.0.0
    - `action-version-matrix.md`: YAML frontmatter added, SHAs verified, buildx v4 SHA corrected

    **Cross-skill:**
    - `SKILL.md` naming standardized (skill.md → SKILL.md for mcp-server-*)
    - New: decision.004-skill-dependencies.md, decision.005-ai-review-integration.md

    **Tests:** 393 pass, no regressions
    ```
  - Keep existing entries below it

  **Must NOT do**:
  - Do NOT modify existing changelog entries
  - Do NOT add project-specific references

  **Recommended Agent Profile**: `writing`

  **Parallelization**: Wave 4 (with Tasks 18-19), depends on Tasks 1-19

  **QA Scenarios**:
  ```
  Scenario: Changelog entry present and well-formatted
    Tool: Bash
    Steps:
      1. Run: head -20 CHANGELOG.md
      2. Assert: contains "## 2026-06-05" and "v2.1.0"
    Evidence: .omo/evidence/task-20-changelog.txt
  ```

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists. For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .omo/evidence/.

  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [20/20] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run full verification:
  ```bash
  python3 -m pytest tests/ -v --tb=short
  python3 skills/afds-doc-writer/docs_validate.py --config skills/afds-doc-writer/afds_config.yaml skills/afds-doc-writer/SKILL.md skills/mcp-server-architect/SKILL.md skills/mcp-server-consumer/SKILL.md skills/ci-cd-architect/SKILL.md skills/ci-cd-architect/references/action-version-matrix.md skills/afds-doc-writer/docs_standards.md skills/mcp-server-architect/mcp-server-standards.md skills/mcp-server-consumer/mcp-consumer-standards.md skills/ci-cd-architect/ci-cd-standard.md decisions/
  grep -c '@v[0-9]' skills/ci-cd-architect/templates/*.yml.j2
  grep -n '3\.14' skills/ci-cd-architect/ci-cd-standard.md
  grep -rni 'goose\|hassio\|Cortexa\|personal-agents' skills/
  ```

  Output: `Tests [N pass/N fail] | Validation [N/N pass] | @v tags [0] | 3.14 refs [0] | Project refs [0] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Execute verification commands from each task. Test cross-task integration (templates + standard consistency). Test edge cases: `git mv skill.md skill-tmp.md && git mv skill-tmp.md SKILL.md` on case-insensitive FS, Jinja2 conditional branches in templates, SHA pinning consistency across all templates.

  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git diff). Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance. Detect cross-task contamination: Task N touching Task M's files. Flag unaccounted changes.

  Output: `Tasks [20/20 compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **1**: `fix(skills): add YAML frontmatter to all SKILL.md files, standardize naming` — 5 skill files + README.md references
- **2**: `fix(templates): SHA pinning, persist-credentials, --break-system-packages, version headers v2.0.0` — 8 template files
- **3**: `docs(ci-cd): version policy table, new rules 24-26, action matrix SHA verification` — ci-cd-standard.md + action-version-matrix.md
- **4**: `docs: add decision.004, decision.005, CHANGELOG v2.1.0 entry` — decisions/ + CHANGELOG.md

---

## Success Criteria

### Verification Commands
```bash
# All tests pass
python3 -m pytest tests/ -v --tb=short
# Expected: all 393+ pass, 0 failures

# All 5 skill files pass individual validation
python3 skills/afds-doc-writer/docs_validate.py --config skills/afds-doc-writer/afds_config.yaml \
  skills/afds-doc-writer/SKILL.md \
  skills/mcp-server-architect/SKILL.md \
  skills/mcp-server-consumer/SKILL.md \
  skills/ci-cd-architect/SKILL.md \
  skills/ci-cd-architect/references/action-version-matrix.md
# Expected: Passed: 5, Failed: 0

# All standards + decisions pass validation
python3 skills/afds-doc-writer/docs_validate.py --config skills/afds-doc-writer/afds_config.yaml \
  skills/afds-doc-writer/docs_standards.md \
  skills/mcp-server-architect/mcp-server-standards.md \
  skills/mcp-server-consumer/mcp-consumer-standards.md \
  skills/ci-cd-architect/ci-cd-standard.md \
  decisions/
# Expected: Passed: 7, Failed: 0

# Zero @v* tags in ALL workflow templates
grep -c '@v[0-9]' skills/ci-cd-architect/templates/*.yml.j2
# Expected: all files return 0

# Zero Python 3.14 references in standard
grep -n '3\.14' skills/ci-cd-architect/ci-cd-standard.md
# Expected: zero results

# No project-specific references leaked into deliverables
grep -rni 'goose\|hassio\|Cortexa\|personal-agents' skills/
# Expected: zero results (TODO.md exempt)
```

### Final Checklist
- [ ] All 5 skill/reference files pass validation (5/5 PASS)
- [ ] Full standards + decisions validation passes (7 files, 0 failures)
- [ ] All tests pass (393+, no regressions)
- [ ] Zero `@v*` tags in ALL workflow templates (all SHA-pinned)
- [ ] Zero `3.14` references in ci-cd-standard.md
- [ ] New rules CI-CDW-24, 25, 26 in standard with formal entries
- [ ] Version policy table in standard (Python: 3.13 rec, 3.11 min; .NET: 8.0.x LTS)
- [ ] `decision.004-skill-dependencies.md` exists and passes validation
- [ ] `decision.005-ai-review-integration.md` exists and passes validation
- [ ] `SKILL.md` naming consistent (no lowercase `skill.md` in mcp-server-*)
- [ ] Zero project-specific references (`goose\|hassio\|Cortexa\|personal-agents`) in deliverables
- [ ] `CHANGELOG.md` has v2.1.0 entry
- [ ] `action-version-matrix.md` has correct frontmatter + verified SHAs
