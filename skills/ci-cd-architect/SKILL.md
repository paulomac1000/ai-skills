---
name: ci-cd-architect
description: Design, repair, and review secure, cost-aware local and hosted quality gates for Python, .NET, MCP, documentation, packages, and containers.
---

# CI/CD architect

Use this skill when a repository needs trustworthy feedback before merge, reproducible artifact release, or control over excessive hosted CI consumption during high-churn development.

## Workflow

1. Classify the repository archetype, release artifact, trust boundaries, and whether hosted-runner time is effectively finite. Classify the target evidence plane as either structural/diagnostic or provider-backed; do not blur the two.
2. Inventory existing commands, tests, package managers, workflow triggers, branch policy, secrets, environments, deployment boundaries, provider-administration dependencies, and expensive jobs.
3. Read `references/provider-trust-bootstrap.md` before designing provider-backed acceptance. Treat trusted executable provenance and trusted orchestration authority as two separate requirements.
4. Select the smallest set of trust profiles and execution policies that covers the actual risks without running expensive CI after every agent commit.
5. Keep local hooks fast and deterministic; use local/pre-push checks for iterative feedback and hosted CI for authoritative gates.
6. For high-churn or quota-constrained repositories, prefer on-demand development CI: manual branch runs plus automatic full assurance on the governed integration branch.
7. Pin every third-party action to a full commit SHA and maintain version comments separately from trust.
8. Give each job least privilege, a timeout, explicit concurrency behavior, and bounded artifact retention.
9. Separate validation from privileged publication.
10. Build, smoke-test, and publish the same immutable artifact or digest.
11. Verify acceptance and release identity from the exact executed revision, not from unrelated trigger context or a workflow that never received a runner.
12. Render and parse templates, run the repository quality gate, inspect final workflow permissions and triggers, and prove both fast and full execution paths where on-demand CI is used.

Read `STANDARD.md`, then choose profiles using `references/template-selection.md`. Use `references/on-demand-ci.md` when agentic commit volume or provider quotas make automatic PR CI wasteful. Use `references/local-quality-gates.md`, `action-sha-maintenance.md`, and `failure-patterns.md` for implementation details.

For GitHub Actions trust-policy checks, run `tools/check_github_actions_policy.py` from a trusted immutable checkout and pass the candidate repository root as its argument. For workflows marked `# ai-skills-execution-policy: on-demand`, additionally run `tools/check_ci_execution_policy.py`. Trust policy governs permissions and secrets; execution policy governs when hosted jobs are allowed to start. Neither replaces provider-control verification.

A pull request must not provide the authoritative copy of the auditor or orchestration that approves the same pull request. A candidate-owned workflow may execute an immutable external verifier for structural diagnostics, but candidate control over the authority SHA, arguments, credentials, required check, or timing means that result is not provider-backed acceptance.

For provider-backed GitHub.com acceptance, start `.github/workflows/consumer-acceptance-dispatch.yml` in the **authority repository** from a provider-protected ref. The dispatcher calls the materialized local reusable `.github/workflows/consumer-acceptance.yml` from the same authority commit. The reusable workflow rejects cross-repository candidate-owned callers, requires caller repository/SHA equality with its provider-reported workflow repository/SHA, checks the protected-ref signal, checks out the exact candidate SHA with an authority-owned read token, requires candidate-lock equality with that external authority, runs provider-control preflight, and validates exact-SHA provider evidence plus independent review. A candidate repository does not invoke this reusable workflow as its own provider-backed gate. `templates/trusted-workflow-audit.yml.template` remains an architecture seed for other authority deployments; a `.template` file is never itself a callable acceptance workflow.

Generate trusted executable locks from the immutable authority checkout with `tools/generate_trusted_executable_sources.py`. The candidate lock is only a declaration of expected authority; it cannot bootstrap its own trust. Provider-backed validation uses `contracts/validate_external_trust_lock.py` to compare it with authority coordinates established by the authority-owned workflow.

## Cost-aware CI operating rule

When expensive workflows consume material hosted-runner quota during branch iteration:

- do not automatically run the full matrix, container build, full security scan, cross-platform artifact smoke, or end-to-end suite on every PR synchronization or agent push;
- expose `workflow_dispatch` for branch validation;
- use a cheap default manual path and a boolean `full` input when one workflow contains both fast and expensive jobs;
- allow automatic push only to explicit integration branches such as `main` or `master` for workflows governed by the on-demand execution policy;
- set `concurrency.cancel-in-progress: true`;
- keep cheap administrative automations and intentional release/scheduled workflows separate rather than disabling everything mechanically;
- require the complete acceptance gate on the exact final SHA before claiming readiness.

If GitHub creates a failed job with no assigned runner, no executed steps, and no command logs, classify it as infrastructure/provider failure. It is not evidence that the code failed and it is never evidence that the code passed. Use `tools/classify_github_run_evidence.py` when the provider records are ambiguous. Repeatedly rerunning expensive jobs under an exhausted quota is not a repair strategy.

## Adoption and migration evidence

Before claiming that this skill has been adopted or a migration is complete:

1. Read the repository-root `contracts/adoption-assessment.yaml.template`, `contracts/rule-catalog.yaml`, canonical shared validator `contracts/validate_adoption.py`, compatibility matrix, selected skill manifest, and `references/provider-trust-bootstrap.md`.
2. Create one assessment bound to the exact SHA and classify every stable rule as applicable, not applicable, or deferred with an owned waiver.
3. Bind each passed claim to a machine result file and passed test-case identity; a green job, badge, screenshot, queued job, or hand-written `passed` value is not evidence.
4. Run `tools/check_github_provider_controls.py` from the trusted authority checkout. Static workflow YAML cannot prove that a branch is protected or an environment exists. `MISCONFIGURED` and `UNVERIFIABLE` both block final adoption, but they are different diagnoses.
5. Use `verification_mode: provider-backed` only with the currently supported GitHub.com and GitHub Actions verifier. Other CI providers remain structural attestations until a reviewed adapter exists and cannot satisfy an approval gate.
6. Configure the authority repository's `AI_SKILLS_CONSUMER_READ_TOKEN` with only the candidate repositories and read surfaces needed for candidate checkout, Actions evidence, pull-request/review evidence, environments, and branch-protection inspection. Dispatch `consumer-acceptance-dispatch.yml` from a protected authority ref for the exact candidate repository/SHA.
7. Require an independent review bound to the exact SHA. The reviewer must not be the PR author, a commit author or committer, or an actor that produced the referenced evidence.
8. Report one migration state: `structurally-conformant`, `provider-preflight-blocked`, `provider-validation-pending`, `independent-review-pending`, or `adopted`.

If repository changes are complete but provider administration is unavailable, do not simulate protection in YAML. Leave the repository fail closed, report `provider-preflight-blocked`, and provide an external-admin checklist with the exact authority ref/secret plus candidate branch/environment/check configuration that must be changed and reverified.

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
- Do not treat a candidate-owned trust lock, verifier checkout, or workflow invocation as the root of provider-backed trust.
- Do not claim an environment or branch is protected solely because repository YAML names it.

The assessed revision MUST NOT supply the authoritative verifier, claim catalog, authority pin, provider credentials, required-check identity, or acceptance orchestration used to approve itself; candidate-local validation is diagnostic and final acceptance requires protected external orchestration plus provider-side evidence.
