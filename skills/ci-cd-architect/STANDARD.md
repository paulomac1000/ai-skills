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
  value: Render every bundled template, parse it as YAML, run `python scripts/ci.py`, execute the trusted workflow-policy auditor, execution-policy validator, and verification-integrity checks against a candidate tree, and review permissions, trigger policy, provider controls, authority binding, evidence identity, test-corpus completeness, execution integrity, state isolation, and release identity manually.
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
- An authoritative gate proves **selection integrity** and **execution integrity**. Its policy-defined corpus is exercised or explicitly accounted for; exact `required_subjects` remain expected when absent or missed by discovery. Test files are one specialization. Green assertions cannot override drift, cancellation, leaked work, or unhandled executable failure.
- Verdict-affecting dependencies come from repository-declared locks, manifests, tool-version files, immutable images, or an explicit deterministic bootstrap. Ambient host packages are not reproducible evidence merely because they happen to satisfy an invocation.
- Ordinary validation is read-only with respect to production-effective runtime state. Test fixtures, generated env/config, databases, caches, sockets, work directories, identities, and credentials use isolated run-owned state. A validation run that mutates the production-effective state it was meant to observe is invalid evidence even if its assertions pass.

Machine-readable verification-integrity semantics live in `references/verification-integrity.md` and compose into `contracts/verification-receipt.schema.json`; profiles do not redefine `PASS`.

## Dependency lock verification and refresh

Candidate verification consumes the committed lock without upstream re-resolution or mutation. Refresh is separate and reviewable; exact refresh requires digest-bound immutable upstream identity. See `references/verification-integrity.md#dependency-lock-operations`.

## Exact artifact evidence construction

An artifact digest is exact evidence only when its **construction semantics and coverage are exact**. Producers use the repository-level `contracts/artifact-evidence.schema.json` contract rather than treating a bare SHA-256 string as proof of how an artifact was covered.

For structured file-tree evidence, the v1 canonical profile is deliberately narrow:

- paths are relative POSIX paths normalized to Unicode NFC, with no absolute, empty, dot, parent, backslash, or NUL-bearing segments;
- entries are sorted by normalized UTF-8 path bytes;
- every structural field is length-prefixed and file entries use a domain-separated encoding, so path/content boundaries cannot collide with delimiter bytes in file contents;
- v1 covers regular-file path and content bytes only. Symlinks and other file types are non-exact under this profile. Permission/executable/mode metadata is not silently ignored when it is load-bearing; such a policy requires another explicit construction profile;
- file-count, byte-count, depth, and duration limits are policy-owned profile data. The byte count includes normalized UTF-8 path bytes plus file-content bytes, so path payload cannot bypass the bound. Hitting any required bound yields `partial` rather than an exact digest;
- an incomplete inventory or unsupported file type is `partial` or `unknown`, never exact.

The subject root, inventory completeness, profile revision, and bounds are established by trusted policy/collector authority. The v1 constructor intentionally accepts no candidate-defined exclusion list. A candidate cannot make evidence exact by omitting load-bearing files from its own subject definition.

Requested/admitted identity and observed identity remain separate. A fallback may observe exact artifact bytes and still prove that the requested version/source did not match, or leave that relationship unknown. `artifact_exact=true` proves only the bytes/structure covered by the named construction profile; it does not imply source, requested-package, runtime, or policy compatibility.

Construction profile identity is part of freshness. Material changes to encoding, normalization, metadata semantics, bounds, or policy revision create a different profile digest; old evidence is not silently comparable to the new profile. Runtime/source lineage and verification receipts consume the artifact evidence or its provenance reference rather than redefining artifact hashing.

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

Pytest warning policy distinguishes informational/deprecation warnings from warnings that encode an executable failure. `PytestUnhandledThreadExceptionWarning`, `PytestUnraisableExceptionWarning`, meaningful never-awaited coroutines, pending/destroyed tasks, and equivalent background failures are blocking. A repository MAY keep known dependency deprecations non-blocking through a narrow reviewed allowlist; it MUST NOT convert all warnings to success or hide the underlying exception trace. The same classification policy is used by the local and hosted entrypoints.

## .NET quality

A production .NET full gate includes restore, `dotnet format --verify-no-changes`, analyzer-enabled release build, tests with TRX and XPlat coverage, coverage report generation, and uploaded test artifacts. Package publication is a separate protected workflow or job and uses a version derived from the validated tag. Under on-demand execution, expensive restore/build/test matrices may be manual during branch iteration but remain mandatory when the repository acceptance policy requires them.

## MCP-specific assurance

MCP repositories additionally test public tool registration, schema exposure, representative client invocation, protocol error shape, cancellation, and the built server artifact. Tool-count assertions are useful only when the expected count is intentionally controlled; capability or contract assertions are preferred when registration is dynamic.

MCP candidate gates consume the same verification-integrity contract. A transport smoke whose selected tests later cancel, leak async work, or raise a background exception is non-green; MCP-specific acceptance must not duplicate or weaken that rule.

