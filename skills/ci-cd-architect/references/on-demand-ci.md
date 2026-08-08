---
description: Cost-aware GitHub Actions execution for high-churn repositories without weakening final acceptance gates.
doc_id: reference.on-demand-ci
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Render the on-demand CI template, run the execution-policy validator, manually dispatch both fast and full modes, and verify that only the integration branch triggers automatically.
---

# On-demand CI

## Goal

Use on-demand CI when hosted runner minutes are finite or agentic development creates many intermediate commits. The objective is to stop paying for the same expensive matrix, container build, security scan, or integration suite on every branch update while preserving a real full gate before acceptance and after integration.

This is an execution policy, not a security profile. Keep the normal `pull-request`, `trusted-ci`, or other trust policy for permissions and secrets. Mark cost-controlled workflows separately:

```yaml
# ai-skills-policy-profile: trusted-ci
# ai-skills-execution-policy: on-demand
```

## Required trigger model

An on-demand development workflow:

- MUST expose `workflow_dispatch`;
- MAY run automatically on explicitly allowed integration branches such as `main` or `master`;
- MUST NOT run automatically on `pull_request`, `pull_request_target`, feature-branch pushes, tag pushes, schedules, or workflow chaining;
- MUST set `concurrency.cancel-in-progress: true` so a newer run replaces stale work;
- SHOULD keep the default manual run cheap and expose a boolean `full` input when one workflow contains both fast and expensive jobs;
- MUST run the complete gate on an automatic integration-branch push when that workflow is responsible for integration assurance.

A repository may use a manual-only workflow for an isolated expensive concern such as Semgrep, cross-platform runtime isolation, a Docker build, or documentation validation. Scheduled assurance remains a separate workflow and must be intentionally budgeted rather than hidden inside the on-demand workflow.

## Manual-dispatch bootstrap

GitHub only accepts `workflow_dispatch` for a workflow file that exists on the repository's default branch. After that definition exists there, the Actions UI, CLI, or API can dispatch it for a selected ref, including a candidate branch.

This matters during migration. If a workflow is being introduced for the first time, or the default-branch copy does not yet declare `workflow_dispatch`, the candidate branch cannot prove its new manual trigger by dispatching that candidate-only definition. Validate the workflow structurally and with repository-owned tests, merge the trigger change through the repository's existing trusted acceptance path, then prove manual dispatch on the first subsequent candidate. Do not add a privileged temporary workflow solely to work around this GitHub bootstrap rule.

When converting an existing workflow that already has `workflow_dispatch` on the default branch, manual candidate-ref validation can be used immediately.

## Recommended agent loop

1. Run formatting, syntax, focused tests, and repository-owned local checks without GitHub Actions.
2. During implementation, do not trigger hosted CI after every agent commit.
3. When remote validation is useful and the workflow is dispatchable from the default branch, dispatch the fast gate with the default `full=false`.
4. Near completion, dispatch `full=true` once on the candidate branch and record the exact run SHA.
5. If the branch changes after that run, the prior run is stale evidence; rerun the required gate on the new exact SHA.
6. Merge only under the repository's acceptance policy. A push to `main` or `master` runs the full integration gate automatically.
7. Keep release and publication workflows separately governed; cost control never authorizes skipping protected release validation.

Typical commands are:

```bash
gh workflow run ci.yml --ref my-branch
gh workflow run ci.yml --ref my-branch -f full=true
```

The manual workflow run is evidence only for the immutable SHA actually executed. A branch name in a command or screenshot is not sufficient by itself.

## What remains automatic

Do not mechanically disable every workflow. Cheap administrative automation may remain event-driven when its cost is negligible and it does not duplicate the full test gate. Examples include label assignment or tiny metadata checks. Release/tag workflows may remain event-driven when they are part of the governed release contract. Scheduled security assurance may remain scheduled if its cadence is intentional and affordable.

The expensive development workflows are the main target: broad test matrices, Docker builds, generated artifact smoke tests, end-to-end environments, cross-platform jobs, Semgrep/full security scans, and integration suites.

## Diagnosing exhausted hosted-runner budget

A workflow record is not proof that code executed. If GitHub creates a failed job but no runner is assigned, no steps execute, and logs contain no command output, classify the result as infrastructure/provider failure until proven otherwise. Signals such as an empty runner identity, `steps: []`, or a failure within seconds across unrelated workflows are useful diagnostics for account or runner-capacity problems, including exhausted billed minutes.

Do not convert such a run into green evidence and do not repeatedly rerun expensive workflows hoping that the code will fix an infrastructure quota. Check billing/usage or runner availability, preserve local evidence separately, and run the hosted acceptance gate when capacity returns.

Plan-specific minute allocations and billing rules are intentionally not hard-coded into this standard because provider limits change.

## Migration procedure

For a repository that currently runs expensive CI on every PR or branch push:

1. Inventory every workflow trigger and approximate which jobs are expensive.
2. Keep cheap administrative and deliberately scheduled/release workflows separate.
3. Confirm whether each target workflow already has a dispatchable definition on the default branch; record workflows that require one-time bootstrap through the existing acceptance path.
4. Convert expensive development workflows to `workflow_dispatch`; add restricted `push.branches` only for integration branches that require automatic assurance.
5. Where useful, split one workflow into `validate` and `full` jobs. `validate` is the cheap default manual path. Gate `full` with:

```yaml
if: github.event_name == 'push' || inputs.full == true
```

6. Add `# ai-skills-execution-policy: on-demand`.
7. Run `tools/check_ci_execution_policy.py` against the migrated workflow or repository.
8. When GitHub's default-branch dispatch precondition is satisfied, manually prove both fast and full dispatch paths and verify that a feature-branch push or PR synchronization does not start the workflow.
9. Update required-check/branch-protection settings. Do not leave a required PR check pointing at a workflow that is intentionally no longer triggered on pull requests.

## Validation command

Audit every marked workflow in a repository:

```bash
python skills/ci-cd-architect/tools/check_ci_execution_policy.py .
```

Audit one workflow and require the marker:

```bash
python skills/ci-cd-architect/tools/check_ci_execution_policy.py . \
  --workflow .github/workflows/ci.yml
```

For a repository whose integration branch is not `main` or `master`, declare it explicitly:

```bash
python skills/ci-cd-architect/tools/check_ci_execution_policy.py . \
  --integration-branch trunk
```

The execution-policy validator complements, rather than replaces, `check_github_actions_policy.py`. Run both when the workflow is governed by both trust and cost policies.
