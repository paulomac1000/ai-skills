# Changelog

## 1.1.0-rc.1 - 2026-07-24

- Bind provider-backed evidence to exact source checkouts, provider-derived job and producer identities, uploaded JUnit digests, and passed test-case selectors.
- Generate schema-version 2 evidence reports in every compatibility, .NET, container, filesystem, and repository evidence lane with 90-day retention.
- Derive reviewer independence from PR authors, commit authors/committers, and evidence-producing workflow actors.
- Add the shared adoption and migration evidence gate to every skill and state the GitHub.com-only provider scope of `1.1.0-rc.1`.

- Added versioned, machine-readable skill contracts with compatibility, maturity, dependency, deprecation, and normative-entrypoint metadata.
- Added one repository-wide adoption assessment, JSON Schema, semantic validator, stable per-skill rule catalog, compatibility evidence contract, and MCP-specific extension with adversarial approval tests.
- Defined normative precedence so standards and active decisions cannot be weakened by profiles, workflows, generators, examples, or simulations.
- Changed generated Python acceptance to build a wheel, install the exact wheel into an isolated environment, and execute the official MCP client suite without editable installs or `PYTHONPATH`.
- Replaced direct-only Python constraints with complete platform-specific runtime and development lock graphs, artifact hashes, `--require-hashes`, and post-install `pip check`; moved the MCP SDK baseline to the fixed 1.28.x line.
- Added Linux, macOS, and Windows tests for atomic no-replace generator publication.
- Added support for production dot-separated .NET namespaces while rejecting unsafe and reserved namespace roots.
- Added pinned Ruff, formatting, mypy, Bandit, dependency-audit, branch-coverage, and retained-diagnostics gates to repository CI and local validation, including the complete Python generator implementation.
- Replaced the brittle migration-test function allowlist with execution of the complete migration contract file.
- Clarified that the bundled MCP consumer engine is a conservative reference helper rather than complete organizational authorization or multi-axis policy.
- Added strict shared SemVer 2.0 validation, exact-head and merge-result CI evidence, Python 3.12-3.14 plus Linux/macOS/Windows compatibility lanes, cross-platform .NET artifact lanes, and a built non-root container smoke through the official MCP client.

## Unreleased - 2026-07-18

- Recovered operational knowledge removed by the cleanup refactor into focused AFDS, CI/CD, MCP server, and MCP consumer playbooks, examples, templates, tools, and regression tests.
- Replaced the global file-count and exact-layout policy with per-skill manifests and extensible resource categories.
- Merged local pre-commit guidance into the CI/CD architecture and removed the incomplete top-level skill.
- Hardened AFDS validation for metadata types, reference-style links, CommonMark code spans, fenced blocks, and relative links.
- Made MCP consumer risk provenance fail closed, rejected negative retry attempts and invalid cursor types, and preserved protocol-native errors.
- Added Python/FastMCP and .NET MCP implementation profiles plus a cross-language incident map.
- Restored Python, MCP, container, .NET, NuGet, documentation, Semgrep, Dependabot, and local-gate templates.
- Changed container publication to build once, smoke-test the exact local image, push the same image tags, and attest the resulting registry digest.
- Added Renovate regex management and parsed-template tests for immutable action SHA maintenance.

## 1.0.0 - 2026-07-17

- Prepared the first stable, project-independent release by preserving reusable tools and tested templates while removing development-stage artifacts and duplicated standards.

## 2026-06-06

- Expanded the MCP server guidance with transport, middleware, discovery, security, reliability, and production-operation rules.

## 2026-06-05

- Standardized skill metadata and hardened documentation and CI template validation.

## 2026-06-01

- Added the MCP consumer skill and its deterministic decision-policy helpers.

## 2026-05-23

- Strengthened CI/CD guidance for immutable actions, release integrity, workflow safety, and dependency automation.

## 2026-05-21

- Corrected CI rule identifiers and improved static-analysis and workflow edge-case handling.

## 2026-05-13

- Added stricter documentation structure checks and expanded the documentation and MCP standards.
