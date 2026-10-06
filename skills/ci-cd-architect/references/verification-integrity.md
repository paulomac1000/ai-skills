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

### Dependency lock operations

For repositories with exact locks, `operation: candidate_verification` requires a declared lock source, `upstream_resolution: forbidden`, `lock_mutation: forbidden`, and `reviewable_diff: false`. The ecosystem gate validates that committed lock (for Python, `pip install --require-hashes` plus `pip check`) without invoking a resolver to choose a new graph.

`operation: dependency_refresh` is separate. Its `lock_contract` declares `upstream_resolution: mutable|immutable`, a safe `upstream_identity`, `resolver_dependency_id`, `runtime_dependency_id`, `lock_mutation: reviewable`, `reviewable_diff: true`, and `reproducibility_claim: observational|exact`; refresh cache is `disabled` or `isolated`. Resolver and runtime IDs MUST name entries in `dependencies`, so their version/source digests are part of evidence. Mutable upstream permits only `observational`; `exact` additionally requires immutable upstream identity. Do not place credentials in source identities.

Lock refresh proposes a diff; it never retroactively proves the previous committed candidate unreproducible. Vulnerability/advisory freshness is an independent gate. Use `tools/check_verification_bootstrap.py`; it extends the existing bootstrap authority rather than defining another one.

## Exact artifact evidence

Use `contracts/artifact-evidence.schema.json` and `contracts/artifact_evidence.py` when a verification or release decision depends on an exact structured artifact identity.

The v1 file-tree encoding starts with the fixed domain `ai-skills/artifact-tree/v1\\0`, then the file count as an unsigned 8-byte big-endian integer. Each sorted regular-file entry is encoded as the byte `F`, followed by an 8-byte length and normalized UTF-8 path bytes, then an 8-byte length and the file content bytes. Length-prefix framing keeps arbitrary delimiter/control bytes in content unambiguous. Ordering is by NFC-normalized relative POSIX path bytes.

The v1 metadata mode is `regular-file-content-only-v1`. It does not claim executable-bit, ownership, timestamp, xattr, device, directory-entry, or symlink identity. A collector encountering a symlink or another unsupported file type returns `unknown`; a policy for which additional metadata is load-bearing must use another explicit construction revision rather than silently treating v1 as sufficient.

Coverage is separate from digest algorithm:

```text
complete trusted enumeration + all profile bounds respected
  -> coverage=exact + artifact digest
file/byte/depth/time bound hit
  -> coverage=partial + no artifact digest
known incomplete enumeration
  -> coverage=partial + no artifact digest
unsupported subject/file semantics
  -> coverage=unknown + no artifact digest
```

Bounds belong to the construction profile and are included in its digest. `max_bytes` counts normalized UTF-8 path bytes plus regular-file content bytes; fixed framing overhead is separately bounded by `max_files`. Qualification must demonstrate that representative supported artifacts fit the selected profile; increasing a bound changes profile identity but does not weaken subject coverage. V1 exposes no exclusion input. The policy-owned collector defines the artifact root and proves enumeration completeness; repository/model/candidate content cannot self-remove files and still claim exact coverage.

Requested identity is immutable admission evidence. Observed identity records what was actually found. A fallback observation may establish an exact artifact digest while `requested_identity_matched` remains false or unknown. The artifact constructor never promotes `source_compatibility_established` or `runtime_compatibility_established`; those claims require their owning evidence.

A material construction-profile change makes direct digest evidence non-comparable unless an owning compatibility policy explicitly proves otherwise. Reuse preserves the original profile digest and producer observation rather than relabeling old evidence as freshly constructed.

## Production-state isolation

Ordinary validation is read-only with respect to production-effective state. Before near-runtime validation, resolve declared writable and protected paths component-wise and prove they do not overlap. Writable paths may be declared before creation; existing protected paths must resolve and must not be symlink aliases. Snapshot/hash protected state where practical, execute validation in unique disposable state, then assert protected state unchanged. A protected tree containing a symlink is rejected rather than followed into ambiguous state.

Use `tools/verify_state_isolation.py`. Deployment and migrations are separate transactions and use `contracts/deployment-lease.schema.json` plus the applicable deployment authority.

## Receipt semantics

`contracts/verification-receipt.schema.json` owns the combined result. New producers set `test_corpus.accounting_profile: governed-validation-corpus`, which requires all subject-accounting fields. `legacy-test-files` and unprofiled schema-v1 receipts retain old file-count compatibility but do not prove governed required-subject claims.

A `pass` requires complete evidence for its declared profile, zero drift/blocking execution conditions, declared dependencies, unchanged protected state, and required evidence references.
