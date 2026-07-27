# Changelog

## 1.1.0 - 2026-07-27

This release consolidates the complete implementation history of the branch into one production version.

### Added

- Added governed `SKILL.md`, `STANDARD.md`, and `manifest.yaml` contracts for AFDS documentation, CI/CD architecture, MCP server architecture, and MCP server consumption.
- Added Python/FastMCP and .NET MCP implementation profiles, executable server generators, migration assessments, compatibility matrices, and cross-language failure guidance.
- Added secure Python, .NET, MCP, documentation, packaging, dependency, container, Semgrep, Dependabot, and local quality-gate templates.
- Added repository-wide adoption, rule-catalog, evidence-report, and independent-approval contracts with provider-backed verification.
- Added `AGENTS.md` as the canonical repository workflow for implementation and migration agents.

### Changed

- Published all bundled skills as version `1.1.0` with `maturity: stable` after the complete cross-platform production gate passed.
- Recovered valuable knowledge from the historical repository into one canonical set of standards, profiles, references, templates, tools, and tests.
- Merged local pre-commit and pre-push guidance into `ci-cd-architect` instead of maintaining a separate incomplete skill.
- Replaced brittle fixed-layout and file-count assumptions with per-skill manifests and extensible reviewed resource categories.
- Made generated Python acceptance build and install an exact wheel in an isolated environment and made container acceptance exercise the exact image that is published.
- Added deterministic complete dependency locks, immutable action pins, exact-head CI, compatibility lanes for supported Python and .NET platforms, and retained diagnostic evidence.
- Clarified normative precedence so lower-level examples, templates, generators, and simulations cannot weaken the standard.

### Security and correctness

- Hardened AFDS metadata, CommonMark fences and code spans, inline and reference links, and explicit verification requirements.
- Made MCP consumer risk, retry, reconciliation, pagination, response parsing, and remote metadata handling fail closed.
- Required authentication and selector authorization before network-backed resolution, post-connect peer verification, trusted approval provenance, optimistic concurrency, and bounded lifecycle ownership.
- Bound evidence claims to exact argv, working directories, result bytes, JUnit identities, provider jobs, artifacts, source revisions, and independent reviewer identities.
- Rejected duplicate or contradictory JUnit identities, ambiguous result paths, incomplete commit provenance, unsafe symlinks, path traversal, and repository-external content claims.

### Removed

- Removed obsolete duplicate standards, numbered implementation aliases, temporary repair workflows, payload fragments, generated coverage databases, and migration leftovers.
- Removed unsafe legacy defaults, including new use of deprecated two-endpoint HTTP plus SSE transport and self-asserted production approval.

## Historical notes before 1.1.0

- 2026-06-06: Expanded MCP server guidance for transport, middleware, discovery, security, reliability, and production operation.
- 2026-06-05: Standardized skill metadata and strengthened documentation and CI template validation.
- 2026-06-01: Added the MCP consumer domain and deterministic decision-policy helpers.
- 2026-05-23: Strengthened CI/CD release integrity, workflow security, and dependency automation.
- 2026-05-21: Corrected CI rule identifiers and static-analysis edge cases.
- 2026-05-13: Added stricter documentation structure checks.
