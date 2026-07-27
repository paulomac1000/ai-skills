---
description: Reusable CI/CD failure patterns derived from production deployment and review incidents.
doc_id: reference.ci-cd-failure-patterns
type: reference
status: active
rigor: informative
owners: [repository-maintainers]
---

# CI/CD failure patterns

## Unreachable release job

A package job guarded by `startsWith(github.ref, 'refs/tags/v')` never runs when the workflow does not trigger on tags. Verify event reachability for every job condition.

## Stale .NET cache

A NuGet cache keyed only by project files survives changes to `Directory.Packages.props` or `Directory.Build.props`. Include central package and build inputs in the key.

## Invalid pip cache in .NET repositories

`setup-python` with `cache: pip` fails or creates meaningless behavior when no matching dependency file exists. Specify `cache-dependency-path` or omit the cache.

## Token-suppressed workflow chaining

Tags or pushes created with `GITHUB_TOKEN` may not trigger a second workflow. Prefer a single release workflow, a reusable workflow call, or an explicitly authorized dispatch with reviewed identity.

## Wrong manual-release identity

Metadata actions derive semver and SHA from event context. When `workflow_dispatch` selects another ref, use validated outputs rather than context-derived tag types.

## Source tests but broken package

Testing the checkout does not test Dockerfile stages, copied files, runtime user, entry point, or resolved image dependencies. Build once, smoke-test the local artifact, then push that exact artifact.

## Unsafe pull-request write permissions

A workflow that executes untrusted PR code with write scopes, secrets, or persistent checkout credentials expands the compromise boundary. Split untrusted validation from trusted comment or release workflows.

## Semgrep report assumptions

Uploading a missing SARIF file turns a useful scan into noisy failure. Preserve scanner failure semantics while guarding the upload on actual report existence.

## Auto-tag early exit

An `exit 0` in a preparation step does not automatically prevent later publish or dispatch steps. Export an explicit decision and gate downstream steps.
