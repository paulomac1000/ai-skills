---
description: Single authoritative standard for pre-commit hook configuration across all compliant Python projects — hook ordering, CI mirroring, speed budgets, environment consistency, and AGENTS.md integration
doc_id: ref.precommit-standard
type: ref
status: active
rigor_tier: L2
ttl_days: 365
stability: stable
ai_scope: editable
domain: pre-commit
tags: ["pre-commit", "hooks", "linting", "formatting", "ci-cd", "python", "mypy", "ruff", "bandit"]
owners: ["backend-team"]
upstream:
  - ref.ci-cd-standard
source_of_truth: true
last_verified: "2026-06-07"
doc_kind: atomic
standard_version: "1.0.0"
---

# Pre-commit Standard — Unified Hook Configuration for Python Projects

> [!IMPORTANT]
> This document is the single authoritative source of truth for how `.pre-commit-config.yaml` is structured, maintained, and validated across all compliant projects. It covers hook ordering, CI mirroring, speed budgets, environment consistency, AGENTS.md integration, and common failure modes. All pre-commit configuration files in compliant projects MUST conform to these rules.
>
> If any project's `.pre-commit-config.yaml` contradicts this standard, **this file takes precedence**. Update the project config to match.

## PURPOSE

Define a unified, version-locked, and reproducible pre-commit hook standard for Python projects. Ensure every project's pre-commit hooks run the same checks as CI lint and test jobs in the same order, with consistent tool versions, speed guarantees, and failure behavior. The standard supports multiple project archetypes (MCP servers, web services, CLI tools, libraries) through configurable hook selection.

## SCOPE

- INCLUDED: `.pre-commit-config.yaml` structure, hook ordering (generic → lint → format → types → security → docs → tests), `repo: local` vs `repo: remote` hook selection, `fail_fast` policy, `pass_filenames` conventions, speed budgets per hook, stage assignment (`pre-commit` vs `pre-push`), CI mirroring requirements, AGENTS.md pre-commit section, `ruff target-version` policy, mypy override requirements, CAFDS doc hook exclude alignment, test collection error detection.
- EXCLUDED: Individual tool configuration beyond pre-commit integration (ruff rules, mypy strictness, bandit severity — these are defined in `ref.ci-cd-standard`). Deployment, secrets management, project-specific business logic.

## DEFINITIONS

- **pre-commit**: A framework for managing and maintaining multi-language pre-commit hooks that run before `git commit`. The `.pre-commit-config.yaml` file defines which hooks run at which stage.
- **local repo** (`repo: local`): A hook that runs tools already installed in the developer's environment (e.g., mypy, bandit, pytest). No download required. Version tracking is manual — the developer must keep tool versions in sync with CI.
- **remote repo** (`repo: https://...`): A hook sourced from a public Git repository. Downloaded and cached on first run. Pinned to a specific commit SHA for immutability. Used for standard tools like ruff and pre-commit-hooks.
- **pass_filenames**: A hook-level option that controls whether staged filenames are passed to the hook's `entry` command. Defaults to `true` for most hooks. Must be set to `false` when the hook scans the entire repository (e.g., mypy, pytest, bandit) or operates on a fixed directory. **Convention**: `pass_filenames: false` is the default for most repo-local hooks — the hook receives only staged file paths by default.
- **fail_fast**: A hook-level option that, when `true`, stops the entire pre-commit run at the first failure. When `false` (the mandatory setting per this standard), all hooks run and report all errors before pre-commit exits with a failure status.
- **stages**: Pre-commit supports multiple stages — `pre-commit` (runs at `git commit`), `pre-push` (runs at `git push`), `commit-msg`, `post-commit`, and others. This standard dictates which stage each hook category belongs to.
- **CI mirroring**: The principle that pre-commit hooks MUST execute the same tools, in the same order, as the CI lint and test jobs. Pre-commit is a local pre-flight for CI, not an independent check suite.
- **hook ordering chain**: The canonical order of hook categories: generic (trailing whitespace, YAML/TOML validation) → lint (ruff check) → format (ruff format) → types (mypy) → security (bandit) → docs (CAFDS) → tests (pytest).

## RULES

### Rule 1: CI Mirroring

