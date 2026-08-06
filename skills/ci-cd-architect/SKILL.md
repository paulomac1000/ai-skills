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

For GitHub Actions policy checks, run `tools/check_github_actions_policy.py` from a trusted immutable checkout and pass the candidate repository root as its argument. A pull request must not provide the authoritative copy of the auditor that approves the same pull request. A repository-local mirror may support offline diagnostics only when CI compares it byte-for-byte with the pinned trusted source before treating its result as evidence.

The auditor's release-environment allowlist is empty by default. Add `--protected-release-environment NAME` only after trusted provider-side inspection confirms that the exact GitHub environment exists and has the required approval and deployment restrictions. The assessed revision must not provide, modify, or derive this allowlist. A name such as `production-release` is only a syntax-constrained identifier and never proves protection by itself.

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

- Do not grant write permissions to untrusted pull-request code. Keep workflow-level permissions read-only; narrowly scoped write access belongs only to a non-PR job whose exact release environment is present in a trusted allowlist obtained outside the assessed revision.
- Do not treat an environment name, an `environment:` key, or candidate-owned configuration as proof that GitHub deployment protection is active.
- Do not use mutable action tags in committed workflows.
- Do not publish an artifact that was not tested in its published form, and never use broad operations such as `docker push --all-tags` when release channels have different promotion rights.
- Do not assume `GITHUB_TOKEN`-generated events trigger downstream workflows.
- Do not use a pip cache in a repository with no matching dependency file.
- Do not hide required release jobs behind unreachable event conditions.

The assessed revision MUST NOT supply the authoritative verifier, claim catalog, release-environment allowlist, or acceptance workflow used to approve itself; candidate-local validation is diagnostic and final acceptance requires immutable external authority coordinates.
