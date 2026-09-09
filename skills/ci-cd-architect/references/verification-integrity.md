---
description: Reusable verification-integrity contract for local and hosted quality gates.
doc_id: reference.cicd-verification-integrity
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Exercise test-corpus drift, execution-integrity, local-parity, dependency-bootstrap, and protected-state fixtures.
---

# Verification integrity

Use this reference when a gate can be green without proving that the intended work actually ran.

A verification verdict is valid only when the intended test corpus was selected, selected tests terminated cleanly, verdict-affecting dependencies came from declared repository-owned sources, the local entrypoint represents every merge-blocking hosted gate or reports it as hosted-only, and validation did not mutate production-effective runtime state.

## Test corpus

Prefer convention-driven automatic discovery. When ordering or another constraint requires an explicit manifest, assert:

```text
discovered by convention
= execution manifest
+ reviewed exclusions
```

A newly added conforming test that is absent from the manifest is `TEST_DISCOVERY_DRIFT`, not an implicit exclusion. Exclusions carry a reason and, where useful, owner and expiry. Unknown discovery completeness yields `incomplete`, never `pass`.

Use `tools/check_test_corpus.py`.

## Execution integrity

A zero process exit or green assertion count is insufficient when selected work was cancelled, remained pending, leaked asynchronous work, or raised an exception outside the primary assertion path.

Blocking classes include unhandled thread/task/process exceptions, unraisable exceptions, pending/destroyed tasks, meaningful never-awaited coroutines, Node file-level cancellation caused by unresolved work, unhandled rejections, and equivalent framework signals. Ordinary deprecations may remain non-blocking only through a reviewed narrow policy.

Explicit skips remain distinct from cancellation. `11/11` successful subtests followed by a cancelled file is non-green.

Use `tools/check_execution_integrity.py`.

## Local and hosted parity

Every merge-blocking hosted gate maps to one supported local entrypoint or has an explicit `hosted_only` rationale. Both paths consume the same policy/configuration and pinned tool sources where the environment permits. Local success reports hosted-only work as not executed; it cannot manufacture provider evidence.

Use `tools/check_local_ci_parity.py`.

## Dependency bootstrap

Verdict-affecting tools come from repository-declared locks, manifests, tool-version files, immutable container digests, or an explicit bootstrap script. Ambient global/site packages never silently satisfy an undeclared dependency. Evidence records the resolved tool version and policy/lock revision. Missing declared bootstrap is an admission failure.

## Production-state isolation

Ordinary validation is read-only with respect to production-effective state. Before near-runtime validation, resolve declared writable and protected paths component-wise and prove they do not overlap. Snapshot/hash protected state where practical, execute validation in unique disposable state, then assert protected state unchanged. Tests that changed the target they were meant to observe are invalid evidence even if assertions passed.

Use `tools/verify_state_isolation.py`. Deployment and migrations are separate transactions and use their own authority/lease contract.
