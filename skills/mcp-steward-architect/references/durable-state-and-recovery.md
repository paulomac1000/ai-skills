---
description: Operational durability, storage, leasing, wake-up, fencing, and crash-recovery guidance for MCP Stewards.
doc_id: reference.mcp-steward-durable-state-recovery
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Exercise lease loss, lost wakeups, stale attempts, restart checkpoints, storage corruption, and the declared single- or multi-instance crash model with deterministic fault injection.
---

# Durable state and recovery

A Steward's core promise is continuity across request, worker, provider, and process failures. Treat storage as the authority and queues as wake-up hints.

## Canonical identities

Use separate identities for the semantic lineage, current job/generation, execution attempt, optimistic record version, and external operation. Do not overload one UUID to mean all of them.

A recheck/replan creates a new lineage generation when an older result could otherwise become actionable. A retry of the same operation normally creates a new attempt within the current generation. Stale attempts may clean up but cannot publish.

## Leases and wakeups

A running work item has a lease/fencing token and expiry. Recovery after expiry reacquires ownership through the durable store. Persist the durable work state and outbox/wakeup intent atomically where possible, then periodically scan due work so notification loss cannot orphan it.

A non-terminal job with no lease, no scheduled wakeup, no recoverable external handle, and no explicit blocked reason is orphaned and should be surfaced by `doctor`.

## Storage profiles

- constrained L1/single-owner: file storage only with atomic replacement, corruption quarantine, exclusive ownership, and explicit crash limits;
- durable single-instance: transactional SQLite/equivalent is the default baseline;
- multi-worker/multi-instance: transactional database with atomic leasing/CAS/equivalent.

Never hold the state transaction open while awaiting a remote provider.

## Recovery checkpoints

Inject failures before/after reservation, dispatch, remote acknowledgement, handle persistence, result persistence, verification, terminal transition, and notification. After restart the runtime should derive its next action from durable state rather than logs or model context.
