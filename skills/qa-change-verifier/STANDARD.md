---
afds_schema_version: 2
description: Normative risk-based change acceptance, semantic review planning, exact-evidence binding, and failure-attribution rules.
doc_id: reference.qa-change-verifier-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Run qa-change-verifier contract, planner, review-plan, acceptance regressions and the repository exact-head gate.
---

# QA change verifier standard

## Risk planning

Verification depth follows evidence risk, not changed-line count. Plan from public/change surface, blast radius, stateful behavior, security sensitivity, external dependencies, and whether post-deploy behavior is material. The baseline layers are static, unit, integration, exact artifact, real transport, external E2E, security review, and post-deploy.

Low risk requires static and unit evidence. Medium risk adds integration and exact-artifact evidence. High risk requires the complete baseline so public/state/security/external failures cannot hide behind narrow tests. A criterion may add a specific proof class that the risk-only baseline would not otherwise select; it does not cause every criterion to inherit every layer.

## Immutable change acceptance contract

When policy requires an explicit software-change contract, use `contracts/change-acceptance.schema.json`. The contract is immutable admitted intent: stable `change_id`, `revision`, semantic `digest`, obligations, and falsifiable acceptance criteria. It contains no mutable satisfaction flags.

Required invariants are:

```text
required obligation
  -> at least one required acceptance criterion
required criterion
  -> one or more deterministic proof classes
required criterion
  -> current exact evidence or an explicitly authorized policy waiver
```

Planner decomposition may refine the work but cannot silently remove or weaken admitted obligations. Changing obligation or criterion semantics creates a new revision/digest. Criteria describe observable outcomes and rejection conditions rather than implementation guesses. Optional criteria remain distinct from waived mandatory criteria.

For contract v1, the digest is `sha256:` plus lowercase SHA-256 of UTF-8 JSON for the complete object with the `digest` member omitted, object keys sorted lexicographically, no insignificant whitespace, and non-ASCII characters encoded directly rather than escaped. Array order is part of v1 identity. The same construction applies to Semantic Review Plan v1. A producer using another language must reproduce this byte contract or treat the digest as opaque rather than invent a competing normalization.

If `proof_classes` is omitted, the deterministic helper derives the minimum mapping from obligation kinds. A repository/policy may declare a more precise mapping. `UNKNOWN`, missing, stale, vacuous, or semantically incomplete evidence for a required criterion is non-green.

## Criterion completeness and exact evidence

Evidence granting candidate confidence MUST identify a non-empty exact candidate revision and the exact acceptance-contract digest. Evidence from another candidate or admitted contract is stale unless an owning policy has a mechanically proven safe-reuse rule. An `exact_artifact` proof additionally carries an `ExactEvidenceBinding` whose candidate and evidence revisions match the current candidate and whose artifact digest is a valid SHA-256 identity; a proof-class label alone is not artifact evidence.

A green layer count is not acceptance when a required criterion is uncovered. Each required proof class must have current evidence. `FAIL` is a hard criterion failure; `UNKNOWN` and missing evidence remain incomplete rather than being averaged into PASS. Acceptance MUST validate runtime container, record, field, and nested-binding shapes for evidence, policy-waiver input, caller gap input, semantic-review input, and concrete path sets before dereferencing them. Static type annotations do not replace boundary validation; malformed decoded input is `INCOMPLETE`, not an exception.

A negative/failure-path criterion that requires proof of exercise must carry a bounded discriminating observation such as a reason code, sentinel, observed transition, provider/mock invocation, or receipt. A green command without evidence that the intended path ran is incomplete. Zero observations capable of discriminating a required claim are a vacuous PASS and therefore non-green.

Producer `PASS` and semantic coverage are separate. Deferred load-bearing evidence, `coverage_complete=false`, or a nonzero deferred count cannot satisfy a criterion that requires complete coverage.

For provider/parser-dependent criteria marked `provider_faithful`, at least one load-bearing proof uses captured provider evidence or an authoritative contract shape. A simplified synthetic fixture may prove a mechanism but not provider compatibility.

## Known gaps and waiver authority

Implementers, models, reviewers, and validators may report a stable known gap, but reporting a gap never grants authority to accept it. A gap intersecting a required criterion remains non-green when its impact is load-bearing or unknown.

`waived_by_policy` is valid only with trusted policy authorization, explicit scope, and a durable waiver reference. Implementer-reported `KnownGap` data carries no authorization fields: waiver authority is a separate policy-owned record bound to the gap id, explicit criterion refs, exact candidate revision, exact acceptance-contract digest, and durable waiver reference. Callers MUST source that authorization from a trusted policy boundary rather than reconstructing it from implementer/model input. An implementer cannot self-declare a required criterion `not_applicable`. A resolved gap is current only when its resolution is bound to the current candidate and acceptance-contract digest.

