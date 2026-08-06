---
description: Normative CI/CD rules for secure, reproducible, and observable quality gates and releases.
doc_id: reference.ci-cd-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Render every bundled template, parse it as YAML, run `python scripts/ci.py`, execute the trusted workflow-policy auditor against a candidate tree, verify release-environment protections through trusted provider data, and review permissions and release identity manually.
---

# CI/CD standard

## Purpose

Define stable delivery invariants for Python, .NET, MCP, documentation, package, and container repositories. Concrete workflow profiles are composable; no repository is forced into one monolithic pipeline.

## Pipeline layers

1. **Local edit gate:** formatting, syntax, and focused checks with no network or secrets.
2. **Local push gate:** bounded parity runner for tests likely to fail remotely.
3. **Pull-request CI:** complete quality, test, security, documentation, and artifact checks using read-only defaults.
4. **Protected release:** exact-revision validation followed by publication through an environment or trusted tag path.
5. **Scheduled assurance:** full security and dependency scans that are too expensive for every edit.

## Universal workflow controls

- Third-party actions use full 40-character commit SHAs. Version comments are informational.
- `actions/checkout` sets `persist-credentials: false` unless a narrowly reviewed step must push.
- Top-level permissions default to `contents: read`; jobs elevate only capabilities they use.
- Write scopes are forbidden for pull-request code. A non-PR job may use only `packages`, `contents`, `id-token`, or `attestations` write access, and only when its exact literal environment name is present in a trusted allowlist supplied from outside the assessed repository. The literal must be `release` or a non-empty name ending in `-release`; that shape is a syntax restriction, not evidence that the environment is protected. Empty values, mappings, expressions, unlisted names, and candidate-local declarations never authorize write access. Repository-local reusable workflows are permitted through literal `./.github/workflows/*.yml` references; external or expression-derived workflow calls are not. Reusable-workflow caller jobs do not inherit release write scopes; the called workflow must own its protected publishing job.
- Every job has a positive numeric `timeout-minutes` and explicit concurrency semantics where overlapping runs are harmful.
- Shell scripts use strict mode when failure propagation matters.
- Cache keys include every file that changes dependency resolution, including central .NET package and build props.
- Generated artifacts have explicit names, retention, and failure behavior.
- Pull-request workflows do not expose privileged secrets to untrusted code.
- Reusable templates parameterize the default branch, runtime version, install command, test command, and relevant paths.

## Trusted release-environment authority

The candidate repository cannot prove that its own GitHub environment is protected. Before adding an environment name to the auditor allowlist, a trusted provider-side verifier or human reviewer must confirm that the environment exists and has the intended deployment protections, including independent approval where the repository policy requires it and branch or tag restrictions appropriate to the release path. A name alone, even `production-release`, is insufficient.

The allowlist belongs to the trusted acceptance workflow, deployment policy, or another authority outside the assessed revision. Unknown, unreadable, or unverifiable provider state fails closed by leaving the name out. The default auditor invocation has an empty allowlist and therefore rejects every job-level write scope.

After provider verification, pass each exact approved name explicitly:

```bash
python /trusted/ai-skills/skills/ci-cd-architect/tools/check_github_actions_policy.py \
  --protected-release-environment production-release \
  /candidate/repository
```

Do not read this allowlist from a file, variable, workflow output, or configuration owned by the candidate revision.

## Python quality

A production Python gate includes, when applicable: dependency installation from the repository source of truth, Ruff lint and format checks, type checking, Bandit or equivalent security checks, unit tests, coverage reports, integration tests, and test artifacts. Missing stubs and exclusions are configured in project files, not hidden in CI command lines.

## .NET quality

A production .NET gate includes restore, `dotnet format --verify-no-changes`, analyzer-enabled release build, tests with TRX and XPlat coverage, coverage report generation, and uploaded test artifacts. Package publication is a separate protected workflow or job and uses a version derived from the validated tag.

## MCP-specific assurance

MCP repositories additionally test public tool registration, schema exposure, representative client invocation, protocol error shape, cancellation, and the built server artifact. Tool-count assertions are useful only when the expected count is intentionally controlled; capability or contract assertions are preferred when registration is dynamic.

## Documentation and security

Documentation changes trigger validation when either governed files, the validator, its configuration, or the workflow itself changes. Pull-request security scans are diff-aware where supported. Scheduled scans cover the full repository and upload SARIF only when a report exists.

A workflow-policy result is authoritative only when the auditor comes from a trusted immutable revision outside the assessed pull-request tree. The candidate may contain an offline mirror, but CI must compare that mirror with the trusted source and execute the trusted source against the candidate workflows. The bundled `tools/check_github_actions_policy.py` fails closed on malformed or duplicate-key YAML, symlinked or oversized workflow input, mutable action and Docker references, broad permissions, dynamic runners, missing timeouts and concurrency, unsafe checkout credentials, incomplete artifact policy, pull-request secret access, and release write scopes lacking externally verified environment authority.

## Release identity and artifact promotion

A release workflow:

1. checks out the selected tag or commit;
2. captures its full SHA immediately;
3. runs repository-controlled validation and confirms `HEAD` did not change;
4. passes that exact SHA to the protected publish job;
5. derives human and immutable tags from validated outputs;
6. builds a local image once, smoke-tests that image, and pushes the same local image tags;
7. pushes only the explicitly derived tags, captures the registry digest, and attests that digest.

Manual dispatch is protected by an externally verified environment. A selected tag must resolve to the captured SHA. The dispatch branch's `github.ref` and `github.sha` are not used as release identity when a separate release ref was selected.

## Local quality gates

Pre-commit runs only deterministic, fast, secret-free checks. Pre-push may run the bounded repository parity runner. Network, deployment, integration environments, and privileged publication remain in CI. See [Local quality gates](references/local-quality-gates.md).

## Verification

Render every workflow with representative values, parse the YAML, inspect each job and `uses` reference, and run the associated project commands. Run the workflow-policy auditor from a trusted immutable checkout against the candidate repository root; do not execute the candidate's copy as approval authority. Resolve the approved release-environment allowlist from trusted provider state rather than candidate content, and prove that an unlisted environment cannot unlock write scopes. For releases, perform a dry run or disposable-registry test proving the smoke-tested image and pushed digest represent the same build.
