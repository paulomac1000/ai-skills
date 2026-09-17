---
description: Authority, candidate identity, state/effect matrices, and fail-closed mutation admission for MCP Stewards.
doc_id: reference.mcp-steward-authority-mutation-admission
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Validate mutation-policy contracts and execute negative admission tests for stale identity, lost authority, insufficient budget, ambiguous delivery, and candidate drift.
---

# Authority and mutation admission

This reference defines the shared fail-closed boundary for authority-bearing effects.

## State/effect matrix

For every mutation, record:

| Field | Meaning |
| --- | --- |
| transition/effect | semantic state transition and external/local effect |
| authority source | authenticated/contractual source that grants the action |
| lease requirement | exact owner/fence/expiry required at mutation time |
| subject identity | exact target/revision dimensions |
| candidate identity | immutable artifact/plan/config candidate, when applicable |
| capability proof | reviewed contract source/id/revision/digest |
| operation identity | durable operation/idempotency identity committed before dispatch |
| budget reserve | remaining wall-clock/call/cost capacity required to start |
| ambiguity path | reconciliation/compensation disposition |
| typed outcomes | admitted and fail-closed rejection classes |

Do not infer any authority-bearing value from friendly defaults such as `HEAD`, `latest`, `unknown`, a random GUID, requested lease duration, provider display text, or caller labels.

## Mutation Admission Gate

The application kernel owns one semantic gate used by every authority-bearing adapter call. A representative decision binds:

```text
job + lineage + captured generation + attempt
+ effective authority
+ authoritative lease/fence/expiry
+ exact subject
+ exact candidate
+ capability contract provenance
+ durable operation reservation
+ disclosure decision if applicable
+ remaining operation/finalization budget
+ unresolved ambiguity state
= typed mutation decision
```

The gate runs immediately before dispatch. If mutable facts can change between planning and dispatch, re-read them at this boundary.

`Admitted` is not a permanent token. It authorizes the exact effect identity/candidate/capability under the checked generation and budget. Any material identity/authority/capability change invalidates reuse.

## Pre-dispatch durability

For a stateful effect:

1. construct canonical request identity/digest;
2. evaluate mutation admission;
3. durably commit operation identity plus the admitted decision/fence;
4. commit succeeds;
5. only then invoke the adapter.

A receipt created after the provider call, or an operation object that existed only in memory when dispatch started, cannot resolve crash ambiguity.

## Lease truth

A lease is mutation authority. Renewal success is established only by authoritative storage/upstream state. Never synthesize expiry as `now + requestedDuration` unless that value is itself the authoritative lease contract. Unknown/ambiguous renewal blocks mutation.

Before a long effect, require enough authoritative lease/deadline margin for the bounded effect plus finalization reserve.

## CandidateIdentity

Verification/approval attaches to an immutable candidate, not merely a broad repository/project subject. A candidate can be a tree SHA, commit SHA, content digest, release bundle digest, deployment-plan digest, observed configuration snapshot, or equivalent immutable representation.

The publication gate re-computes/re-reads the candidate identity from the exact material to be published. Any mismatch forces revalidation or rejection.

## Invariant enforcement matrix

For each material invariant record:

```text
invariant
→ authoritative source
→ enforcement point
→ durable proof/event
→ typed failure outcome
→ negative regression
```

If a project cannot identify where an invariant is enforced on every applicable path, treat it as `PARTIAL`, even if a helper with a promising name exists.
