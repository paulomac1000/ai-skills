---
description: Pinning index for the 3 remote hooks used by precommit-standard. For discovering additional hooks, see https://pre-commit.com/hooks.html
doc_id: ref.hook-catalog
type: ref
status: active
rigor_tier: L2
stability: stable
ai_scope: editable
source_of_truth: true
upstream: [ref.precommit-standard]
last_verified: 2026-06-14
owners: ["precommit-maintainer"]
ttl_days: 30
standard_version: "1.1.0"
---

# Hook Catalog — Project Pinning Index

> **Canonical hooks source**: https://pre-commit.com/hooks.html
> **Standard**: `ref.precommit-standard` Rules PRECOMMIT-09, PRECOMMIT-10, PRECOMMIT-14
> **Rule details**: PRECOMMIT-09 (Remote Hook Pinning), PRECOMMIT-10 (Committed Config and AGENTS.md), PRECOMMIT-14 (Secret Scanning)
> **Rationale**: This file pins the SHA for each remote hook the precommit-standard uses. For DISCOVERING new hooks, see the canonical hooks list at https://pre-commit.com/hooks.html (maintained by the pre-commit team). We do NOT duplicate that list here — by reference, not by copy.

## SHA Pinning Policy (PRECOMMIT-09)

Remote hooks MUST be pinned to their full 40-character commit SHA, with the version tag as a trailing comment:

```yaml
- repo: https://github.com/pre-commit/pre-commit-hooks
  rev: cef0300fd0fc4d2a87a85fa2093c6b283ea36f4b  # v5.0.0
```

To obtain the commit SHA for any hook version:
```bash
git ls-remote https://github.com/<owner>/<repo>.git refs/tags/<version> | awk '{print $1}'
```

**Why SHA pinning**: Mutable version tags can be re-targeted by attackers who compromise a hook repository. The pre-commit project itself emits a warning for mutable revs (see `pre_commit.clientlib.WarnMutableRev`). See https://pre-commit.com/#using-the-latest-version-for-a-repository.

## Native Git Hook Template (`pre-commit-shell.j2`)

For projects that cannot use the pre-commit Python framework (e.g., .NET, Rust, Go, polyglot repos), the `pre-commit-shell.j2` template generates a native bash script at `.githooks/pre-commit`. It mirrors the same 4 hook categories:

| Check | Entry | Category |
|-------|-------|----------|
| `format_check` | `dotnet format`, `cargo fmt --check`, `gofmt -l`, `ruff format --check` | Format |
| `build_check` | `dotnet build`, `cargo check`, `go build`, `python -m compileall` | Compile / Syntax |
| `merge_conflict_check` | `grep -r '<<<<<<< HEAD'` | Merge Conflict |
| `secret_scan` | `grep -r 'BEGIN (RSA\|EC\|DSA\|OPENSSH\|PRIVATE) KEY'` | Secret Scan |

**Setup**: `git config --local core.hooksPath .githooks && chmod +x .githooks/pre-commit`

**Pitfalls**: Missing `chmod +x` causes git to silently skip the hook. Wrong `core.hooksPath` points at the wrong directory. Does not run on Windows (native bash only).

## Pinned Hooks (used by precommit-standard)

| Hook ID(s) | Repo URL | SHA (40-char) | Version | Category | Notes |
|------------|----------|---------------|---------|----------|-------|
| `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-merge-conflict`, `check-case-conflict`, `check-added-large-files`, `mixed-line-ending`, `detect-private-key` | `pre-commit/pre-commit-hooks` | `cef0300fd0fc4d2a87a85fa2093c6b283ea36f4b` | v5.0.0 | Generic | Universal language-agnostic hooks. Full list: https://github.com/pre-commit/pre-commit-hooks. `detect-private-key` is the PRECOMMIT-14 minimum. |
| `ruff`, `ruff-format` | `astral-sh/ruff-pre-commit` | `<PINNED_AT_RELEASE>` | v0.11.0+ | Lint + Format | Linter and formatter. Replaces flake8+isort+black. |
| `gitleaks` (optional) | `gitleaks/gitleaks` | `<PINNED_AT_RELEASE>` | latest | Secret Scanning | PRECOMMIT-14 recommended. https://github.com/gitleaks/gitleaks. |
| `detect-secrets` (optional) | `Yelp/detect-secrets` | `<PINNED_AT_RELEASE>` | latest | Secret Scanning | PRECOMMIT-14 alternative. Requires baseline. |

## Local Hooks (repo: local — no SHA needed)

| Hook | Entry pattern | Notes |
|------|---------------|-------|
| mypy | `python3 -m mypy <src> --strict` | Static type checking |
| bandit | `python3 -m bandit -r <src> -ll` | AST-based security scanner |
| pytest (unit) | `python3 -m pytest tests/unit/ -q` | Pre-commit stage |
| pytest (integration) | `python3 -m pytest tests/integration/ -q` | Pre-push stage only |

## Discovering Additional Hooks

For the canonical list of all available hooks maintained by the pre-commit team:
- **https://pre-commit.com/hooks.html** — featured hooks (language-agnostic, Python, shell, web, config, text/docs, commit messages, secret scanning, other languages)
- **https://github.com/topics/pre-commit-hook** — community-maintained hooks

When adding a new hook to the precommit-standard templates:
1. Identify the hook at https://pre-commit.com/hooks.html.
2. Obtain the full SHA: `git ls-remote <repo-url> refs/tags/<version> | awk '{print $1}'`
3. Add to the appropriate template (python/mcp/minimal) with SHA + version tag comment.
4. Update `last_verified` here.
