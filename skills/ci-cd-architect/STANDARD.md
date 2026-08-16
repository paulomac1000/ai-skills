---
afds_schema_version: 2
description: Normative CI/CD rules for secure, reproducible, cost-aware, and observable quality gates and releases.
doc_id: reference.ci-cd-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Render every bundled template, parse it as YAML, run `python scripts/ci.py`, execute the trusted workflow-policy auditor and the on-demand execution-policy validator against a candidate tree, and review permissions, trigger policy, provider controls, authority binding, evidence identity, and release identity manually.
---

# CI/CD standard

## Purpose

Define stable delivery invariants for Python, .NET, MCP, documentation, package, and container repositories. Concrete workflow profiles are composable; no repository is forced into one monolithic pipeline. Hosted-runner time is a finite engineering resource when the provider or account applies quotas, so execution frequency is governed separately from workflow trust and permissions.

## Pipeline layers

1. **Local edit gate:** formatting, syntax, and focused checks with no network or secrets.
2. **Local push gate:** bounded parity runner for tests likely to fail remotely.
3. **Development CI:** either continuous pull-request CI or cost-aware on-demand CI, chosen explicitly from repository constraints.
4. **Integration gate:** the complete required gate runs on the exact candidate before acceptance and automatically when the governed integration branch is updated when that workflow owns integration assurance.
5. **Protected release:** exact-revision validation followed by publication through an environment or trusted tag path.
6. **Scheduled assurance:** full security and dependency scans that are intentionally too expensive for every edit.

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
- A workflow run is evidence only when a runner actually executed the required steps. A created job with no assigned runner, `steps: []`, or no command output is infrastructure/provider failure, not a passed quality gate.

## Workflow policy profiles

The trusted auditor evaluates one explicit trust profile. A workflow declares it in a leading comment or in the repository-owned `.github/workflow-policy.yaml` map:

```yaml
# ai-skills-policy-profile: pull-request
```

```yaml
schema_version: 1
workflows:
  .github/workflows/ci.yml: trusted-ci
```

A path declaration and an inline marker must agree. Unknown profiles, missing governed paths, malformed configuration, duplicate YAML keys, and paths outside `.github/workflows` fail closed.

The supported trust profiles are:

- `pull-request`: untrusted repository code, no write permissions, no repository secrets, and only the minimum read scopes;
- `trusted-ci`: trusted or mixed-event validation with top-level read-only permissions; job-level `checks: write` or `security-events: write` is allowed only for bounded reporting, never artifact or source publication;
- `protected-release`: no pull-request event, top-level read-only permissions, and narrowly scoped job-level write permissions only for protected publication.

A protected-release job with write permissions names a protected environment and depends on a prior validation or artifact-production job. Supported release write scopes are limited to the capabilities actually needed for contents, packages, OIDC, attestations, or security reporting. A trusted-CI reporting step that writes checks or SARIF uses an event and fork guard appropriate to the provider. The auditor rejects unrecognized write scopes and top-level write permissions. Local reusable workflows remain inside `.github/workflows`; external reusable workflows and actions use full immutable SHAs. Pull-request workflows never inherit secrets through reusable workflow calls.

## Execution policy and hosted-runner budget

Trust policy and execution policy are independent dimensions. A repository with high agent commit volume or finite hosted-runner minutes SHOULD use the on-demand execution policy for expensive development workflows rather than weakening their security profile.

Declare it separately:

```yaml
# ai-skills-policy-profile: trusted-ci
# ai-skills-execution-policy: on-demand
```

An `on-demand` workflow MUST expose `workflow_dispatch`. It MAY also run automatically on literal governed integration branches such as `main` or `master`. It MUST NOT auto-run on pull-request events, feature-branch pushes, tag pushes, schedules, or workflow chaining. When automatic `push` is enabled, it MUST be branch-restricted. It MUST set `concurrency.cancel-in-progress: true` so newer work replaces stale queued or running work.

For a workflow that contains both cheap and expensive checks, the recommended contract is:

- a `validate` job is the default manual path;
- `workflow_dispatch.inputs.full` is a boolean with `default: false`;
- expensive jobs run when `inputs.full == true`;
- the same expensive jobs run automatically on the governed integration-branch push;
- branch work does not auto-trigger the workflow merely because an agent creates or updates a pull request.

The canonical full-job guard is:

```yaml
if: github.event_name == 'push' || inputs.full == true
```

