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

The deterministic helper always derives the minimum proof mapping from the referenced obligation kinds. Explicit `proof_classes` augment that minimum; they may add narrower or specialized proof but MUST NOT replace or weaken the obligation-kind minimum. `UNKNOWN`, missing, stale, vacuous, or semantically incomplete evidence for a required criterion is non-green.

## Criterion completeness and exact evidence

Evidence granting candidate confidence MUST identify a non-empty exact candidate revision and the exact acceptance-contract digest. Evidence from another candidate or admitted contract is stale unless an owning policy has a mechanically proven safe-reuse rule. An `exact_artifact` proof additionally carries an `ExactEvidenceBinding` whose candidate and evidence revisions match the current candidate and whose artifact digest is a valid SHA-256 identity; a proof-class label alone is not artifact evidence.

A green layer count is not acceptance when a required criterion is uncovered. Each required proof class must have current evidence. A `FAIL` is a hard criterion failure only when it comes from a required proof class, passes the same exact identity/provenance binding required for that proof class, and satisfies any required proof-of-exercise discriminant; unbound, stale, or unexercised failure evidence is `INCOMPLETE`, not authority to reject the candidate. `UNKNOWN` and missing evidence remain incomplete rather than being averaged into PASS. Public validators and acceptance evaluation MUST validate decoded root/container, record, field, nested-binding, policy-waiver, caller-gap, semantic-review, and concrete-path shapes before dereferencing them. Static type annotations do not replace boundary validation; malformed decoded input is returned as findings/`INCOMPLETE`, not an exception.

A negative/failure-path criterion that requires proof of exercise must carry a bounded discriminating observation such as a reason code, sentinel, observed transition, provider/mock invocation, or receipt. A green command without evidence that the intended path ran is incomplete. Zero observations capable of discriminating a required claim are a vacuous PASS and therefore non-green.

Producer `PASS` and semantic coverage are separate. Deferred load-bearing evidence, `coverage_complete=false`, or a nonzero deferred count cannot satisfy a criterion that requires complete coverage.

For provider/parser-dependent criteria marked `provider_faithful`, every load-bearing proof that can decide acceptance uses captured provider evidence or an authoritative contract shape. This applies before either PASS or hard FAIL is authoritative. A simplified synthetic fixture may prove a mechanism but not provider compatibility.

## Known gaps and waiver authority

Implementers, models, reviewers, and validators may report a stable known gap, but reporting a gap never grants authority to accept it. A gap intersecting a required criterion remains non-green when its impact is load-bearing or unknown.

`waived_by_policy` is valid only with trusted policy authorization, explicit scope, and a durable waiver reference. Implementer-reported `KnownGap` data carries no authorization fields: waiver authority is a separate policy-owned record bound to the gap id, explicit criterion refs, exact candidate revision, exact acceptance-contract digest, and durable waiver reference. Callers MUST source that authorization from a trusted policy boundary rather than reconstructing it from implementer/model input. An implementer cannot self-declare a required criterion `not_applicable`. A resolved gap is current only when its resolution is bound to the current candidate and acceptance-contract digest.

Acceptance additionally consumes a trusted **complete known-gap registry snapshot** bound to the exact candidate and acceptance-contract digest. The snapshot carries the complete `KnownGap` records—not only their IDs—including criterion scope, load-bearing state, disposition, and any resolution identity. Acceptance evaluates those trusted records directly and validates their runtime shape fail-closed before dereferencing fields. A gap whose impact is load-bearing or unknown MUST identify at least one affected criterion regardless of disposition; an empty scope is incomplete rather than equivalent to “affects nothing,” including for resolved or waived records. A caller-supplied gap list may be used only as a consistency cross-check and cannot override or erase the snapshot. An explicit empty trusted snapshot is therefore required to prove that no durable gaps exist; omission from a later handoff, summary, or prose cannot turn a previously known load-bearing gap green.

## Semantic review plan

When policy requires semantic review, use `contracts/semantic-review-plan.schema.json` to declare **what must be reviewed before the verdict is interpreted**. The plan is separate from a ReviewReceipt: the plan declares scope for exact candidate `C`; the receipt records what a reviewer actually examined and concluded for `C`.

Review priority follows consequence and semantic ownership rather than LOC or filename order. Supported risk reasons include authority boundaries, state transitions, persistence/migration, external side effects, retry/idempotency, concurrency, security boundaries, public contracts, cross-component invariants, rollback/recovery, analogue drift, and diagnostic egress.

A plan may contain user/system flows, focus areas, analogous implementations, and invariant matrices. Required criteria mapped to `semantic_review` have explicit plan coverage. Semantic-review PASS evidence is accepted only when the evaluator has validated the plan against the same candidate and acceptance contract and the evidence carries that exact plan digest. When the plan declares a non-null base revision, the evaluator also requires the current base revision and rejects missing or stale base identity. Conversely, when a caller supplies the current base revision, a plan with a null or different base binding is stale. Widening or revising the plan therefore invalidates older semantic-review evidence even when the candidate SHA is unchanged. An empty or generic “review these files” plan cannot satisfy a required criterion: a focus area identifies concrete paths, risk reasons, and invariants. When a concrete repository path set is available, deterministic validation rejects unresolved primary and analogue path references rather than treating arbitrary strings as coverage, and acceptance evaluation forwards that same set before counting semantic-review proof.

