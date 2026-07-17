# Changelog

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