Manual-only workflows are appropriate for isolated expensive concerns such as cross-platform runtime isolation, full Semgrep scans, container builds, generated artifact smoke tests, or end-to-end environments. Cheap administrative automation such as bounded PR labeling MAY remain event-driven. Release/tag workflows and intentionally scheduled assurance remain separately governed and MUST NOT be disabled mechanically merely to reduce development CI usage.

A cost-saving configuration MUST NOT become an evidence bypass. Before a PR or release is accepted, every quality gate required by repository policy MUST have genuinely executed on the exact accepted SHA. A branch change invalidates prior exact-SHA acceptance evidence. If provider quota exhaustion prevents runner assignment, record an infrastructure failure and wait for capacity, purchase capacity, or use a separately governed runner; do not reinterpret the non-executed run as success.

Use `templates/on-demand-ci.yaml.template` as the seed and validate marked workflows with:

```bash
python skills/ci-cd-architect/tools/check_ci_execution_policy.py .
```

The validator defaults automatic push allowlisting to `main` and `master`; repositories with another integration branch pass one or more `--integration-branch` values. See [On-demand CI](references/on-demand-ci.md).

## Python quality

A production Python full gate includes, when applicable: dependency installation from the repository source of truth, Ruff lint and format checks, type checking, Bandit or equivalent security checks, unit tests, coverage reports, integration tests, and test artifacts. Missing stubs and exclusions are configured in project files, not hidden in CI command lines. Under on-demand execution, a fast manual job may run a strict subset, but it does not replace the full gate required for acceptance.

## .NET quality

A production .NET full gate includes restore, `dotnet format --verify-no-changes`, analyzer-enabled release build, tests with TRX and XPlat coverage, coverage report generation, and uploaded test artifacts. Package publication is a separate protected workflow or job and uses a version derived from the validated tag. Under on-demand execution, expensive restore/build/test matrices may be manual during branch iteration but remain mandatory when the repository acceptance policy requires them.

## MCP-specific assurance

MCP repositories additionally test public tool registration, schema exposure, representative client invocation, protocol error shape, cancellation, and the built server artifact. Tool-count assertions are useful only when the expected count is intentionally controlled; capability or contract assertions are preferred when registration is dynamic.

## Documentation and security

In continuous pull-request CI, documentation changes trigger validation when either governed files, the validator, its governance file, or the workflow itself changes. Under on-demand execution, equivalent validation runs manually during branch work and as part of the integration/full acceptance gate. Pull-request security scans are diff-aware where continuous PR scanning is intentionally enabled. Scheduled scans cover the full repository and upload SARIF only when a report exists.

Provider-backed approval requires two independent trust dimensions: **trusted executable provenance** and **trusted orchestration authority**. Executing immutable verifier bytes is necessary but not sufficient when the candidate still chooses the verifier SHA, arguments, provider credentials, claim catalog, required-check identity, or execution timing. Candidate-owned orchestration that checks out an immutable verifier is structural/diagnostic evidence only.

A workflow-policy result is authoritative only when the auditor comes from a trusted immutable revision outside the assessed pull-request tree and the acceptance orchestration is independently controlled outside that candidate. The candidate may contain an offline mirror, but CI must compare that mirror with the trusted source and execute the trusted source against the candidate workflows. The bundled `tools/check_github_actions_policy.py` fails closed on malformed or duplicate-key YAML, symlinked or oversized workflow input, mutable action and Docker references, permissions inconsistent with the selected profile, unconstrained runner expressions, missing timeouts and concurrency, unsafe checkout credentials, incomplete artifact policy, and pull-request secret access.

The candidate's `trusted-executable-sources.lock.yaml` is a declaration of expected authority, not a root of trust. Provider-backed orchestration supplies the expected authority repository and full SHA independently and verifies equality with `contracts/validate_external_trust_lock.py` before accepting candidate evidence. `tools/generate_trusted_executable_sources.py` produces digest entries from a verified exact authority checkout; hand-computed hashes from mutable branch bytes are not an acceptable bootstrap.

