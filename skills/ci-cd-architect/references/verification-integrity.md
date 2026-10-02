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

A gate defines a **policy-governed validation corpus** and proves discovery/selection/exercise completeness. Test files are one specialization; governed config, templates, and inventories use the same rule.

Prefer automatic convention discovery. A manifest must satisfy:

```text
discovered = selected + reviewed exclusions
```

Use exact repository-relative `required_subjects` for anything whose absence must fail. Required subjects join discovery when present; when absent they appear in `missing_required_subjects` and make the gate non-green. They cannot be excluded. Pattern discovery alone cannot prove that a formerly present source still exists.

Selection and execution are separate evidence axes. Without observed execution, completeness is unknown. The summary reports `expected_subjects`, `discovered_subjects`, `exercised_subjects`, and `missing_required_subjects`; manifest drift, missing required identities, stale exclusions, or execution drift is non-green.

Use `tools/check_test_corpus.py`; `--executed-manifest` supplies runner-observed execution. The filename is retained for compatibility.

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

`contracts/verification-receipt.schema.json` owns the combined result. New producers set `test_corpus.accounting_profile: governed-validation-corpus`, which requires all subject-accounting fields. `legacy-test-files` and unprofiled schema-v1 receipts retain old file-count compatibility but do not prove governed required-subject claims.

A `pass` requires complete evidence for its declared profile, zero drift/blocking execution conditions, declared dependencies, unchanged protected state, and required evidence references.
