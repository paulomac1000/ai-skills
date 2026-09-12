---
description: Operational contract for stateful upstream dispatch, delivery ambiguity, reconciliation, recovery, and retry safety.
doc_id: reference.mcp-steward-external-reconciliation
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Inject failures around receipt persistence, provider dispatch, acknowledgement loss, remote-handle persistence, and replay, then prove delivery-unknown never becomes an unverified resend.
---

# External operations and reconciliation

The hardest Steward failures occur after a side effect may have crossed the process boundary but before local state can prove what happened.

## Receipt before dispatch

Persist an `ExternalOperationReceipt` or equivalent start intent before stateful dispatch. Bind it to the job/generation/attempt, exact capability/target, canonical request digest, non-secret credential slot, and idempotency identity when one exists.

## Delivery states

Keep delivery separate from provider execution:

- `not-delivered`: local policy can prove the request was not dispatched or the provider definitively rejected it before effect;
- `delivered`: provider acceptance/delivery is established, even if later execution is still running;
- `delivery-unknown`: dispatch may have crossed the boundary but acknowledgement was lost or ambiguous.

`delivery-unknown` is not failure and not permission to retry. Reconcile using provider request ID, idempotency lookup, remote handle, status/query-by-key, independent target read-back, or another observed contract. If the provider cannot reconcile an operation whose replay may duplicate an effect, fail closed with explicit unresolved ambiguity.

## Stateful versus one-shot upstreams

Classify every upstream operation before implementing the adapter. Durable remote jobs need start/status/result/cancel/recover semantics and should not be modeled as repeated stateless one-shot calls. A transport that launches a new process per call cannot be assumed to preserve in-process remote-job state.

## Retry

Retry requires eligible failure classification, remaining deadline/budget, stable target/capability identity, compatible idempotency/replay semantics, refreshed conflict preconditions when applicable, and no ambiguity veto. Retry inference/model reasoning separately from external side effects.