**[RULE: PRECOMMIT-01] [L1+]** Pre-commit MUST run the same checks as CI lint+test jobs in the same order. Every tool configured in CI's `lint` and `test` jobs MUST appear in `.pre-commit-config.yaml` at the appropriate stage. The hook ordering (see PRECOMMIT-02) MUST match the CI job step ordering. Pre-commit is a local pre-flight that mirrors CI — it is NOT an independent check suite with its own toolset or ordering.

Pre-commit runs in the developer's full local environment (`pip install -e ".[dev]"`), which includes all project dependencies. CI lint jobs frequently have a minimal environment (`pip install ruff mypy bandit` without project deps). This environment mismatch is the root cause of many pre-commit-vs-CI failures. Rules PRECOMMIT-03 (ruff target-version), PRECOMMIT-11 (mypy overrides), and PRECOMMIT-12 (CAFDS excluded_dirs) specifically address this mismatch.

### Rule 2: Hook Ordering

**[RULE: PRECOMMIT-02] [L1+]** Hook ordering in `.pre-commit-config.yaml` MUST follow this canonical chain:

```
generic → lint → format → types → security → docs → tests
```

Where each category maps to:

| Category | Tools | Stage | Notes |
|----------|-------|-------|-------|
| generic | trailing-whitespace, end-of-file-fixer, check-yaml, check-toml, check-json | pre-commit | Run first — cheap, catch structural errors fast |
| lint | ruff check | pre-commit | Run before format to catch issues format could mask |
| format | ruff format | pre-commit | Run after lint; formatted code is easier to reason about |
| types | mypy | pre-commit | Run after format so type errors reference formatted source |
| security | bandit | pre-commit | Run after format; security issues reference formatted source |
| docs | CAFDS (docs_validate.py), semgrep | pre-commit | Network-OK, runs after code quality gates |
| tests | pytest (unit) | pre-commit | Run last — tests pass or fail based on the code, not formatting |

### Rule 3: Ruff target-version

**[RULE: PRECOMMIT-03] [L1+]** The `ruff target-version` in `pyproject.toml` MUST match the minimum Python version declared in `requires-python`, NOT the CI runner's Python version. Setting `target-version` to a higher version than the project supports causes `ruff format` to rewrite syntax into forms incompatible with older Python versions.

**Example failure**: `target-version = "py314"` on a project with `requires-python = ">=3.11"` caused ruff to convert `except (X, Y):` syntax back to `except X as e:` followed by separate handler — breaking Python 3.11-compatible except clauses that were intentionally modern.

**Correct**: `target-version = "py311"` when `requires-python = ">=3.11"`.

### Rule 4: No Error Masking

**[RULE: PRECOMMIT-04] [L1+]** NEVER use `|| true` or `--ignore` to mask errors in pre-commit hook entries. Silent failures in pre-commit produce silent failures in CI. If a check legitimately cannot pass, it should be deferred to a later stage (e.g., `pre-push` for slow tests) or the underlying issue should be fixed — not masked.

**Real-world failure**: An agent added `|| true` to ruff format to bypass `except (X, Y):` syntax errors instead of fixing the `target-version` mismatch (PRECOMMIT-03). The syntax was silently broken until CI failed.

### Rule 5: python3 Entry Commands

**[RULE: PRECOMMIT-05] [L1+]** All hook `entry` commands MUST use `python3`, not `python`. Debian-based systems (including Ubuntu) only provide `python3` as the system Python binary; `python` does not exist by default. Using `python` in hook entries causes pre-commit to fail with "command not found" on Debian/Ubuntu.

```yaml
# CORRECT
entry: python3 -m pytest tests/unit/ -v

# WRONG
entry: python -m pytest tests/unit/ -v
```

### Rule 6: fail_fast Policy

**[RULE: PRECOMMIT-06] [L1+]** ALL hooks MUST use `fail_fast: false`. This ensures all errors are collected and reported before pre-commit exits, rather than stopping at the first failure. Developers can fix all issues in one pass rather than iterating through failures one at a time.

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-check
        fail_fast: false
```

### Rule 7: Heavy Tests to pre-push

**[RULE: PRECOMMIT-07] [L2+]** Heavy tests (integration tests, end-to-end tests, tests requiring external services) MUST be assigned to the `pre-push` stage, not `pre-commit`. The `pre-commit` stage is limited to 30 seconds total (PRECOMMIT-08) — integration tests that take 30+ seconds belong at `pre-push`.

```yaml
- id: integration-tests
  name: Integration tests (pre-push only)
  entry: python3 -m pytest tests/integration/ -v
  stages: [pre-push]
  pass_filenames: false
