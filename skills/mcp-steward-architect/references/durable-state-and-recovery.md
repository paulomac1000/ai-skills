---
description: Operational durability, storage, leasing, wake-up, fencing, and crash-recovery guidance for MCP Stewards.
doc_id: reference.mcp-steward-durable-state-recovery
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Exercise lease loss, lost wakeups, stale attempts, captured-generation successor races, canonical artifact recovery, restart checkpoints, storage corruption, and the declared single- or multi-instance crash model with deterministic fault injection.
---

# Durable state and recovery

A Steward's core promise is continuity across request, worker, provider, and process failures. Treat storage as the authority and queues as wake-up hints.

## Canonical identities

Use separate identities for the semantic lineage, current job/generation, execution attempt, optimistic record version, and external operation. Do not overload one UUID or one monotonically increasing field to mean all of them.

A recheck/replan creates a new lineage generation when an older result could otherwise become actionable. A retry of the same operation normally creates a new attempt within the current generation. Stale attempts may clean up but cannot publish.

Optimistic state version and semantic work generation serve different purposes. State version orders/CAS-protects ordinary mutations. Work generation is an invalidation epoch: it advances when previously admitted work or its actionable result must become stale. A system may name these fields differently, but an ordinary state transition must not accidentally create a fresh work epoch for stale work.

## Captured-generation rule

When a worker or stage is admitted, claimed, or resumed, capture the semantic generation that authorizes that work. Treat it as an input to the work, not something to look up again from the latest subject row when scheduling successors.

Propagate the captured generation through:

- successor job enqueue;
- deferred continuation and recovery records;
- projections and derived artifacts;
- external side-effect authorization;
- completion candidates and terminal publication.

If the generation advanced before one of those operations, the old worker must fail closed/stale rather than enqueue work tagged with the new generation. Persistence code must never silently substitute `current_generation` for `expected_generation` supplied by the caller. This prevents old work from adopting the cancellation/withdraw/replan epoch that was created specifically to invalidate it.

For projections that also need ordering inside one work generation, carry both the expected work generation and the expected state/version identity.

## Read consistency versus optimistic write fencing

CAS protects the write; it never repairs the read. A decision composing several authoritative
records must observe one consistent snapshot or carry a read-set atomically revalidated before
it becomes actionable — parent at generation N with children at N+1 is a torn read even when
every write CAS-succeeded. Stateful admission controllers version decisions with an epoch;
older-epoch completions are history only and never grant current capability/readiness/authority.

## Canonical-first persisted state

Retry safety requires more than deduplicating writes. If a stable stage/artifact identity already owns canonical artifact A and a retry computes different artifact B, a no-op insert/CAS loss/dedupe result must return or reload A. All downstream gates, successor jobs, evidence, and handoffs consume A or its canonical reference/digest.

Do not let a losing retry continue with B merely because the database correctly refused to overwrite A. After restart between artifact persistence and successor scheduling, recovery first reads the canonical persisted artifact, then derives the next step from that value.

Useful persistence APIs therefore return one of:

- the value/reference just committed;
- the already-existing canonical value/reference that won the stable identity;
- a typed stale/conflict result that prevents downstream execution.

A bare `void`/success result from `insert-if-absent` is unsafe when the caller can retain a different attempt-local value.

## Leases and wakeups

A running work item has a lease/fencing token and expiry. Recovery after expiry reacquires ownership through the durable store. Persist the durable work state and outbox/wakeup intent atomically where possible, then periodically scan due work so notification loss cannot orphan it.

A non-terminal job with no lease, no scheduled wakeup, no recoverable external handle, and no explicit blocked reason is orphaned and should be surfaced by `doctor`.

## Storage profiles

- constrained L1/single-owner: file storage only with atomic replacement, corruption quarantine, exclusive ownership, and explicit crash limits;
- durable single-instance: transactional SQLite/equivalent is the default baseline;
- multi-worker/multi-instance: transactional database with atomic leasing/CAS/equivalent.

Never hold the state transaction open while awaiting a remote provider.

## Recovery checkpoints

Inject failures before/after reservation, generation capture, successor enqueue, dispatch, remote acknowledgement, handle persistence, canonical artifact persistence, result observation, verification, terminal transition, and notification. After restart the runtime should derive its next action from durable state rather than logs, attempt-local variables, or model context.

At minimum prove these recovery cases:

1. old worker captures generation N; invalidation advances to N+1; old worker cannot schedule a successor as N+1;
2. attempt 1 persists canonical artifact A; retry computes B; downstream still consumes A;
3. canonical artifact is committed and the process dies before successor scheduling; restart schedules from the persisted artifact without recomputing a different canonical result;
4. lease expires during external wait; recovery resumes/reconciles without allowing both old and new owners to publish.
