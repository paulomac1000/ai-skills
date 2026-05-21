# Action Version Matrix

> **Standard Version:** 1.0.0
> **Reference:** `ref.ci-cd-standard` Rule 2 and Rule 13

This document tracks the history of GitHub Action versions used across CI/CD standard versions. It is the authoritative reference for which action versions belong to which standard version.

## Upgrade Policy

1. Action version bumps require a new standard version.
2. When a new standard version is released, all projects have a 30-day migration window.
3. Backward-incompatible action changes MUST be documented in the migration guide in SKILL.md.
4. Minor/patch action upgrades within the same standard version are NOT allowed.

## Current Versions (Standard v1.0.0)

| Action | Version | Purpose |
|--------|---------|---------|
| `actions/checkout` | `v6` | Checkout repository |
| `actions/setup-python` | `v6` | Set up Python runtime |
| `docker/setup-buildx-action` | `v4` | Set up Docker Buildx |
| `docker/login-action` | `v4` | Log in to container registry |
| `docker/metadata-action` | `v6` | Extract Docker tags and labels |
| `docker/build-push-action` | `v7` | Build and push Docker image |
| `actions/attest` | `v4` | Generate artifact attestation |
| `softprops/action-gh-release` | `v3` | Create GitHub Release |
| `codecov/codecov-action` | `v6` | Upload coverage to Codecov |
| `actions/upload-artifact` | `v4` | Upload build artifacts |
| `actions/download-artifact` | `v4` | Download artifacts between jobs |
| `actions/cache` | `v5` | Cache dependencies (NuGet, pip) |
| `semgrep/semgrep-action` | `v1` | Security scanning |
| `github/codeql-action/upload-sarif` | `v4` | Upload SARIF to Security tab |
| `actions/setup-dotnet` | `v5` | Set up .NET SDK |
| `actions/github-script` | `v9` | Post/update PR comments |
| `tj-actions/changed-files` | `v47` | Detect changed files |
| `dorny/test-reporter` | `v3` | Publish test results |
| `marocchino/sticky-pull-request-comment` | `v3` | Post coverage summary to PR |

**Language versions:**
| Language | Version |
|----------|---------|
| Python | `3.14` |
| .NET | `8.0.x` |

## Version History

### v1.0.0 (2026-05-20) — Initial deployed standard

First version deployed across production MCP server projects. Covers Python + Docker (primary), .NET + NuGet (variant), polyglot projects. Includes CI pipeline, Docker publish, auto-tag, Semgrep security scanning, Dependabot, documentation validation, concurrency best practices, and PR feedback patterns.

All action versions are pinned at their latest stable major versions as of May 2026.
