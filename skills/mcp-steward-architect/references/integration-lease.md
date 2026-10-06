---
description: Exact authority, mutation admission, one-shot dispatch, and reconciliation contract for autonomous repository integration.
doc_id: reference.mcp-steward-integration-lease
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Exercise exact principal/candidate/base/evidence admission, one-shot operation reservation, ambiguous-delivery reconciliation, squash lineage, replay fencing, and provider-neutral receipt projection.
---

# Integration lease

Use this profile when a Steward or other autonomous control plane may integrate a reviewed/verified candidate into a governed repository target. Generic repository write/push access is not integration authority. Candidate code, PR/change content, model output, workers, and provider display state cannot mint, widen, refresh, or delegate this authority.

## Exact authority envelope

An IntegrationLease is an authority-owned, bounded, one-shot grant. It binds at least:

- lease and authority-principal identity;
- repository and optional provider change identity;
- exact candidate head and optional tree identity;
- exact target ref and authoritative observed base;
- base policy and merge strategy;
- exact required evidence-set digest plus applicable review/verification policy revisions;
- autonomy policy revision and execution generation;
- issue/expiry and lifecycle state.

`active`, `used`, `revoked`, and `expired` are authority states, not model labels. A delegated implementation worker does not inherit a parent/control-plane lease unless the authority owner explicitly issues a lease to that principal. Branch protection, merge queues, required provider checks, and equivalent repository controls remain additional authoritative facts.

## Mutation admission

Immediately before reserving the integration operation, re-read authoritative current state and compare it with the lease:

```text
acting principal + execution generation + autonomy policy
repository/change identity + candidate head/tree
target ref + current base/topology
required review/verification evidence identity/currentness
provider integration controls
```

Only `INTEGRATION_ADMITTED` may progress to operation reservation. Candidate drift yields `STALE_CANDIDATE`; incompatible/unknown target movement yields `BASE_TOPOLOGY_CHANGED`; stale/missing evidence yields `EVIDENCE_STALE`; authority/generation/policy loss yields `LOST_AUTHORITY`; provider protection/controls yield `PROVIDER_BLOCKED`.

A compatible base advance is not implicit permission to merge. It may be classified `BASE_ADVANCED_COMPATIBLE`, but remains non-dispatching until the owning base/delivery policy performs its required revalidation, queue transition, or re-admission. Planning/execution-base topology remains owned by its canonical contract rather than this lease.

## One-shot reservation and replay fencing

Integration is a stateful external effect. Durable operation identity is reserved before the first provider byte is dispatched. Reservation atomically consumes the one-shot lease and binds it to that operation identity. A crash after reservation resumes/reconciles the same operation; it does not make the lease active again.

This prevents all of the following from authorizing a second dispatch:

- client timeout;
- lost acknowledgement;
- provider rejection;
- process restart;
- a stale worker/attempt;
- an already `used`, `revoked`, or `expired` lease.

A new dispatch after a conclusively non-integrated operation requires fresh policy-owned authority/re-admission. Replay safety is never inferred from a transport error.

## Ambiguous integration reconciliation

After dispatch, transport acknowledgement and repository reality remain distinct. `delivery-unknown` enters `RECONCILIATION_REQUIRED` and blocks replay. Reconciliation reads provider/change and target-ref state using the durable operation identity and exact candidate.

A successful reconciliation must establish all load-bearing facts needed for the chosen strategy, including exact candidate identity, target before/after identity, resulting integrated revision, and a strategy-appropriate lineage proof. If any required relation is unknown or contradictory, remain reconciliation-required.

For squash/rebase/merge transformations the integrated revision may differ from the verified candidate:

```text
candidate C + strategy squash + target B
→ authoritative integration observation
→ integrated I + lineage proof C → I
```

Consumers must not assume `C == I`.

## Evidence and receipt projection

The durable operation/result retains lease, principal/policy lineage through the lease, evidence-set digest, candidate head/tree, target/base, merge strategy, operation identity, and resulting integrated revision. It contains no repository credentials.

A bounded adapter may project the result into the cross-system execution-evidence model as an `integration` receipt containing candidate/integrated identities, lease and operation refs, target before/after, strategy, policy revisions, evidence-set digest, and lineage-proof ref. This profile defines integration authority; the execution-evidence contract owns broader delivery lineage and receipt correlation.

Manual/external integration may be recorded as an observed external transition by the evidence owner, but must not be retroactively represented as lease-authorized when no valid lease/operation existed.

## Provider neutrality

The contract uses repository/change/target/candidate/provider observations rather than a GitHub PR schema. GitHub pull requests, GitLab merge requests, Gerrit changes, Azure DevOps pull requests, and other providers may adapt their native identities and controls without becoming the wire model.

## Security boundary

Do not place credentials, tokens, cookies, or raw provider payloads in the lease/result. Untrusted repository/model content cannot supply authority principal, policy revision, provider-control verdict, exact evidence currentness, or authoritative reconciliation state. Large logs remain behind governed evidence refs.