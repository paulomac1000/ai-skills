---
name: ci-cd-architect
description: Design, repair, and review secure local and hosted quality gates for Python, .NET, MCP, documentation, packages, and containers.
---

# CI/CD architect

Use this skill when a repository needs trustworthy feedback before merge or a reproducible artifact release.

## Workflow

1. Classify the repository archetype and release artifact.
2. Inventory existing commands, tests, package managers, branch policy, secrets, environments, and deployment boundaries.
3. Select the smallest set of workflow profiles that covers the actual risks.
4. Keep local hooks fast and deterministic; make CI the authoritative full gate.
5. Pin every third-party action to a full commit SHA and maintain version comments separately from trust.
6. Give each job least privilege, a timeout, explicit concurrency behavior, and bounded artifact retention.
7. Separate validation from privileged publication.
8. Build, smoke-test, and publish the same artifact.
9. Verify release identity from the selected revision, not from unrelated trigger context.
10. Render and parse templates, run the repository quality gate, and inspect the final workflow permissions.

Read `STANDARD.md`, then choose profiles using `references/template-selection.md`. Use `references/local-quality-gates.md`, `action-sha-maintenance.md`, and `failure-patterns.md` for implementation details.

## Constraints

- Do not grant write permissions to untrusted pull-request code.
- Do not use mutable action tags in committed workflows.
- Do not publish an artifact that was not tested in its published form.
- Do not assume `GITHUB_TOKEN`-generated events trigger downstream workflows.
- Do not use a pip cache in a repository with no matching dependency file.
- Do not hide required release jobs behind unreachable event conditions.
