---
description: Normative rules for preserving task intent, admitting delegated work, reconciling child outcomes, and completing evidence-bound agent tasks.
doc_id: reference.agent-task-orchestrator-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Validate the intent and delegation contracts, run the deterministic orchestration regressions, and verify final task evidence against the current intent revision and exact execution identity.
---

# Agent task orchestrator standard

## Purpose

This standard governs mutable task state and delegated execution. It preserves the user's current intent across planning, compaction, continuation, delegation, retries, and completion without granting new authority. Durable repository instructions remain owned by the applicable repository-instruction standard; this skill owns only task-lifecycle state.

Provider-specific job APIs, agent transports, and UI concepts are adapters. They may report facts such as job identity, progress, base relationship, and result evidence, but they do not redefine scope, authority, completion, or retry policy.

## Intent ledger

Maintain one compact authoritative ledger using `contracts/intent-ledger.schema.json`. Record a stable task identity, monotonic `intent_revision`, goal, stable requirement IDs and source, required capabilities, required execution methods, acceptance criteria, prohibitions, authorized operations, scope, open questions, and unresolved conflicts.

Requirements remain `pending`, `satisfied`, `blocked`, or `superseded`. A satisfied requirement carries evidence. Superseding a requirement names its replacement and the authority that permitted the change. Strategy changes, context compaction, resource pressure, or delegation must not silently erase a mandatory requirement, required capability, required execution method, prohibition, or acceptance criterion.

User changes produce a new intent revision. Preserve provenance so an older plan or child result cannot silently overwrite newer intent.

## Scope and authority

Before every side effect, bind the exact target and side-effect class to the current ledger. The target must be listed in `in_scope_targets`, must not be listed in `protected_or_out_of_scope_targets`, and the effect class must be listed in `allowed_side_effect_classes`.

A newly discovered collateral target is out of scope until the task owner explicitly expands the ledger. Time pressure, token pressure, unavailable tools, cost pressure, or child convenience do not expand scope.

Delegated authority is a strict subset of parent authority. A child receives only capabilities, operations, resource domains, and protected handles needed for its subtask. A parent credential, DeploymentLease, or secret-taint state does not automatically authorize a child; protected use follows the canonical secret-taint and deployment-lease contracts.

## Planning and execution bases

Record immutable `planning_base` and `execution_base` values for repository-backed work using `contracts/delegation-contract.schema.json`. Each value identifies repository, ref, and full revision. Never rewrite the planning base after a branch moves.

Classify admission as `BASE_UNCHANGED`, `BASE_ADVANCED_COMPATIBLE`, `BASE_TOPOLOGY_CHANGED`, or `BASE_UNKNOWN`. Equal exact revisions are unchanged. A descendant execution revision is compatible only after explicit revalidation proves that upstream changes do not invalidate working-set, authority, interface, generated-output, or other plan assumptions.

A different repository/ref, rebased or diverged history, overlapping upstream change, or incompatible topology requires stop and replan. Unknown relationship or incomplete revalidation fails closed. Branch movement by itself is not evidence of compatibility.

## Delegation admission

Define the smallest delegated subtask before dispatch: current `intent_revision`, immutable planning/execution bases, plan revision, required child capabilities, authority subset, resource domains, expected outputs, and whether actual work is required.

Admission verifies target scope, base state, runtime/provider capability availability, authority subset, and resource-domain conflicts. A child may not infer missing authority from parent prose, repository instructions, or a previous attempt.

The child contract is sufficient to perform its bounded task but does not transfer ownership of parent completion. Shared outcome, runtime identity, audit, secret-taint, and deployment authority contracts remain canonical at repository level and are referenced rather than copied here.

## Dispatch and continuation

Assign a durable `attempt_id` before dispatch and record the returned durable child/job identity exactly once. Launch acceptance proves only that the provider accepted a job; it does not prove the child started useful work or completed the task.

Do not redispatch an existing attempt merely because polling was ambiguous. Reconcile the durable child identity first. Continuing an existing child uses a bounded delta containing only new facts, decisions, or evidence. Do not replay the full task history or raw secrets. A genuine fresh dispatch receives a new attempt identity.

Ambiguous dispatch or terminal outcomes use the canonical layered action outcome and reconciliation semantics before retry.

## Progress and no-stall scheduling

Meaningful progress is evidence-backed change in task state, artifacts, execution, or a discriminating decision. Heartbeats, repeated status prose, and identical progress text are not meaningful by themselves.

Bound consecutive no-progress observations and stop/reconcile/replan when the limit is reached. Do not spin indefinitely on silent or no-op children.

After background dispatch, the parent continues any independent runnable work. It may yield for child evidence only when no independent parent work is currently runnable. The user must not need to send a message merely to resume work that was already admissible and independent of the child result.

## Terminal reconciliation

A child terminal label is one input, not parent evidence. Reconcile terminal state with expected artifacts, published revision, authoritative side-effect state, verification evidence, and the exact execution identity.

When `requires_work=true`, a child reporting completion without expected artifact/change evidence, authoritative no-change evidence, or another task-specific completion proof is `COMPLETED_NO_EVIDENCE`. Treat it as suspicious and reconcile; do not silently promote it to success.

Preserve `planning_base`, admitted `execution_base`, and any `published_revision` in the result. Verification for repository mutation binds to the published/execution revision actually produced, not the stale planning revision.

## Parent completion gate

Only the parent/task owner decides overall completion. Compare the current intent revision against evidence for every non-superseded mandatory requirement, required capability, required execution method, and acceptance criterion.

A requirement is not complete because a child said `done`, a command returned zero, a transport ACK arrived, or an artifact was merely published. Use the canonical layered outcome and verification contracts. Missing, stale, ambiguous, or identity-mismatched evidence blocks completion or requires reconciliation.

Superseded requirements stop blocking only when the ledger records the replacement and valid superseding authority. Newer intent invalidates an older completion decision until the new revision is evaluated.

## Parallel resource domains

Parallel delegates declare writer/resource domains before dispatch. Overlapping writer or stateful resource domains serialize unless a stronger domain-specific concurrency contract proves safe independence.

Read-only work may run concurrently when it cannot mutate shared state and its evidence remains bound to the correct revision. Parallelism is an optimization, never a reason to weaken target, authority, or evidence boundaries.

## Handoff and compaction

Handoff preserves compact authoritative state: ledger/task identity, `intent_revision`, unresolved requirement IDs, required capabilities/methods, scope boundaries, active durable child identities, admitted execution revisions, and evidence references needed to continue safely.

Do not replay the entire chat, satisfied requirement prose, full child prompts, or raw credentials when stable IDs and opaque references suffice. Compaction never converts `pending` or `blocked` into satisfied and never drops scope/prohibition state.

Secret taint survives handoff as metadata/opaque reference. Loaded skill identity and other runtime capabilities are reconciled separately against their current live state.

## Verification

Verification includes regressions for exact scope admission, protected/out-of-scope targets, no resource-pressure bypass, base drift and revalidation, least-authority child admission, dispatch-once, delta-only continuation, bounded no-progress, parent no-stall scheduling, parallel resource conflicts, terminal no-evidence detection, legitimate no-change evidence, compact handoff, and the parent completion gate.

Final evidence binds the current intent revision to the exact relevant source/artifact/runtime identities. Provider adapters are tested separately for truthful mapping into these portable contracts.