## Documentation and security

In continuous pull-request CI, documentation changes trigger validation when either governed files, the validator, its governance file, or the workflow itself changes. Under on-demand execution, equivalent validation runs manually during branch work and as part of the integration/full acceptance gate. Pull-request security scans are diff-aware where continuous PR scanning is intentionally enabled. Scheduled scans cover the full repository and upload SARIF only when a report exists.

Provider-backed approval requires two independent trust dimensions: **trusted executable provenance** and **trusted orchestration authority**. Executing immutable verifier bytes is necessary but not sufficient when the candidate still chooses the verifier SHA, arguments, provider credentials, claim catalog, required-check identity, or execution timing. Candidate-owned orchestration that checks out an immutable verifier is structural/diagnostic evidence only.

A workflow-policy result is authoritative only when the auditor comes from a trusted immutable revision outside the assessed pull-request tree and the acceptance orchestration is independently controlled outside that candidate. The candidate may contain an offline mirror, but CI must compare that mirror with the trusted source and execute the trusted source against the candidate workflows. The bundled `tools/check_github_actions_policy.py` fails closed on malformed or duplicate-key YAML, symlinked or oversized workflow input, mutable action and Docker references, permissions inconsistent with the selected profile, unconstrained runner expressions, missing timeouts and concurrency, unsafe checkout credentials, incomplete artifact policy, and pull-request secret access.

The candidate's `trusted-executable-sources.lock.yaml` is a declaration of expected authority, not a root of trust. Provider-backed orchestration supplies the expected authority repository and full SHA independently and verifies equality with `contracts/validate_external_trust_lock.py` before accepting candidate evidence. `tools/generate_trusted_executable_sources.py` produces digest entries from a verified exact authority checkout; hand-computed hashes from mutable branch bytes are not an acceptable bootstrap.

The canonical GitHub.com path starts with `.github/workflows/consumer-acceptance-dispatch.yml` in the authority repository on a protected ref. Its local reusable workflow compares caller `github.repository`/`github.sha` with `job.workflow_repository`/`job.workflow_sha`, verifies `github.ref_protected`, then binds the exact candidate SHA, candidate trust declaration, provider controls, and independent review. Direct candidate-owned cross-repository invocation is not provider-backed acceptance. See `references/provider-trust-bootstrap.md` for operational details.

Repository YAML cannot prove provider-side branch or environment protection. Run `tools/check_github_provider_controls.py` from the authority checkout before final adoption. `MISCONFIGURED` means the provider control was observable and insufficient. `UNVERIFIABLE` means credentials, visibility, plan support, or provider response did not allow the control to be established. Both block approval, but the diagnoses MUST remain distinct. A repository file MUST NOT simulate branch protection, environment reviewers, or deployment branch policy. Authority policy, not candidate input, selects any required status-check identity.

Where the authority workflow channel is unavailable, a signed wheel or OCI verifier pinned by digest may be used only with an independently governed orchestration authority that provides equivalent candidate-SHA, authority-SHA, provider-control, and review binding. `curl main | python`, a mutable branch reference, or the assessed revision's own verifier cannot serve as acceptance authority.

## Release identity and artifact promotion

A protected container release uses two trust stages:

1. a read-only validation job resolves the selected existing tag or full SHA, proves it is reachable from the trusted default branch, captures the full source SHA, builds once without production authority, smoke-tests that exact build, pushes it only to an isolated quarantine registry, resolves its immutable registry digest, and smoke-tests the exact quarantined digest;
2. a protected publish job does not check out or execute candidate source and does not load or rebuild the candidate image. It authenticates only to the bounded source registry and production registry, then promotes the already-tested exact digest registry-to-registry under the allowed immutable and release tags.

The publisher verifies that every promoted production tag resolves to the expected digest before attestation. A selected tag resolves to the captured SHA. Manual dispatch never treats the dispatch branch's unrelated context as release identity when a separate release ref was selected. Arbitrary branch preview builds remain unprivileged.

`docker push --all-tags` is forbidden. An authority-bearing publisher MUST NOT check out, build/package, load/import, or execute candidate content. The auditor rejects supported shell/action/container variants (including continuations and Compose) and fails closed on opaque reusable-workflow delegation; registry-native exact-digest promotion/inspection remains allowed. A short SHA is not durable source identity.

## Release deliverable closure

When policy declares release deliverables, source/tests/docs are insufficient: the manifest schema and closure receipt/helper bind required presence, packaged identity, and required smoke to one exact source revision, artifact digest/evidence identity, and manifest identity. Missing/unknown presence, identity mismatch, non-`PASS` smoke, or unresolved critical unexpected content blocks closure. V1 is bounded and secret-free, not an SBOM; drift is `STALE`, malformed evidence is `UNKNOWN`. Required closure must be `COMPLETE` before governed promotion and grants no publication, deployment, or runtime-acceptance authority.

