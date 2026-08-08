---
name: ci-cd-architect
description: Design, repair, and review secure, cost-aware local and hosted quality gates for Python, .NET, MCP, documentation, packages, and containers.
---

# CI/CD architect

Use this skill when a repository needs trustworthy feedback before merge, reproducible artifact release, or control over excessive hosted CI consumption during high-churn development.

## Workflow

1. Classify the repository archetype, release artifact, trust boundaries, and whether hosted-runner time is effectively finite.
2. Inventory existing commands, tests, package managers, workflow triggers, branch policy, secrets, environments, deployment boundaries, and expensive jobs.
3. Select the smallest set of trust profiles and execution policies that covers the actual risks without running expensive CI after every agent commit.
4. Keep local hooks fast and deterministic; use local/pre-push checks for iterative feedback and hosted CI for authoritative gates.
5. For high-churn or quota-constrained repositories, prefer on-demand development CI: manual branch runs plus automatic full assurance on the governed integration branch.
6. Pin every third-party action to a full commit SHA and maintain version comments separately from trust.
7. Give each job least privilege, a timeout, explicit concurrency behavior, and bounded artifact retention.
8. Separate validation from privileged publication.
9. Build, smoke-test, and publish the same immutable artifact or digest.
10. Verify acceptance and release identity from the exact executed revision, not from unrelated trigger context or a workflow that never received a runner.
11. Render and parse templates, run the repository quality gate, inspect final workflow permissions and triggers, and prove both fast and full execution paths where on-demand CI is used.

Read `STANDARD.md`, then choose profiles using `references/template-selection.md`. Use `references/on-demand-ci.md` when agentic commit volume or provider quotas make automatic PR CI wasteful. Use `references/local-quality-gates.md`, `action-sha-maintenance.md`, and `failure-patterns.md` for implementation details.

For GitHub Actions trust-policy checks, run `tools/check_github_actions_policy.py` from a trusted immutable checkout and pass the candidate repository root as its argument. For workflows marked `# ai-skills-execution-policy: on-demand`, additionally run `tools/check_ci_execution_policy.py`. Trust policy governs permissions and secrets; execution policy governs when hosted jobs are allowed to start. Neither replaces the other.

A pull request must not provide the authoritative copy of the auditor that approves the same pull request. A repository-local mirror may support offline diagnostics only when CI compares it byte-for-byte with the pinned trusted source before treating its result as evidence.

## Cost-aware CI operating rule

When expensive workflows consume material hosted-runner quota during branch iteration:

- do not automatically run the full matrix, container build, full security scan, cross-platform artifact smoke, or end-to-end suite on every PR synchronization or agent push;
- expose `workflow_dispatch` for branch validation;
- use a cheap default manual path and a boolean `full` input when one workflow contains both fast and expensive jobs;
- allow automatic push only to explicit integration branches such as `main` or `master` for workflows governed by the on-demand execution policy;
- set `concurrency.cancel-in-progress: true`;
- keep cheap administrative automations and intentional release/scheduled workflows separate rather than disabling everything mechanically;
- require the complete acceptance gate on the exact final SHA before claiming readiness.

If GitHub creates a failed job with no assigned runner, no executed steps, and no command logs, classify it as infrastructure/provider failure. It is not evidence that the code failed and it is never evidence that the code passed. Repeatedly rerunning expensive jobs under an exhausted quota is not a repair strategy.

## Adoption and migration evidence

Before claiming that this skill has been adopted or a migration is complete:

1. Read the repository-root `contracts/adoption-assessment.yaml.template`, `contracts/rule-catalog.yaml`, compatibility matrix, and the selected skill manifest.
2. Create one assessment bound to the exact SHA and classify every stable rule as applicable, not applicable, or deferred with an owned waiver.
3. Bind each passed claim to a machine result file and passed test-case identity; a green job, badge, screenshot, queued job, or hand-written `passed` value is not evidence.
4. Use `verification_mode: provider-backed` only with the currently supported GitHub.com and GitHub Actions verifier. Other CI providers remain structural attestations until a reviewed adapter exists and cannot satisfy an approval gate.
5. Run `python contracts/validate_adoption.py <assessment> --require-approval` with read-only provider credentials before approval.
6. Require an independent review bound to the exact SHA. The reviewer must not be the PR author, a commit author or committer, or an actor that produced the referenced evidence.

Generated templates and examples are architecture seeds, not production acceptance. Apply the relevant CI/CD trust and execution policies, verify the exact deployment artifact, record rollback and residual risk, and retain provider evidence long enough for the stated decision lifetime.

## Constraints

- Do not grant write permissions to untrusted pull-request code.
- Do not use mutable action tags in committed workflows.
- Do not publish an artifact that was not tested in its published form.
- Do not assume `GITHUB_TOKEN`-generated events trigger downstream workflows.
- Do not use a pip cache in a repository with no matching dependency file.
- Do not hide required release jobs behind unreachable event conditions.
- Do not require expensive automatic PR workflows by habit when the repository intentionally uses the governed on-demand policy.
- Do not treat provider quota failure, an unassigned runner, or a job with zero executed steps as a successful acceptance gate.

The assessed revision MUST NOT supply the authoritative verifier, claim catalog, or acceptance workflow used to approve itself; candidate-local validation is diagnostic and final acceptance requires immutable external authority coordinates.