The default freshness rule is `plan(C1) is stale for C2`. Base-dependent plans are stale after a material base change. Reuse is allowed only when policy can mechanically establish unchanged load-bearing dependencies; provider UI state or prose is insufficient.

The resulting receipt is evidence, not the plan: the repository-level `contracts/review-receipt.schema.json` contract and `contracts/review_receipt.py` evaluator own the provider-neutral `ReviewReceipt` v1 that records what a reviewer actually examined and concluded for the exact candidate — attested reviewer independence, predeclared per-criterion outcomes, review-input coverage, provider operation lifecycle, durable finding state, and mechanical exact-candidate currentness. Consumers derive the admission gate under their own trusted review policy; a candidate, plan, rubric, policy, base, or input-manifest change invalidates the receipt by default, and the reviewer's aggregate verdict can never raise a gate above its own criterion and finding state.

## Negative space and invariant families

For identity, authority, admission, provenance, parser/schema, state, and recovery boundaries, review the applicable negative space around the invariant instead of only the changed happy path. Select dimensions from the actual risk; do not impose the full matrix on unrelated pure functions.

Structured-input dimensions may distinguish present-valid, invalid, missing, explicit null, empty container, wrong type, malformed value, unknown, stale, concurrent, recovery, conflicting identity/generation/digest, equal aliases, conflicting aliases, unexpected extra sources, and ambiguous fallback. Dimensions may be collapsed only when the owning contract proves they are semantically equivalent for the reviewed invariant. Analogous branches/adapters can be grouped so one repaired path does not hide analogue drift.

For diagnostic egress, consume the repository-level `contracts/diagnostic-egress.schema.json` contract (with `contracts/diagnostic_egress.py` as the reference constructor/semantic validator). Consider known/alternate provider wording, internal apostrophes or nested quotes, escaped/double quotes, multiline and Unicode/control input, malformed-decode paths, nested wrappers, long errors, unknown wording, and source/request payload embedded in an upstream error. Review protected sinks for the invariant that raw source/provider payload is absent, unknown classification falls back to a bounded generic diagnostic, and any forensic raw detail is only an opaque narrower-authority reference. Prefer typed/allowlisted construction over copying arbitrary error strings and attempting heuristic redaction.

A newly discovered omitted invariant dimension may revise the plan; the new plan receives a new semantic digest and exact-candidate binding rather than silently widening the old receipt. Deterministic validation checks declared shape, published schema-version/type/length bounds, and references but does not claim static heuristics can discover all semantically applicable risks or invariants.

## Migration acceptance

When a change modifies persistent schema/storage or claims compatibility with historical persisted state, acceptance MUST declare the current schema identity, the exact production migration entrypoint and its revision, every supported input state, and the intentionally unsupported/ambiguous input classes. Fresh/empty installation evidence is separate from legacy-upgrade evidence; neither substitutes for the other.

Every supported legacy fixture is constructed or restored **without executing the current bootstrap/migration path first**. Before the candidate migrator runs, executable preflight evidence proves the intended legacy schema/version, selected legacy characteristics, selected current characteristics that are still absent, and an immutable fixture/snapshot identity. A filename, variable name, or caller assertion such as `v5.db` is not pre-migration proof.

Migration acceptance invokes the same coordinator/entrypoint used by production startup or deployment and binds that implementation to an exact revision. An alias, helper, test migrator, or another database layer with a compatible interface is not equivalent; exercising it is harness failure. When several migration layers exist, the acceptance matrix names the layer under test.

The matrix proves separately:

1. fresh/empty state reaches the current schema;
2. every declared supported predecessor reaches current through the production migrator;
3. representative persisted data and required ownership/key/index invariants survive;
4. current-schema rerun is exercised only when production requires idempotent rerun;
5. unsupported, too-old, unknown, or ambiguous starting state is deliberately rejected and cannot be silently normalized to current; an unsupported entry may carry a known schema identity or an explicit unknown/null identity, but it remains distinct from `fresh`; and
6. interrupted/failed migration follows the declared transaction/recovery contract.

Historical fixtures or builders are immutable/version-pinned evidence inputs. Changing them changes the compatibility claim and requires review. Dropping support changes the declared matrix explicitly rather than deleting a failing predecessor fixture.

Use `tools/migration_acceptance.py` to compose a bounded receipt that names the exact candidate revision, current schema, production entrypoint revision, and each exercised input's stable ref, kind, and declared schema identity. Raw migration evidence describes observations only: it MUST NOT choose whether current-schema rerun or interrupted-recovery proof is required. Those policy switches arrive through a trusted caller/policy boundary; malformed or caller-authored policy fields in the raw payload are rejected. The helper evaluates evidence; it does not execute a product migrator or turn caller-authored labels into proof. Product tests remain responsible for executable pre-state assertions, migration invocation, data checks, and recovery observations.

## Failure attribution

