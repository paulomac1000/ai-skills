---
description: Normative CI/CD rules for secure, reproducible, and observable quality gates and releases.
doc_id: reference.ci-cd-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Render every bundled template, parse it as YAML, run `python scripts/ci.py`, execute the trusted workflow-policy auditor against a candidate tree, and review permissions and release identity manually.
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
- Every job has a positive numeric `timeout-minutes` and explicit concurrency semantics where overlapping runs are harmful.
- Shell scripts use strict mode when failure propagation matters.
- Cache keys include every file that changes dependency resolution, including central .NET package and build props.
- Generated artifacts have explicit names, retention, and failure behavior.
- Pull-request workflows do not expose privileged secrets to untrusted code.
- Reusable templates parameterize the default branch, runtime version, install command, test command, and relevant paths.
- GitHub-hosted runners use a concrete image label such as `ubuntu-24.04`; moving `*-latest` labels are not accepted as reproducible execution identities. A `${{ matrix.os }}` runner is accepted only when every generated matrix value is a concrete literal runner and no expression or moving label can enter the axis.

## Workflow policy profiles

The trusted auditor evaluates one explicit profile. A workflow declares it in a leading comment or in the repository-owned `.github/workflow-policy.yaml` map:

```yaml
# ai-skills-policy-profile: pull-request
```

```yaml
schema_version: 1
workflows:
  .github/workflows/ci.yml: trusted-ci
```

A path declaration and an inline marker must agree. Unknown profiles, missing governed paths, malformed configuration, duplicate YAML keys, and paths outside `.github/workflows` fail closed.

The supported profiles are:

- `pull-request`: untrusted repository code, no write permissions, no repository secrets, and only the minimum read scopes;
- `trusted-ci`: trusted or mixed-event validation with top-level read-only permissions; job-level `checks: write` or `security-events: write` is allowed only for bounded reporting, never artifact or source publication;
- `protected-release`: no pull-request event, top-level read-only permissions, and narrowly scoped job-level write permissions only for protected publication.

A protected-release job with write permissions names a protected environment and depends on a prior validation or artifact-production job. Supported release write scopes are limited to the capabilities actually needed for contents, packages, OIDC, attestations, or security reporting. A trusted-CI reporting step that writes checks or SARIF uses an event and fork guard appropriate to the provider. The auditor rejects unrecognized write scopes and top-level write permissions. Local reusable workflows remain inside `.github/workflows`; external reusable workflows and actions use full immutable SHAs. Pull-request workflows never inherit secrets through reusable workflow calls.

## Python quality

A production Python gate includes, when applicable: dependency installation from the repository source of truth, Ruff lint and format checks, type checking, Bandit or equivalent security checks, unit tests, coverage reports, integration tests, and test artifacts. Missing stubs and exclusions are configured in project files, not hidden in CI command lines.

## .NET quality

A production .NET gate includes restore, `dotnet format --verify-no-changes`, analyzer-enabled release build, tests with TRX and XPlat coverage, coverage report generation, and uploaded test artifacts. Package publication is a separate protected workflow or job and uses a version derived from the validated tag.

## MCP-specific assurance

MCP repositories additionally test public tool registration, schema exposure, representative client invocation, protocol error shape, cancellation, and the built server artifact. Tool-count assertions are useful only when the expected count is intentionally controlled; capability or contract assertions are preferred when registration is dynamic.

## Documentation and security

Documentation changes trigger validation when either governed files, the validator, its governance file, or the workflow itself changes. Pull-request security scans are diff-aware where supported. Scheduled scans cover the full repository and upload SARIF only when a report exists.

A workflow-policy result is authoritative only when the auditor comes from a trusted immutable revision outside the assessed pull-request tree. The candidate may contain an offline mirror, but CI must compare that mirror with the trusted source and execute the trusted source against the candidate workflows. The bundled `tools/check_github_actions_policy.py` fails closed on malformed or duplicate-key YAML, symlinked or oversized workflow input, mutable action and Docker references, permissions inconsistent with the selected profile, unconstrained runner expressions, missing timeouts and concurrency, unsafe checkout credentials, incomplete artifact policy, and pull-request secret access.

The canonical consumption path is a protected reusable workflow from a separately governed verifier repository, pinned by full commit SHA. `templates/trusted-workflow-audit.yml.template` checks out the caller revision and an independently pinned verifier into separate directories, installs the verifier's hashed dependency graph, and executes only the trusted auditor against the candidate workflows. Where that distribution channel is unavailable, a signed wheel or OCI verifier pinned by digest may be used. `curl main | python`, a mutable branch reference, or the assessed revision's own verifier cannot serve as acceptance authority.

## Release identity and artifact promotion

A protected container release uses two trust stages:

1. a read-only validation job checks out the selected existing tag or full SHA, proves it is reachable from the trusted default branch, captures the full source SHA, runs validation, builds once, smoke-tests that exact image, exports it as an OCI or Docker archive, and records checksums and metadata;
2. a protected publish job does not check out or execute source code. It downloads the closed archive from the prior job, verifies checksums, source revision and image metadata, loads the tested image, applies an immutable `sha-<full-40-character-sha>` tag plus explicitly allowed release aliases, and pushes only those named tags.

A selected tag resolves to the captured SHA. Manual dispatch never treats the dispatch branch's `github.ref` or `github.sha` as release identity when a separate release ref was selected. Arbitrary branch preview builds remain unprivileged; a job with registry write permission treats their exported image only as bounded data and never runs it.

`docker push --all-tags` is forbidden because unrelated local tags may be promoted accidentally. The workflow captures the registry digest after push and attests that digest when the provider and repository plan support it. A short SHA may be a human alias but is not the durable source identity.

## Local quality gates

Pre-commit runs only deterministic, fast, secret-free checks. Pre-push may run the bounded repository parity runner. Network, deployment, integration environments, and privileged publication remain in CI. See [Local quality gates](references/local-quality-gates.md).

## Verification

Render every workflow with representative values, parse the YAML, inspect each job and `uses` reference, and run the workflow-policy auditor under the declared profile. Every bundled workflow template must pass its own expected profile after rendering. Run the auditor from a trusted immutable checkout against the candidate repository root; do not execute the candidate's copy as approval authority. For releases, perform a dry run or disposable-registry test proving that the archived smoke-tested image and pushed digest represent the same build and that the publish job never executes candidate source.
