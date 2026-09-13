---
description: Operational contract for stateful upstream dispatch, delivery ambiguity, reconciliation, recovery, disclosure, and retry safety.
doc_id: reference.mcp-steward-external-reconciliation
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Inject failures around disclosure projection, receipt persistence, provider dispatch, acknowledgement loss, remote-handle persistence, and replay, then prove delivery-unknown never becomes an unverified resend and blocked data never reaches the external boundary.
---

# External operations and reconciliation

The hardest Steward failures occur after a side effect may have crossed the process boundary but before local state can prove what happened.

## Disclosure before dispatch

Before an outbound call crosses a confidentiality or trust boundary, build an explicit policy-approved projection for that destination/capability. Raw inbound/domain objects should not flow directly into external reasoning, research, review, browser, or provider adapters when they can contain private, mixed, unknown, or caller-controlled data.

A safe prompt envelope, role separation, instruction quoting, or prompt-injection filtering controls instruction semantics; none of those authorize disclosure. Treat disclosure as a separate policy decision executed before the provider call.

Prefer type-level separation such as `RawArticleContext -> DisclosureSafeArticleContext` or `IngressProposal -> PublicationSafeCandidate`. Unknown/mixed classification fails closed unless policy can construct a bounded redacted projection. Bind the projection to subject identity, relevant revision/generation, provider/capability, and disclosure-policy revision when those dimensions affect what is allowed to leave the trust boundary.

## Receipt before dispatch

Persist an `ExternalOperationReceipt` or equivalent start intent before stateful dispatch. Bind it to the job/generation/attempt, exact capability/target, canonical request digest, non-secret credential slot, and idempotency identity when one exists.

## Delivery states

Keep delivery separate from provider execution:

- `not-delivered`: local policy can prove the request was not dispatched or the provider definitively rejected it before effect;
- `delivered`: provider acceptance/delivery is established, even if later execution is still running;
- `delivery-unknown`: dispatch may have crossed the boundary but acknowledgement was lost or ambiguous.

`delivery-unknown` is not failure and not permission to retry. Reconcile using provider request ID, idempotency lookup, remote handle, status/query-by-key, independent target read-back, or another observed contract. If the provider cannot reconcile an operation whose replay may duplicate an effect, fail closed with explicit unresolved ambiguity.

## Observed remote handle but failed local binding

Treat these as two separate facts:

1. the remote system returned/observably assigned a handle or child identity;
2. the normal local transaction that binds that handle to the durable operation succeeded.

If (1) happened and (2) fails, never fall back to plain `reserved`, `not-delivered`, or another state that permits a second start. Preserve a recoverable `dispatch-observed / binding-uncertain / reconcile-required` state or equivalent. The observed handle should be retained through a crash-durable uncertainty record when possible; otherwise the adapter contract must support lookup by the durable operation/attempt/idempotency identity.

On recovery, prefer the observed/recovered remote handle and resume/status/cancel path. Starting replacement work is legal only after reconciliation proves the first dispatch cannot still produce the effect.

## Stateful versus one-shot upstreams

Classify every upstream operation before implementing the adapter. Durable remote jobs need start/status/result/cancel/recover semantics and should not be modeled as repeated stateless one-shot calls. A transport that launches a new process per call cannot be assumed to preserve in-process remote-job state.

For long-running upstreams, expose an observed progress/state marker when available. Repeated status with the same marker is liveness/observation, not semantic progress. Prefer bounded server-side wait/long-poll or next-poll guidance over workflows that require the model to generate repeated sleep/status turns.

## Retry

Retry requires eligible failure classification, remaining deadline/budget, stable target/capability identity, compatible idempotency/replay semantics, refreshed conflict preconditions when applicable, and no ambiguity veto. Retry inference/model reasoning separately from external side effects.

Credential failover does not erase delivery uncertainty. Provider/model substitution is also a separate policy decision: after any stateful dispatch that may have succeeded, changing credential/provider and repeating the operation is prohibited until reconciliation makes replay safe.

## Required adversarial tests

Include deterministic tests for:

- private/unknown sentinel fields that must never reach the fake outbound adapter;
- stateful dispatch succeeds, remote handle is returned, local binding persistence fails;
- response is lost after dispatch and retry is requested with another credential;
- restart with a recoverable remote handle resumes rather than submits again;
- repeated status returns the same progress marker and does not advance semantic progress.
