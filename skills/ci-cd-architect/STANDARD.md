---
description: Normative rules for secure, reproducible, observable CI/CD pipelines.
doc_id: reference.ci-cd-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Render applicable templates, validate workflow syntax, and run the target repository's local CI command.
---

# CI/CD standard

## Delivery model

A pipeline makes the path from source revision to validation, artifact, publication, deployment, and recovery traceable.

- Every stage refers to the same source revision or an immutable artifact identity.
- Triggers cover events and paths that can affect the result without creating unreachable jobs.
- Obsolete validation runs are cancelled where safe.
- Concurrent releases are serialized or otherwise protected from conflicting mutations.
- Jobs and external operations have explicit timeouts.
- Required checks fail clearly. Advisory checks are labeled as advisory.

## Repository discovery

Before designing jobs, inspect:

- source languages and runtime versions;
- package manifests, lock files, generated files, and build configuration;
- existing test categories and required services;
- Dockerfiles, deployment manifests, registries, and release conventions;
- branch protection, environments, secrets, and identity federation;
- current workflow history and known operational constraints.

Do not infer the delivery model from filenames alone.

## Trust and permissions

- Default workflow permissions to read-only and elevate only the job that needs more.
- Never run untrusted pull-request code with repository or environment secrets.
- Treat `pull_request_target`, reusable workflows, `workflow_run`, artifact downloads, caches, and generated scripts as trust-boundary features.
- Disable persisted checkout credentials when later steps do not need to push.
- Prefer short-lived federated identity over stored long-lived credentials.
- Protect release environments with review and branch or tag policies appropriate to impact.
- Validate user-controlled paths, image names, tags, and command arguments before mutation.

## Dependencies and actions

- Use lock files or exact constraints for dependencies used by the quality gate.
- Pin third-party GitHub Actions to full commit SHAs and retain a human-readable release comment.
- Keep Dependabot or equivalent automation enabled for controlled updates.
- Pin container images by digest for protected release paths when operationally feasible.
- Do not duplicate current versions in standards or manually maintained matrices.
- Verify update PRs through the same tests as ordinary changes.

## Validation sequence

Prefer this order when dependencies allow it:

1. repository and configuration validation;
2. formatting and generated-file checks;
3. static analysis and schema validation;
4. compilation or build;
5. unit and contract tests;
6. integration tests with controlled dependencies;
7. packaging and artifact inspection;
8. security and policy gates;
9. publication and deployment smoke tests.

A smaller repository may combine steps, but it must not hide which property failed.

## Tests and external compatibility

- Unit tests prove local logic.
- Contract fixtures prove producer and consumer assumptions against recorded examples.
- Service containers or sandboxes prove integration behavior under controlled conditions.
- Live smoke tests prove current external compatibility when credentials and cost permit.
- Mocks do not prove an upstream API, registry, or deployment platform still behaves as expected.
- Flaky checks are fixed, isolated as explicitly advisory, or removed; they are not silently retried until green.

## Artifacts and caching

- Build once and promote the tested artifact where feasible.
- Record artifact digest, source revision, build inputs, and provenance.
- Cache keys include all inputs that affect the cached result.
- Caches accelerate work but are never treated as trusted release artifacts.
- Restore keys are broad only when stale entries are safe.
- Validate packages, archives, images, or generated bundles at the layer actually shipped.

## Publication and deployment

- Use one version authority and verify package, image, tag, and release metadata agree.
- Make publication idempotent or detect already-published versions safely.
- Separate validation permissions from publication permissions.
- Require successful validation of the exact source or artifact being released.
- Define rollback, safe-forward recovery, and post-deployment verification before enabling automated production changes.
- Keep release notes focused on user-visible or operational changes, not internal review history.

## Observability

A production delivery path records:

- workflow and job identity;
- source revision and artifact digest;
- environment and deployment target;
- duration, result, retries, and cancellation;
- publication or deployment outcome;
- recovery action when a mutation partially succeeds.

Logs do not expose secrets, tokens, private keys, or sensitive payloads.

## Local parity

Provide a local command for deterministic checks. Local hooks may be faster and narrower than CI, but they use the same underlying configuration and do not weaken the authoritative gate.

Networked, credentialed, multi-platform, and deployment checks may remain CI-only. Document that boundary instead of pretending full local parity exists.

## Template use

Bundled templates demonstrate secure defaults for common cases. Before use:

1. remove jobs that do not apply;
2. replace placeholders with repository facts;
3. verify action commits and runtime versions;
4. minimize permissions;
5. validate trigger reachability;
6. run the local quality gate;
7. inspect the rendered workflow as ordinary code.

## Acceptance

A pipeline is acceptable when the tested revision is traceable to the released artifact, trust boundaries are enforced, dependencies are reproducible, actions are immutable, deterministic checks have local parity, publication is protected, and recovery is defined.

## Verification

Render every applicable template with representative values, scan `uses:` entries for full commit SHAs, validate YAML after template rendering, run the target repository's local CI command, and exercise at least one failing path. Live publication or deployment claims require runtime evidence from the target platform.