```

### Rule 8: Speed Budget

**[RULE: PRECOMMIT-08] [L2+]** The total runtime of all hooks on the `pre-commit` stage MUST be under 30 seconds. If the combined runtime exceeds 30 seconds, move the slowest hooks to `pre-push`. Developers will disable pre-commit entirely if it slows down their commit workflow.

| Hook Category | Target Time | Stage |
|---------------|------------|-------|
| generic (whitespace, YAML) | <2s | pre-commit |
| ruff check | <3s | pre-commit |
| ruff format | <3s | pre-commit |
| mypy | <10s | pre-commit |
| bandit | <5s | pre-commit |
| CAFDS docs | <5s | pre-commit |
| pytest unit | <10s | pre-commit |
| **Total budget** | **<30s** | pre-commit |
| pytest integration | — | **pre-push only** |
| e2e tests | — | **CI only** |

### Rule 9: Remote Hook Pinning

**[RULE: PRECOMMIT-09] [L2+]** Remote hooks MUST use commit SHA pinning, NOT version tags. Version tags are mutable references — an attacker who compromises a hook repository can push malicious code to a version tag. Commit SHAs are cryptographically immutable.

```yaml
# CORRECT — commit SHA
- repo: https://github.com/astral-sh/ruff-pre-commit
  rev: a8fe2af36a22bca86a229fb3b00d132b41c5cd08  # v0.11.0

# WRONG — mutable tag
- repo: https://github.com/astral-sh/ruff-pre-commit
  rev: v0.11.0
