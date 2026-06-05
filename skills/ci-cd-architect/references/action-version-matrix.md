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

# Action Version Matrix

> **Standard Version:** 2.0.0
> **Reference:** `ref.ci-cd-standard` Rule 2 and Rule 13

This document tracks the history of GitHub Action versions used across CI/CD standard versions. It is the authoritative reference for which action versions belong to which standard version.

## Upgrade Policy

1. Action version bumps require a new standard version.
2. When a new standard version is released, all projects have a 30-day migration window.
3. Backward-incompatible action changes MUST be documented in the migration guide in SKILL.md.
4. Minor/patch action upgrades within the same standard version are NOT allowed.

## Security: Full Commit SHA Pinning

All workflows MUST pin GitHub Actions to their full immutable commit SHA, with the version tag as a trailing comment. Example:

```yaml
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v6
```

To obtain the commit SHA for any action version:
```bash
git ls-remote https://github.com/<owner>/<repo>.git refs/tags/<version> | awk '{print $1}'
```

**Curl API fallback:** If `git ls-remote` is unavailable (e.g., in restricted CI runners with `actions/checkout` disabled), use the GitHub API:
```bash
curl -s "https://api.github.com/repos/<owner>/<repo>/git/refs/tags/<version>" | jq -r '.object.sha'
```

Updating commit SHAs requires a new standard version.

### ⚠️ Known Problematic Actions

The following actions have known SHA pinning issues or documented failures — use with caution:

| Action | Issue |
|--------|-------|
| `docker/setup-buildx-action` | 3 documented SHA mismatch failures across version bumps (v3→v4). The action's release tags have been retagged after initial publication, causing SHA drift. Always verify via `git ls-remote` before updating. |

## Current Versions (Standard v2.0.0)

| Action | Version | SHA | Verified |
|--------|---------|-----|----------|
| `actions/checkout` | v6 | `df4cb1c069e1874edd31b4311f1884172cec0e10` | ✅ |
| `actions/setup-python` | v6 | `a309ff8b426b58ec0e2a45f0f869d46889d02405` | ✅ |
| `actions/setup-dotnet` | v5 | `9a946fdbd5fb07b82b2f5a4466058b876ab72bb2` | ✅ |
| `docker/setup-buildx-action` | v4 | `d7f5e7f509e45cec5c76c4d5afdd7de93d0b3df5` | ✅ |
| `docker/setup-qemu-action` | v3 | `c7c53464625b32c7a7e944ae62b3e17d2b600130` | ✅ |
| `docker/login-action` | v4 | `650006c6eb7dba73a995cc03b0b2d7f5ca915bee` | ✅ |
| `docker/metadata-action` | v6 | `80c7e94dd9b9319bd5eb7a0e0fe9291e23a2a2e9` | ✅ |
| `docker/build-push-action` | v7 | `f9f3042f7e2789586610d6e8b85c8f03e5195baf` | ✅ |
| `actions/attest-build-provenance` | v2 | `96b4a1ef7235a096b17240c259729fdd70c83d45` | ✅ |
| `actions/upload-artifact` | v7 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` | ✅ |
| `actions/download-artifact` | v8 | `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` | ✅ |
| `actions/cache` | v5 | `27d5ce7f107fe9357f9df03efb73ab90386fccae` | ✅ |
| `actions/github-script` | v9 | `373c709c69115d41ff229c7e5df9f8788daa9553` | ✅ |
| `tj-actions/changed-files` | v47 | `24d32ffd492484c1d75e0c0b894501ddb9d30d62` | ✅ |
| `softprops/action-gh-release` | v3 | `b4309332981a82ec1c5618f44dd2e27cc8bfbfda` | ✅ |
| `codecov/codecov-action` | v6 | `e79a6962e0d4c0c17b229090214935d2e33f8354` | ✅ |
| `returntocorp/semgrep-action` | v1 | `713efdd345f3035192eaa63f56867b88e63e4e5d` | ✅ |
| `github/codeql-action/upload-sarif` | v4 | `411bbbe57033eedfc1a82d68c01345aa96c737d7` | ✅ |
| `dorny/test-reporter` | v3 | `1cc81a5edf733718d4850df304aaa21c05cd7280` | ✅ |
| `marocchino/sticky-pull-request-comment` | v3.0.4 | `0ea0beb66eb9baf113663a64ec522f60e49231c0` | ✅ |

**Language versions:**
| Language | Version |
|----------|---------|
| Python | `3.14` |
| .NET | `8.0.x` (current LTS) |

## Version History

### v1.0.0 (2026-05-20) — Initial deployed standard

First version deployed across production MCP server projects. Covers Python + Docker (primary), .NET + NuGet (variant), polyglot projects. Includes CI pipeline, Docker publish, auto-tag, Semgrep security scanning, Dependabot, documentation validation, concurrency best practices, and PR feedback patterns.

All action versions are pinned at their latest stable major versions as of May 2026.