The canonical GitHub.com provider-backed path starts with `.github/workflows/consumer-acceptance-dispatch.yml` in the separately governed authority repository. The dispatcher runs from a provider-protected authority ref and calls the local materialized `.github/workflows/consumer-acceptance.yml` from the same authority commit. The reusable workflow verifies caller repository/SHA equality with its provider-reported workflow repository/SHA and the protected-ref signal, then checks out the candidate exact SHA with an authority-owned read token. A direct cross-repository invocation from candidate code fails the authority-orchestration gate and cannot become provider-backed evidence. The authority flow then binds candidate-lock authority to the externally established authority, performs provider-control preflight, and validates provider evidence plus independent review. `templates/trusted-workflow-audit.yml.template` remains an architecture seed for organizations that operate a distinct verifier repository; it is not itself callable through `workflow_call`.

Repository YAML cannot prove provider-side branch or environment protection. Run `tools/check_github_provider_controls.py` from the authority checkout before final adoption. `MISCONFIGURED` means the provider control was observable and insufficient. `UNVERIFIABLE` means credentials, visibility, plan support, or provider response did not allow the control to be established. Both block approval, but the diagnoses MUST remain distinct. A repository file MUST NOT simulate branch protection, environment reviewers, deployment branch policy, or authority-secret configuration. Authority policy may additionally name a required status-check identity; the candidate does not select that identity for its own approval.

The authority dispatcher uses a separately administered read token restricted to approved candidate repositories and the provider read surfaces needed for candidate contents, Actions evidence, pull-request/review evidence, environments, and branch-protection inspection. Missing permission or provider-plan visibility is `UNVERIFIABLE`, not evidence that a control exists or does not exist.

Where the authority-owned workflow distribution channel is unavailable, a signed wheel or OCI verifier pinned by digest may be used only with an independently governed orchestration authority that provides equivalent candidate-repository/SHA, authority-SHA, provider-control, and review binding. `curl main | python`, a mutable branch reference, or the assessed revision's own verifier cannot serve as acceptance authority.

## Release identity and artifact promotion

A protected container release uses two trust stages:

1. a read-only validation job resolves the selected existing tag or full SHA, proves it is reachable from the trusted default branch, captures the full source SHA, builds once without production authority, smoke-tests that exact build, pushes it only to an isolated quarantine registry, resolves its immutable registry digest, and smoke-tests the exact quarantined digest;
2. a protected publish job does not check out or execute candidate source and does not load or rebuild the candidate image. It authenticates only to the bounded source registry and production registry, then promotes the already-tested exact digest registry-to-registry under the allowed immutable and release tags.

The publisher verifies that every promoted production tag resolves to the expected digest before attestation. A selected tag resolves to the captured SHA. Manual dispatch never treats the dispatch branch's unrelated context as release identity when a separate release ref was selected. Arbitrary branch preview builds remain unprivileged.

`docker push --all-tags` is forbidden because unrelated local tags may be promoted accidentally. `docker image load` or candidate execution in the privileged publisher is forbidden because it reintroduces candidate-controlled execution after the trust boundary. A short SHA may be a human alias but is not the durable source identity.

## Local quality gates

Pre-commit runs only deterministic, fast, secret-free checks. Pre-push may run the bounded repository parity runner. Network, deployment, integration environments, and privileged publication remain in CI. In an on-demand repository, local and pre-push gates carry more of the iterative feedback load but never manufacture hosted evidence. See [Local quality gates](references/local-quality-gates.md).

## Verification

Render every workflow with representative values, parse the YAML, inspect each job and `uses` reference, and run the workflow-policy auditor under the declared trust profile. For workflows carrying `ai-skills-execution-policy: on-demand`, also run `check_ci_execution_policy.py`, dispatch the fast and full paths, prove a feature-branch push and PR synchronization do not start the workflow, and prove an integration-branch push runs the full path. Every bundled workflow template must pass its declared policy after rendering.

For provider-backed adoption, dispatch the authority-owned acceptance workflow from a protected authority ref, prove caller repository/SHA and reusable workflow repository/SHA are identical authority coordinates, compare the candidate trust declaration with that authority, run provider-control preflight, correlate provider evidence to the exact candidate repository/SHA, and require independent review. Classify incomplete migrations as `structurally-conformant`, `provider-preflight-blocked`, `provider-validation-pending`, or `independent-review-pending`; use `adopted` only after all provider-backed gates pass. Use `tools/classify_github_run_evidence.py` when a run result may be a zero-step/no-runner provider failure.

For releases, perform a disposable-registry test proving that the quarantined smoke-tested digest and promoted production digest are identical and that the protected publisher never checks out, rebuilds, loads, or executes candidate source.
