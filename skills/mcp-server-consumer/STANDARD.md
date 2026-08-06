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

`TrustedCapabilityPolicy` and `TrustedCapabilityContract` require that binding. The caller supplies the exact observed `CapabilityIdentity`; any mismatch fails closed. There is no boolean `trusted_server` or equivalent upgrade channel. Trusting a server connection does not trust every annotation or policy value emitted by that server.

Unknown remains unknown and defers rather than invokes. See [Risk and trust](references/risk-and-trust.md).

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

Run decision-engine and scenario tests covering boolean trust-channel rejection, exact binding matches and mismatches, trust downgrade attempts, conflicting retry signals, nested retry constraints, conflict refresh, independent reconciliation proof, native and malformed error content, nullable SDK fields, annotation validation, schema-aware detail selection, catalog invalidation, pagination limits, partial execution, and cross-server data boundaries. Add organization-specific tests for every risk axis and authorization boundary not represented by the reference helper.
