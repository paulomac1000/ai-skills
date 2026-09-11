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

Before a high-impact operation, resolve canonical owner and target, observe current runtime/artifact/config/instance identity, inspect readiness for the required action class, then compare live evidence with expected evidence. Classify deterministically as `MATCH`, `SUSPECTED_DRIFT`, `CONFIRMED_DRIFT`, `OWNER_UNKNOWN`, `RUNTIME_STALE_OR_UNKNOWN`, or `CAPABILITY_DEGRADED`. Incomplete identity plus disagreement is suspected rather than fabricated certainty. Unknown owner or ambiguous target blocks mutation; stale/unknown runtime and degraded required capability are non-green. Live runtime evidence outranks stale documentation, and fallback must preserve target, identity, credentials/authority, and policy rather than switching endpoints to make the call succeed.

### Scoped health and public identifier integrity

Health is a typed per-provider matrix: process, transport, auth, read, and write/action-class state remain distinct and carry freshness plus canonical runtime/generation provenance when available. A successful read cannot imply write readiness; `read=ready, write=degraded` remains degraded for mutation and never becomes whole-service `healthy=true`. Stale or unknown health is non-authoritative.

A public identifier is handed off with its namespace/kind, source operation, and canonical runtime identity. A documented create → status → read/result lifecycle must preserve the same typed resource identity; equal-looking strings from different namespaces are not interchangeable. An immediate unknown/mismatched ID after successful creation is a contract failure unless documented namespace/retention semantics explain it, and consumers fail closed rather than guessing an alternate identifier.

### Ambiguous delivery reconciliation

Transport acknowledgement is evidence, not final side-effect truth. After `NO_ACK`, timeout-after-dispatch, connection loss, or another ambiguous send/write outcome, the consumer enters `RECONCILE_REQUIRED` and must not speculatively resend. Use the authoritative provider/resource read-back with bounded waiting and the same target, canonical runtime identity, operation/resource identity, and idempotency context. Read-back-confirmed delivery stops with no duplicate retry; disproven delivery may enter normal retry policy; still-unknown state remains reconciliation-required. Retry is allowed only after delivery is disproven or an exact reviewed idempotency contract proves replay safe.

### Extracted content evidence

For research/content tools, HTTP success and raw bytes are not semantic evidence. The flow is transport response → status/content-type validation → format-appropriate extraction → bounded semantic text → evidence with source locator, fetched freshness where available, content type, extractor/method version, extraction state, truncation/coverage, and content hash. States are `EXTRACTED`, `PARTIAL`, `UNEXTRACTED`, and `UNSUPPORTED_FORMAT`. An arbitrary HTML prefix—such as the first 4 KiB containing navigation/chrome—remains `UNEXTRACTED`, never a summary. Extractor failure is typed partial/unextracted, and binary/non-text content follows a format-specific path or remains `UNSUPPORTED_FORMAT`; downstream claims may require extracted content and fail closed otherwise.

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

Run decision-engine and scenario tests covering boolean trust-channel rejection, exact binding matches and mismatches, trust downgrade attempts, conflicting retry signals, nested retry constraints, conflict refresh, independent reconciliation proof, native and malformed error content, nullable SDK fields, annotation validation, schema-aware detail selection, catalog invalidation, pagination limits, partial execution, cross-server data boundaries, canonical runtime-identity reference validation, all six admission classifications, scoped read/write health, public-ID handoff integrity, NO_ACK reconciliation, and extraction-state/provenance handling. Add organization-specific tests for every risk axis and authorization boundary not represented by the reference helper.