Acceptance additionally consumes a trusted **complete known-gap registry snapshot** bound to the exact candidate and acceptance-contract digest. The snapshot carries the complete `KnownGap` records—not only their IDs—including criterion scope, load-bearing state, disposition, and any resolution identity. Acceptance evaluates those trusted records directly and validates their runtime shape fail-closed before dereferencing fields. A gap whose impact is load-bearing or unknown MUST identify at least one affected criterion regardless of disposition; an empty scope is incomplete rather than equivalent to “affects nothing,” including for resolved or waived records. A caller-supplied gap list may be used only as a consistency cross-check and cannot override or erase the snapshot. An explicit empty trusted snapshot is therefore required to prove that no durable gaps exist; omission from a later handoff, summary, or prose cannot turn a previously known load-bearing gap green.

## Semantic review plan

When policy requires semantic review, use `contracts/semantic-review-plan.schema.json` to declare **what must be reviewed before the verdict is interpreted**. The plan is separate from a ReviewReceipt: the plan declares scope for exact candidate `C`; the receipt records what a reviewer actually examined and concluded for `C`.

Review priority follows consequence and semantic ownership rather than LOC or filename order. Supported risk reasons include authority boundaries, state transitions, persistence/migration, external side effects, retry/idempotency, concurrency, security boundaries, public contracts, cross-component invariants, rollback/recovery, analogue drift, and diagnostic egress.

A plan may contain user/system flows, focus areas, analogous implementations, and invariant matrices. Required criteria mapped to `semantic_review` have explicit plan coverage. Semantic-review PASS evidence is accepted only when the evaluator has validated the plan against the same candidate and acceptance contract and the evidence carries that exact plan digest. When the plan declares a non-null base revision, the evaluator also requires the current base revision and rejects missing or stale base identity. Conversely, when a caller supplies the current base revision, a plan with a null or different base binding is stale. Widening or revising the plan therefore invalidates older semantic-review evidence even when the candidate SHA is unchanged. An empty or generic “review these files” plan cannot satisfy a required criterion: a focus area identifies concrete paths, risk reasons, and invariants. When a concrete repository path set is available, deterministic validation rejects unresolved primary and analogue path references rather than treating arbitrary strings as coverage, and acceptance evaluation forwards that same set before counting semantic-review proof.

The default freshness rule is `plan(C1) is stale for C2`. Base-dependent plans are stale after a material base change. Reuse is allowed only when policy can mechanically establish unchanged load-bearing dependencies; provider UI state or prose is insufficient.

## Negative space and invariant families

For identity, authority, admission, provenance, parser/schema, state, and recovery boundaries, review the applicable negative space around the invariant instead of only the changed happy path. Select dimensions from the actual risk; do not impose the full matrix on unrelated pure functions.

Structured-input dimensions may distinguish present-valid, invalid, missing, explicit null, empty container, wrong type, malformed value, unknown, stale, concurrent, recovery, conflicting identity/generation/digest, equal aliases, conflicting aliases, unexpected extra sources, and ambiguous fallback. Dimensions may be collapsed only when the owning contract proves they are semantically equivalent for the reviewed invariant. Analogous branches/adapters can be grouped so one repaired path does not hide analogue drift.

For diagnostic egress, consume the reusable diagnostic-safety contract and consider known/alternate provider wording, internal apostrophes or nested quotes, multiline and Unicode/control input, nested wrappers, long errors, unknown wording, and source/request payload embedded in an upstream error. Prefer constructing typed/allowlisted diagnostics over copying arbitrary error strings and attempting heuristic redaction.

A newly discovered omitted invariant dimension may revise the plan; the new plan receives a new semantic digest and exact-candidate binding rather than silently widening the old receipt. Deterministic validation checks declared shape, published schema-version/type/length bounds, and references but does not claim static heuristics can discover all semantically applicable risks or invariants.

## Failure attribution

Verification MUST distinguish harness failure from product failure. A broken harness blocks the affected verification claim but is not evidence that the product failed; a product failure remains product evidence even when the harness also has faults. Mixed conditions stay explicit until separated.

## Composition boundaries

This skill owns software-change acceptance semantics and semantic-review scope planning. It does not own task/session memory, Steward workflow state, ReviewReceipt verdict/independence semantics, cross-system evidence lineage, or delivery-policy selection of when these contracts are mandatory. Those owners consume stable contract/plan identities rather than copying these schemas.

## Definition of done

The risk class and required layers are deterministic; the admitted obligation/criterion set has a stable semantic identity; every required obligation has required criterion coverage; every required criterion has current non-vacuous proof or an authorized waiver; known gaps cannot self-waive; semantic review scope is exact-candidate-bound and covers every required review criterion; stale simulation/plans/evidence are invalidated; harness and product failures are not conflated; and every required claim is either satisfied or explicitly non-green.
