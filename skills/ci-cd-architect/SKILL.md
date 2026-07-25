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

## Adoption and migration evidence

Before claiming that this skill has been adopted or a migration is complete:

1. Read the repository-root `contracts/adoption-assessment.yaml.template`, `contracts/rule-catalog.yaml`, compatibility matrix, and the selected skill manifest.
2. Create one assessment bound to the exact SHA and classify every stable rule as applicable, not applicable, or deferred with an owned waiver.
3. Bind each passed claim to a machine result file and passed test-case identity; a green job, badge, screenshot, or hand-written `passed` value is not evidence.
4. Use `verification_mode: provider-backed` only with the currently supported GitHub.com and GitHub Actions verifier. Other CI providers remain structural attestations until a reviewed adapter exists and cannot satisfy an approval gate.
5. Run `python contracts/validate_adoption.py <assessment> --require-approval` with read-only provider credentials before approval.
6. Require an independent review bound to the exact SHA. The reviewer must not be the PR author, a commit author or committer, or an actor that produced the referenced evidence.

Generated templates and examples are architecture seeds, not production acceptance. Apply the relevant CI/CD profile, verify the exact deployment artifact, record rollback and residual risk, and retain provider evidence long enough for the stated decision lifetime.

## Constraints

- Do not grant write permissions to untrusted pull-request code.
- Do not use mutable action tags in committed workflows.
- Do not publish an artifact that was not tested in its published form.
- Do not assume `GITHUB_TOKEN`-generated events trigger downstream workflows.
- Do not use a pip cache in a repository with no matching dependency file.
- Do not hide required release jobs behind unreachable event conditions.