## Deployment mutation authority and fencing

Where policy requires a DeploymentLease, bind exact principal/session, target/resource, artifact/source, action/arguments, policy and validity window. Schema version 2 also binds the conflicting mutation domain, authority-owned expected-current target state and fence. Immediately before dispatch, re-read authority and target state: a matching preflight is still non-dispatching until the one-shot lease is atomically consumed and that domain reserved.

Same-domain mutations serialize through provider CAS or a durable broker/generation fence. Immediately before dispatch, a brokered holder re-checks that its operation/lease still owns the current domain fence; handover invalidates stale holders. An unknown dispatch outcome retains the domain owner and blocks conflicting work or replay until authoritative reconciliation; an applied mutation advances the fence, and rollback conflicts with forward deployment in that domain. Runtime evidence may inform expected state but never grants deployment authority. See `contracts/deployment-lease.schema.json`, `contracts/deployment_lease.py`, and `contracts/audit-event.schema.json`.

## Artifact publication authority

When an autonomous publisher may place an already-proven artifact into a governed package, registry, release-asset, or distribution namespace, generic build/test, repository-write, deployment, or registry credentials are insufficient. Publication requires an authority-owned one-shot lease bound to the exact prepared artifact ref/digest, destination provider/namespace/package/version/tags or channels, bounded action, publication-policy/evidence identity, execution generation, and expiry. Immediately before reservation the publisher MUST re-read trusted lease authority, exact artifact evidence, destination state, mutable-channel state, and provider controls; artifact substitution, destination widening, stale evidence/policy, lost authority, unknown destination state, or an immutable same-version/different-artifact conflict fails closed.

The durable publication operation MUST be reserved before dispatch and reservation consumes the lease. An already-present same artifact may converge without another write only when current provider/policy explicitly admits that reconciliation and exact read-back proves the consumed operation's artifact. Timeout, connection loss, or provider conflict MUST reconcile that same operation against authoritative destination identity before any later dispatch can receive fresh authority. Mutable channel movement records before/after artifact identity. A successful result emits a bounded `artifact_publication` receipt with exact artifact, destination, lease/operation, policy, outcome, and evidence lineage; a later deployment may consume the published artifact identity but inherits no publication or rebuild authority. Immediately before dispatch, the protected publisher MUST bind the artifact it actually opened/read to the reserved exact artifact identity; a different ref or digest fails before provider mutation. The protected publisher still MUST NOT check out, rebuild, repack, load/import, or execute candidate source under publication credentials. See `references/artifact-publication-lease.md`.

## Local quality gates

Pre-commit runs only deterministic, fast, secret-free checks. Pre-push may run the bounded repository parity runner. Network, deployment, integration environments, and privileged publication remain in CI. In an on-demand repository, local and pre-push gates carry more of the iterative feedback load but never manufacture hosted evidence. See [Local quality gates](references/local-quality-gates.md).

Every merge-blocking hosted gate maps to one supported local entrypoint or an explicit `hosted_only` classification with rationale. The local entrypoint uses the same policy/configuration and pinned dependency source where feasible; unavailable provider-only checks remain visible as not executed. Use `tools/check_local_ci_parity.py` for the mapping, `tools/check_verification_bootstrap.py` for dependency provenance, `tools/check_test_corpus.py` for corpus completeness, `tools/check_execution_integrity.py` for hidden runtime failures, and `tools/verify_state_isolation.py` when validation can run near protected state.

## Verification

Render every workflow with representative values, parse the YAML, inspect each job and `uses` reference, and run the workflow-policy auditor under the declared trust profile. For workflows carrying `ai-skills-execution-policy: on-demand`, also run `check_ci_execution_policy.py`, dispatch the fast and full paths, prove a feature-branch push and PR synchronization do not start the workflow, and prove an integration-branch push runs the full path. Every bundled workflow template must pass its declared policy after rendering.

For every authoritative gate, prove corpus completeness (including exact required identities), clean execution, declared dependency bootstrap, and state isolation where applicable. Unknown completeness, missing required subjects, cancelled/pending work, unhandled failure, ambient dependency, or production-state mutation cannot report `PASS/verified`.

For provider-backed adoption, dispatch from a protected authority ref, prove caller and reusable-workflow repository/SHA equality, compare the candidate trust declaration with that authority, run provider-control preflight, correlate provider evidence to the exact candidate SHA, and require independent review. Classify incomplete migrations as `structurally-conformant`, `provider-preflight-blocked`, `provider-validation-pending`, or `independent-review-pending`; use `adopted` only after all provider-backed gates pass. Use `tools/classify_github_run_evidence.py` when a run result may be a zero-step/no-runner provider failure.

For releases, perform a disposable-registry test proving that the quarantined smoke-tested digest and promoted production digest are identical and that the protected publisher never checks out, rebuilds, loads, or executes candidate source.
