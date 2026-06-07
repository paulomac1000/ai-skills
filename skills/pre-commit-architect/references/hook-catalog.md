---
doc_id: ref.hook-catalog
type: ref
status: active
rigor_tier: L2
stability: stable
ai_scope: editable
source_of_truth: true
upstream: [ref.precommit-standard]
last_verified: 2026-06-07
owners: ["precommit-maintainer"]
ttl_days: 30
description: Available pre-commit hooks with SHA pinning and upgrade policy
---

# Hook Catalog

> **Standard Version:** 1.0.0
> **Reference:** `ref.precommit-standard` Rules PRECOMMIT-09, PRECOMMIT-10

This document catalogs every hook managed by the pre-commit architect skill. Remote hooks use full commit SHA pinning per PRECOMMIT-09. Local hooks use `repo: local` and rely on the developer's environment.

## SHA Pinning Policy

Remote hooks MUST be pinned to their full immutable commit SHA, with the version tag as a trailing comment:

```yaml
- repo: https://github.com/pre-commit/pre-commit-hooks
  rev: cef0300fd0fc4d2a87a85fa2093c6b283ea36f4b  # v5.0.0
```

To obtain the commit SHA for any hook version:
```bash
git ls-remote https://github.com/<owner>/<repo>.git refs/tags/<version> | awk '{print $1}'
```

## Hook Catalog

| Hook ID | Repo URL | SHA/Version | Category | Notes |
|---------|----------|-------------|----------|-------|
| `trailing-whitespace` | `pre-commit/pre-commit-hooks` | `cef0300f` (`v5.0.0`) | Generic | Removes trailing whitespace; first in ordering per PRECOMMIT-02 |
| `check-yaml` | `pre-commit/pre-commit-hooks` | `cef0300f` (`v5.0.0`) | Generic | Validates YAML syntax; runs before lint hooks |
| `check-toml` | `pre-commit/pre-commit-hooks` | `cef0300f` (`v5.0.0`) | Generic | Validates TOML syntax (pyproject.toml) |
| `ruff` | `astral-sh/ruff-pre-commit` | `99abe27a` (`v0.11.0`) | Lint | Ruff check + format; replaces flake8+isort+black |
| `mypy` | `repo: local` | N/A (local) | Types | Static type checking; uses `additional_dependencies` for third-party stubs |
| `bandit` | `repo: local` | N/A (local) | Security | AST-based security scanner; uses `additional_dependencies` |
| `pytest` | `repo: local` | N/A (local) | Tests | Unit test runner; pre-commit stage only (integration tests must use pre-push) |
| `semgrep` | `returntocorp/semgrep-action` | `713efdd3` (`v1`) | Security | Semgrep SAST scanning; must match CI semgrep config |
| `CAFDS docs` | `repo: local` | N/A (local) | Docs | Validates AFDS frontmatter via `curl \| python3`; uses `docs_validate.py` |

## Hook Ordering (PRECOMMIT-02)

```
Generic (trailing-whitespace, check-yaml, check-toml)
  → Lint (ruff check, ruff format)
    → Types (mypy)
      → Security (bandit, semgrep)
        → Docs (CAFDS)
          → Tests (pytest unit)
```

Heavy tests (integration, e2e) MUST go to `pre-push` stage per PRECOMMIT-07.

## Version History

### v1.0.0 (2026-06-07) — Initial catalog

First version based on deployment experience from `ha-mcp-readonly` and `local-home-devices-mcp`. All remote hooks pinned at latest stable versions as of June 2026.
