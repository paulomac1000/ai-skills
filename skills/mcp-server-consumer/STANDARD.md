---
afds_schema_version: 2
description: Normative policy for safe, efficient, and verifiable MCP capability consumption.
doc_id: reference.mcp-consumer-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Run `python -m pytest tests/test_decision_engine.py tests/test_consumer_payload_validation.py tests/test_consumer_retry_and_annotations.py` and exercise representative read, write, partial-failure, pagination, and cross-server workflows.
---

# MCP consumer standard

## Purpose

Define deterministic safety and efficiency rules for consumers that operate across servers with different trust, maturity, and response contracts.

## Scope and non-goals

The bundled decision engine is a conservative reference helper for monotonic trust, risk, retry, payload, and pagination decisions. It is not a complete organizational authorization or policy engine and its return value is never sufficient authority to execute an operation.

The helper intentionally compresses some decisions into compatibility projections such as `read`, `write`, `destructive`, `dangerous`, `sensitive`, and `unknown`. Production policy must independently evaluate applicable confidentiality, operational impact, financial or physical consequence, cost and abuse potential, target binding, reversibility, regulatory class, principal scope, and environment-specific controls. Missing axes remain unresolved; they are not inferred as safe.

Server-side authentication, resource authorization, operator gates, stable-target enforcement, and runtime validation remain mandatory even when the consumer permits or confirms an invocation. A consumer confirmation cannot mint server approval, broaden credentials, or downgrade server policy.

## Outcome before capability

State the desired outcome and required capability tags before tool selection. Empty requirements do not authorize an arbitrary tool. Discovery is bounded by server, category, count, and context budget.

## Trust and provenance

Discovered server metadata, descriptions, annotations, schemas, and names are untrusted policy inputs. They may raise risk, require confirmation, mark confidentiality, or veto retry. They cannot reduce unknown risk, establish read-only safety, claim idempotency, or transfer authority between servers.

Safety-reducing values come only from consumer-owned typed objects bound to an exact capability identity:

- server identity;
- tool name;
- input-schema SHA-256;
- manifest version;
- optional target scope;
- immutable reviewed policy-source digest.

`TrustedCapabilityPolicy` and `TrustedCapabilityContract` require that binding. The caller supplies the exact observed `CapabilityIdentity`; any mismatch fails closed. There is no boolean `trusted_server` or equivalent authority-upgrade channel. Trusting a server connection does not trust every annotation or policy value emitted by that server.

For migration compatibility only, the bundled reference helper may still accept the 1.2 unbound policy/contract constructor shapes and `trusted_server=` keyword. Those legacy inputs are treated as untrusted at the compatibility boundary: they may only escalate risk, require confirmation, mark confidentiality, or veto positive replay safety. They never establish read-only safety or positive idempotency. New conforming integrations use exact identity bindings.

Unknown remains unknown and defers rather than invokes. See [Risk and trust](references/risk-and-trust.md).

## Runtime identity references

`RuntimeIdentityRef` is the canonical object from `contracts/runtime-identity.schema.json`, not a second DTO. Preserve and validate `schema_version`, `runtime_id`, `instance_generation`, and canonical provenance fields. Do not translate them to alternate keys such as `server_id`, `generation`, or a synthetic `provenance` object.

A changed `runtime_id` or `instance_generation` invalidates generation-bound evidence. `tools/runtime_identity_ref.py` validates the canonical object and returns its canonical runtime/generation key.

### Pre-mutation admission

Resolve owner/target, observe canonical runtime/artifact/config/generation and action readiness, then compare live with expected evidence. Classify only as `MATCH`, `SUSPECTED_DRIFT`, `CONFIRMED_DRIFT`, `OWNER_UNKNOWN`, `RUNTIME_STALE_OR_UNKNOWN`, or `CAPABILITY_DEGRADED`. Unknown owner or ambiguous target blocks mutation; stale/unknown runtime and degraded capability are non-green; disagreement without exact identity is suspected drift. Fallback preserves target, identity, authority, and policy.

### Scoped health and public identifier integrity

Health is per-provider `process/transport/auth/read/write`, freshness, and canonical runtime provenance. Read-ready/write-degraded remains mutation-degraded, never whole-service green. Public IDs carry kind, source operation, and canonical runtime identity; create → status → read/result preserves the same ID/kind/runtime key. Unknown or mismatched handoff fails closed.

### Ambiguous delivery reconciliation

`NO_ACK`, post-dispatch timeout, or connection loss means `RECONCILE_REQUIRED`, never speculative resend. Authoritative provider/resource read-back uses the same target, runtime, operation/resource identity, and idempotency context. Confirmed delivery stops; disproven delivery may enter reviewed retry policy; unknown stays reconciliation-required. Replay requires disproven delivery or an exact reviewed replay-safe contract.