Verification MUST distinguish harness failure from product failure. A broken harness blocks the affected verification claim but is not evidence that the product failed; a product failure remains product evidence even when the harness also has faults. Mixed conditions stay explicit until separated.

## Verification scheduling and minimum rerun

A verification plan MAY declare dependency-aware verification nodes so that execution order and the minimum rerun set are derived from evidence dependencies and policy instead of one fixed global checklist. `tools/verification_schedule.py` is the deterministic planner; it composes with the risk planner in `tools/plan_verification.py` and never replaces it.

One node declares its identity, the criteria it covers, its evidence kind, its dependencies, its relative cost class, an optional trusted duration profile, an optional validation-environment identity, the subjects whose change invalidates its evidence, the boundaries before which it is required, and whether it is required at all. The representation is indicative; the invariants below are not.

```text
bounded, typed plan input
  -> unique node identities, existing dependencies, no self-edge, no cycle, bounded size
  -> deterministic order: dependency topology, then material discrimination, then cost and known duration
cheap independent discriminator before an expensive dependent gate
  -> a failed prerequisite blocks the dependent gate instead of buying it
current exact-subject evidence
  -> reused only while candidate, base, contract, policy, environment, expiry, and declared subject coverage stay current
changed subject
  -> invalidates the directly bound receipt and only its declared dependents
required exact-candidate final gate
  -> mandatory regardless of cheaper focused success, and stale after any source change
unknown coverage, unknown identity, or unknown duration
  -> conservative non-green, never optimistic reuse and never a fabricated blocker
```

The planner returns one typed decision per node — `RUN`, `REUSE_CURRENT`, `DEFER_UNTIL_DEPENDENCY`, `NON_DISPATCH`, or `BLOCKED_UNKNOWN` — each with a typed reason and the required next action. A scheduling recommendation is never a pass, a waiver, a reviewer verdict, a mutation authorization, or a release decision. The planner executes nothing and never runs a candidate command taken from schedule data.

Ordering is a preference inside proof dependencies, not permission to reorder across a correctness dependency. Where dependencies permit, cheap structural and schema discriminators run before focused tests, focused tests run before broader and full gates, and the policy-required exact-candidate final gate runs at the freeze or integration boundary. A node whose outcome cannot change the next verification action and that nothing depends on MAY be deferred when it is not required; a mandatory node is never deferred for that reason, and a mandatory node with no branching value still runs.

Reuse is a property of qualified evidence, not of a caller's claim. Only a complete trusted evidence snapshot authorizes reuse, and each receipt binds its node, candidate revision, optional base revision, acceptance-contract digest, policy revision, validation environment, expiry, and the concrete subjects its evidence depends on. A receipt that does not declare coverage for every declared invalidation kind has unknown dependency coverage and is not reusable. Caller-supplied pass text, a file name, or a green status badge is not evidence.

A changed subject invalidates the directly bound receipt and, through declared dependencies, only its dependents. Unaffected current evidence stays reusable. A candidate-bound node's evidence does not survive a candidate change, so the final exact-candidate gate and the exact-head review are re-required after any source change. Content-tree equality does not transfer reviewer approval, and a squash or integration commit is not the reviewed candidate revision.

Provider availability is separate from product outcome. A `NOT_EXECUTED` or unavailable external gate leaves that node non-green and its dependents deferred; it does not invalidate unrelated current local evidence and it never justifies rerunning an unchanged current gate. `UNKNOWN` provenance never normalizes to a match.

Operation admission uses a trusted measured or declared duration profile plus a reconciliation reserve. A node whose trusted duration plus reserve exceeds the remaining admitted window is parked with a typed non-dispatch result instead of a predictable timeout. An unknown duration stays unknown and never becomes a fabricated blocker.

A cheap prerequisite that can detect a release-worktree divergence belongs before the expensive gate it protects. When the committed release artifact and the working-tree artifact disagree, the release worktree head mismatch is reported and the dependent gate is not dispatched until the state is corrected and the candidate is committed.

Scheduling composes with the existing owners. Evidence truth and freshness remain owned by the execution-evidence lineage, review verdicts by the review-receipt owner, environment identity by the validation-environment owner, waiver authority by the delivery policy, and artifact closure by the artifact-closure contract. This skill owns ordering and the minimum rerun set; it does not define a second evidence identity, a second assessment evaluator, or a runtime queue.

## Composition boundaries

This skill owns software-change acceptance semantics and semantic-review scope planning. It does not own task/session memory, Steward workflow state, ReviewReceipt verdict/independence semantics, cross-system evidence lineage, or delivery-policy selection of when these contracts are mandatory. Those owners consume stable contract/plan identities rather than copying these schemas.

## Definition of done

The risk class and required layers are deterministic; the admitted obligation/criterion set has a stable semantic identity; every required obligation has required criterion coverage; every required criterion has current non-vacuous proof or an authorized waiver; known gaps cannot self-waive; semantic review scope is exact-candidate-bound and covers every required review criterion; stale simulation/plans/evidence are invalidated; harness and product failures are not conflated; and every required claim is either satisfied or explicitly non-green.