```

### Rule 10: Committed Config and AGENTS.md

**[RULE: PRECOMMIT-10] [L1+]** The `.pre-commit-config.yaml` file MUST be committed to the repository. Every project's `AGENTS.md` MUST contain a pre-commit section documenting the expected hooks, their purpose, and how to install them (`pre-commit install`).

The AGENTS.md section SHOULD include:
- A list of hooks with brief descriptions
- The command to install: `pre-commit install`
- The command to run manually: `pre-commit run --all-files`
- A note that pre-commit mirrors CI lint+test (PRECOMMIT-01)

### Rule 11: Mypy Overrides for Third-Party Dependencies

**[RULE: PRECOMMIT-11] [L1+]** The `[[tool.mypy.overrides]]` section in `pyproject.toml` MUST list every third-party dependency used by the project. Each override MUST include the `module` key (the import name) and `ignore_missing_imports = true` (when type stubs are unavailable). CI lint jobs frequently have minimal environments (`pip install ruff mypy bandit` without project dependencies) — `ignore_missing_imports` set globally is prohibited (CI-CDW-8), so every third-party package that lacks type stubs must be explicitly declared in overrides.

**Real-world failure**: `mypy` passed locally because the developer had installed all project deps via `pip install -e ".[dev]"`. CI lint ran `pip install ruff mypy bandit` (minimal env), so mypy could not resolve `fastmcp.*`, `requests.*`, `pyyaml.*`, `starlette.*`, `uvicorn.*`, `dateutil.*`, `pydantic.*`. Seven third-party libraries were silently type-checked as `Any` or errored.

```toml
[[tool.mypy.overrides]]
module = ["fastmcp", "requests", "pyyaml", "starlette", "uvicorn", "dateutil", "pydantic"]
ignore_missing_imports = true
```

### Rule 12: CAFDS Exclude Alignment

**[RULE: PRECOMMIT-12] [L1+]** The `excluded_dirs` in `afds_config.yaml` MUST match the directories excluded by the pre-commit docs validation hook's `exclude` pattern. If pre-commit excludes `.omo/` from CAFDS scanning but `afds_config.yaml` does not list `.omo` in `excluded_dirs`, CI's docs validation will scan `.omo/` and fail on non-AFDS planning documents.

**Real-world failure**: The pre-commit hook had `exclude: ^(\.omo/|archived/)` but `afds_config.yaml` lacked `.omo` in `excluded_dirs`. CI scanned `.omo/plans/*.md` (planning docs without YAML frontmatter) and failed.

**Correct alignment**:
```yaml
# .pre-commit-config.yaml
- id: cafds-docs
  exclude: ^(\.omo/|archived/)

# afds_config.yaml
excluded_dirs:
  - archived
  - .omo
```

### Rule 13: Test Collection Error Detection

**[RULE: PRECOMMIT-13] [L2+]** Pre-commit MUST NOT silently pass when test files fail to collect. If `pytest --collect-only` reports errors (import errors, syntax errors in test files, missing fixtures), the pre-commit run MUST fail even if all collected tests pass. Environment-specific import errors (e.g., a package works in CI but fails in the developer's virtual environment due to a missing optional dependency) must not mask test collection failures.

**Real-world failure**: A `fastmcp` import error in a test file prevented `test_server.py` from collecting. All other collected tests passed, so pre-commit reported "Passed." In CI (where `fastmcp` was properly installed), the tests collected and failed due to an API format change. The silent pre-commit pass hid the CI failure until post-push.

**Mitigation**:
```bash
pytest --collect-only -q 2>&1 | grep -q "ERROR" && exit 1
```

Or use the `-x` (exit on first error) flag on the test step: `pytest tests/ -x --collect-only` before running the full suite.

## INTERFACES

- INPUT: Repository with `.pre-commit-config.yaml`, `pyproject.toml` with `[tool.ruff]`, `[tool.mypy]`, and `[tool.bandit]` sections, and a test suite.
- OUTPUT: Pass/fail status on `git commit`. All lint, format, type, security, docs, and unit test checks run before commit is allowed. Hook output is printed to stdout and stderr.
- SIDE_EFFECTS: Pre-commit modifies staged files when auto-fix hooks run (e.g., `ruff format` reformats code, `trailing-whitespace` removes trailing spaces). After auto-fix, files must be re-staged with `git add`. Pre-commit installs hook environments into `.cache/pre-commit/`.

## STATE

- Assumptions: The developer has `pre-commit` installed (`pip install pre-commit`). Python 3.11+ is available in the developer's environment. The project uses `pyproject.toml` with `[tool.ruff]`, `[tool.mypy]`, and `[tool.bandit]` sections. CI lint and test jobs mirror the pre-commit hook configuration (PRECOMMIT-01). The developer has run `pre-commit install` to register the git hook. The AGENTS.md file exists at the repository root.
- Constraints: Total pre-commit runtime must stay under 30 seconds (PRECOMMIT-08). Hook ordering is fixed and must not be reordered (PRECOMMIT-02). All hooks use `fail_fast: false` (PRECOMMIT-06). Remote hooks must use commit SHA pinning (PRECOMMIT-09). No error masking via `|| true` or `--ignore` (PRECOMMIT-04).
- Known Limitations: Pre-commit runs in the developer's full local environment, which may mask environment-specific issues that appear in CI's minimal environment (PRECOMMIT-11). Test collection errors are environment-dependent — a package import failure in one environment may silently skip tests (PRECOMMIT-13). Pre-commit does not replace CI; it is a pre-flight that mirrors CI checks. Rust-based tools (ruff) can have different behavior across versions — pin remote hooks to commit SHA, not version tags (PRECOMMIT-09). Some hooks (mypy, bandit, pytest) require `pass_filenames: false` because they scan the entire repository rather than operating on individual staged files.

## EDGE_CASES

- CASE: Developer works offline and a remote hook cache is empty → EXPECTED: Pre-commit fails for that hook until network is restored. Use `SKIP=hook-id git commit` to bypass.
- CASE: pre-commit total runtime exceeds 30 seconds → EXPECTED: Violation of PRECOMMIT-08. Move the slowest hook to `pre-push` stage.
- CASE: `ruff target-version` is set to a higher version than `requires-python` → EXPECTED: Violation of PRECOMMIT-03. `ruff format` may rewrite syntax into forms incompatible with the declared minimum Python version.
- CASE: Developer uses `python` instead of `python3` in hook entry on Debian/Ubuntu → EXPECTED: Hook fails with "command not found". Fix per PRECOMMIT-05.
- CASE: Test collection error (import error in a test file) prevents test discovery → EXPECTED: Pre-commit must fail per PRECOMMIT-13, not silently pass.
- CASE: A third-party dependency lacks type stubs and is not listed in `[[tool.mypy.overrides]]` → EXPECTED: Violation of PRECOMMIT-11. mypy may pass locally (full env) but fail in CI (minimal env).
- CASE: Developer uses `--ignore` or `|| true` to mask a failing hook → EXPECTED: Violation of PRECOMMIT-04. The underlying issue will eventually fail in CI.

## EXAMPLES

### Example `.pre-commit-config.yaml` (standard Python project)

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: 5v3z8a9b2c1d4e6f7a8b9c0d1e2f3a4b5c6d7e8f9  # v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-json

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: a8fe2af36a22bca86a229fb3b00d132b41c5cd08  # v0.11.0
    hooks:
      - id: ruff
        name: ruff check
        args: [--fix]
        fail_fast: false
      - id: ruff-format
        name: ruff format
        fail_fast: false

  - repo: local
    hooks:
      - id: mypy
        name: mypy type check
        entry: python3 -m mypy src/ --strict
        language: system
        types: [python]
        pass_filenames: false
        fail_fast: false

      - id: bandit
        name: bandit security scan
        entry: python3 -m bandit -r src/ -ll
        language: system
        types: [python]
        pass_filenames: false
        fail_fast: false

      - id: pytest-unit
        name: unit tests
        entry: python3 -m pytest tests/unit/ -v
        language: system
        types: [python]
        pass_filenames: false
        fail_fast: false

      - id: pytest-integration
        name: integration tests (pre-push only)
        entry: python3 -m pytest tests/integration/ -v
        language: system
        types: [python]
        pass_filenames: false
        stages: [pre-push]
```

### Example AGENTS.md pre-commit section

```markdown
## Pre-commit Hooks

This project uses pre-commit hooks to catch issues before they reach CI. The hooks mirror our CI lint and test jobs exactly.

### Install

```bash
pip install pre-commit
pre-commit install
```

### Run manually

```bash
pre-commit run --all-files  # run all hooks on all files
SKIP=mypy,bandit git commit # skip specified hooks
```

### Hook summary

| Hook | Purpose |
|------|---------|
| trailing-whitespace | Remove trailing whitespace |
| end-of-file-fixer | Ensure files end with a newline |
| check-yaml/check-toml/check-json | Validate config file syntax |
| ruff check | Lint Python code |
| ruff format | Format Python code |
| mypy | Static type checking |
| bandit | Security scanning |
| pytest unit | Run unit tests |
| pytest integration | Run integration tests (pre-push only) |
```

## NON_GOALS

- This standard does not cover individual tool configuration beyond their pre-commit integration. Ruff rule selection, mypy strictness levels, and bandit severity are defined in `ref.ci-cd-standard`.
- It does not prescribe specific hook version management tools (e.g., `pre-commit autoupdate`, Dependabot for pre-commit). Version management patterns are covered in `ref.ci-cd-standard`.
- It does not cover commit message hooks (`commit-msg` stage), pre-receive hooks, or server-side hooks.
- It does not define project-specific test configurations — only that tests MUST run and MUST NOT silently skip.

## CHANGELOG

### 1.0.0 (2026-06-07) — Initial standard

- PRECOMMIT-01: CI mirroring — pre-commit MUST run same checks as CI lint+test in same order
- PRECOMMIT-02: Hook ordering chain — generic → lint → format → types → security → docs → tests
- PRECOMMIT-03: ruff target-version MUST match requires-python minimum, not CI runner version
- PRECOMMIT-04: NEVER use `|| true` or `--ignore` to mask errors
- PRECOMMIT-05: Use `python3` not `python` in all entry commands
- PRECOMMIT-06: ALL hooks use `fail_fast: false`
- PRECOMMIT-07: Heavy tests go to `pre-push` stage, not `pre-commit`
- PRECOMMIT-08: Pre-commit total runtime MUST be under 30 seconds
- PRECOMMIT-09: Remote hooks use commit SHA, not version tags
- PRECOMMIT-10: `.pre-commit-config.yaml` committed, AGENTS.md section present
- PRECOMMIT-11: `[[tool.mypy.overrides]]` MUST list every third-party dependency
- PRECOMMIT-12: CAFDS `excluded_dirs` in `afds_config.yaml` MUST match pre-commit doc hook excludes
- PRECOMMIT-13: Pre-commit MUST NOT silently pass when test files fail to collect
