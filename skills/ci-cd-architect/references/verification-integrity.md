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

A verification verdict is valid only when the intended validation corpus was selected, actual selected-subject execution is evidenced, selected work terminated cleanly, verdict-affecting dependencies came from declared repository-owned or immutable sources, the local entrypoint represents every merge-blocking hosted gate or reports it as hosted-only, and validation did not mutate production-effective runtime state. The canonical combined receipt is `contracts/verification-receipt.schema.json`.

## Validation corpus

A gate first defines the **policy-governed validation subjects**, then proves discovery/selection/exercise completeness. Test files are the common specialization, but the same rule applies to governed configuration, templates, generated policy inventories, or other validation inputs whose omission could make a green gate meaningless.

Prefer convention-driven automatic discovery. When ordering or another constraint requires an explicit manifest, assert:

```text
discovered by convention
= selected by execution policy
+ reviewed exclusions
```

When a subject is mandatory even if it disappears from the filesystem, declare its exact repository-relative identity in `required_subjects`. Required subjects are resolved independently of discovery heuristics: an existing required subject joins the corpus even when an include heuristic would miss it, while a deleted required subject is reported in `missing_required_subjects` and makes the corpus non-green. A required subject cannot be converted into an exclusion.

Equivalent policy:

```yaml
schema_version: 1
policy_revision: governed-source/v1
mode: automatic
include:
  - "**/*.yaml"
required_subjects:
  - automations.yaml
  - scripts.yaml
exclusions: []
```

Selection and execution are separate evidence axes. Automatic discovery proves which existing subjects should be selected; it does not prove those subjects actually executed. Post-run execution evidence is therefore required before a corpus result becomes `complete`. Without it, the verdict is `incomplete`, never `pass`.

The gate summary exposes legacy file counts plus generic `expected_subjects`, `discovered_subjects`, `exercised_subjects`, and exact `missing_required_subjects`. A newly added conforming test absent from an explicit selection manifest, a deleted required source, or a governed source dropped only because a semantic heuristic no longer recognizes it is discovery drift rather than an implicit reduction of the corpus. Exclusions carry a reason and, where useful, owner and expiry; stale exclusions remain policy drift.

Use `tools/check_test_corpus.py`; provide `--executed-manifest` from the test-runner/result adapter for authoritative execution evidence. The filename remains stable for compatibility even though the contract now covers the broader validation corpus.

## Execution integrity

A zero process exit or green assertion count is insufficient when selected work was cancelled, remained pending, leaked asynchronous work, or raised an exception outside the primary assertion path.

Blocking classes include unhandled thread/task/process exceptions, unraisable exceptions, pending/destroyed tasks, meaningful never-awaited coroutines, Node file-level cancellation caused by unresolved work, unhandled rejections, and equivalent framework signals. Explicit skips remain distinct from cancellation. `11/11` successful subtests followed by a cancelled file is non-green.

Warning allowlists apply only to otherwise non-blocking warning classes. A regex or framework allowlist MUST NOT suppress an already recognized unhandled exception, pending task, cancellation, unraisable exception, or leaked-async-work signal. Ordinary deprecations may remain non-blocking through a narrow reviewed policy; an unclassified warning is not silently promoted to green.

Use `tools/check_execution_integrity.py`.

## Local and hosted parity

Every merge-blocking hosted gate maps to one supported local entrypoint or has an explicit `hosted_only` rationale. The mapping names the policy/configuration source used for the verdict and, for local execution, the dependency/bootstrap source. A gate cannot be both local and hosted-only. Local success reports hosted-only work as not executed; it cannot manufacture provider evidence.

Use `tools/check_local_ci_parity.py`.

## Dependency bootstrap

Verdict-affecting tools come from repository-declared locks, manifests, tool-version files, immutable container digests, or an explicit bootstrap script. Ambient global/site packages never silently satisfy an undeclared dependency. Evidence records the resolved tool version and source digest/reference. Mutable image tags are not immutable dependency sources. Network and cache assumptions are explicit; cached dependency use is either disabled or verified against the declared identity.

Use `tools/check_verification_bootstrap.py`. It validates dependency-source provenance; ecosystem-specific bootstrap/install commands remain repository-owned and must consume those declared sources.

## Production-state isolation

Ordinary validation is read-only with respect to production-effective state. Before near-runtime validation, resolve declared writable and protected paths component-wise and prove they do not overlap. Writable paths may be declared before creation; existing protected paths must resolve and must not be symlink aliases. Snapshot/hash protected state where practical, execute validation in unique disposable state, then assert protected state unchanged. A protected tree containing a symlink is rejected rather than followed into ambiguous state.

Use `tools/verify_state_isolation.py`. Deployment and migrations are separate transactions and use `contracts/deployment-lease.schema.json` plus the applicable deployment authority.

## Receipt semantics

`contracts/verification-receipt.schema.json` is the single machine-readable owner of the combined result. A `pass` receipt requires declared-only dependency resolution, complete test-corpus evidence with zero discovery/execution drift, zero blocking execution-integrity conditions, and unchanged production-effective state. Unknown corpus completeness, unknown async leak state, hidden hosted-only work, or missing evidence must remain incomplete/degraded/blocked as appropriate rather than being encoded as success.