### Extracted content evidence

Transport success is not semantic evidence: validate status/type → extract by format → bound semantic text → attach source, type, hash, truncation/coverage, and extractor version. States are `EXTRACTED`, `PARTIAL`, `UNEXTRACTED`, `UNSUPPORTED_FORMAT`. A chrome-only first 4 KiB of HTML is `UNEXTRACTED`, not a summary; unsupported binary stays `UNSUPPORTED_FORMAT`. Claims may require extracted text and fail closed otherwise.

## Decision policy

| Risk | Default behavior |
| --- | --- |
| read | invoke unless local policy requires confirmation |
| sensitive | confirm unless explicit approved workflow permits it |
| write | confirm unless an already confirmed workflow covers the exact mutation |
| destructive | confirm immediately before invocation |
| dangerous | reject unless explicitly requested by capability name, then confirm |
| unknown | defer or reject; never auto-invoke |

Server-side authorization remains mandatory regardless of consumer decision.

## Efficient selection

Prefer the narrowest capability with the required contract. Prefer batch only when it preserves per-item authorization, error visibility, and verification. Start with summary, minimal, or compact parameters only when the schema accepts those values. Preserve stable identifiers between read, select, mutate, and verify steps.

## Response contract

Recognize explicit structured success and protocol-native MCP results. Preserve native error detail from `structuredContent` or content blocks. Empty `None`, list, map, or string may be a meaningful success. Unrecognized shapes fail closed.

Validate every known non-null field of content-block annotations before accepting either success or error content. Nullable optional fields emitted as `None` by an official SDK are treated as absent. `audience`, when non-null, is an array containing only `user` and `assistant`; `priority`, when non-null, is a finite number from zero through one; `lastModified`, when non-null, is a non-empty string. Unknown annotation fields remain available for forward-compatible extensions and never grant trust or retry permission.

## Retry policy

Retry only when:

- the error strategy permits a bounded retry;
- the attempt is a non-negative integer below the limit;
- the operation is idempotent under an identity-bound reviewed contract;
- at least one authoritative signal explicitly opts in;
- no manifest, response, policy, or discovered signal explicitly vetoes retry;
- a conflict precondition has been refreshed before retry;
- an ambiguous earlier outcome has been reconciled when required;
- server identity, tool schema, manifest version, target snapshot, and idempotency key still match the retry receipt.

When a manifest includes `retryConditions`, top-level and nested `retryable` values must agree. The current error must appear in the eligible-error list, `maxAttempts` must leave another invocation in the total budget, backoff must be positive, and required reconciliation must have completed. Precondition refresh and uncertain-outcome reconciliation are independent proofs: one cannot satisfy the other. Missing, malformed, incomplete, contradictory, or stale conditions deny retry.

Cancellation, validation, authentication, authorization, unsupported behavior, and unknown errors are not automatically retried.

## Catalog and approval invalidation

A `tools/listChanged` notification, reconnect, server-identity change, schema-hash change, manifest-version change, or target-scope change invalidates the corresponding trusted binding. Tool selection, policy evaluation, confirmation, and retry planning must be recomputed. An approval for an earlier schema or manifest is not automatically valid for the replacement capability.

## Pagination

Continue only when the outcome is not satisfied, the page budget remains, the server has not declared completion, and a valid continuation token exists. Cursors are non-empty strings. Offsets are non-boolean integers greater than or equal to zero. Treat cursors as opaque.

## Cross-server workflows

Minimize data transfer between servers. Pass stable identifiers instead of whole sensitive records where possible. Re-evaluate policy at each server boundary. Do not let one server's metadata, identity, approval, or policy binding authorize another server's tool. Verify mutations through an independent read or observable result.

## Partial execution and compensation

For multi-step or batch operations, record completed, failed, skipped, uncertain, and compensation-required items. Do not retry the whole workflow when that would duplicate completed effects. Compensation is an explicit capability with its own risk and confirmation policy. A compensating action does not make the original operation reversible unless its reviewed contract proves the relevant effects are restored.

## Compatibility and negotiation

Inspect protocol and capability versions before relying on optional fields. Prefer capability detection over version guessing. When the required contract is unavailable, select a safe fallback only if it still satisfies the outcome; otherwise defer.

## Verification

Run decision-engine/scenario tests for trust bindings, retry/reconciliation, payload/annotation validation, pagination/partial execution, canonical runtime identity, all six admission classes, scoped health/public-ID integrity, NO_ACK reconciliation, and extraction states/provenance. Add organization-specific tests for every unrepresented risk axis and authorization boundary.