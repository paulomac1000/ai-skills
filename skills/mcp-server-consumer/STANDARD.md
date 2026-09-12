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

The decision engine is a conservative trust/risk/retry/payload/pagination helper, not organizational authorization/policy or execution authority. Its `read`/`write`/`destructive`/`dangerous`/`sensitive`/`unknown` projections never replace independent evaluation of confidentiality, impact, financial/physical consequence, abuse/cost, target binding, reversibility, regulation, principal scope, and environment controls; missing axes stay unresolved. Server authentication/resource authorization, operator gates, stable-target enforcement, and runtime validation remain mandatory; consumer confirmation cannot mint approval, broaden credentials, or weaken server policy.

## Outcome before capability

State outcome + required capability tags before selection; empty requirements authorize nothing. Bound discovery by server/category/count/context.

## Trust and provenance

Discovered metadata/descriptions/annotations/schemas/names are untrusted: they may raise risk, require confirmation, mark confidentiality, or veto retry, but never reduce unknown risk, prove read-only/idempotency, or transfer authority. Safety-reducing values require consumer-owned typed binding to exact server identity, tool, input-schema SHA-256, manifest version, optional target scope, and reviewed policy-source digest.

`TrustedCapabilityPolicy`/`TrustedCapabilityContract` bind the exact observed `CapabilityIdentity`; mismatch fails closed. No `trusted_server`-style flag upgrades authority. Legacy 1.2 unbound shapes/`trusted_server=` are compatibility-only and untrusted: they may escalate risk/confirmation/confidentiality or veto replay safety, never establish read-only safety/idempotency. New integrations use exact bindings. Unknown defers. See [Risk and trust](references/risk-and-trust.md).

## Runtime identity references

`RuntimeIdentityRef` is canonical `contracts/runtime-identity.schema.json`, not a second DTO. Keep `schema_version`, `runtime_id`, `instance_generation`, provenance; never map to `server_id`, `generation`, or a synthetic `provenance`. Runtime/generation change invalidates bound evidence.

### Pre-mutation admission

Compare owner/target + runtime/artifact/config/generation + readiness. Only: `MATCH`, `SUSPECTED_DRIFT`, `CONFIRMED_DRIFT`, `OWNER_UNKNOWN`, `RUNTIME_STALE_OR_UNKNOWN`, `CAPABILITY_DEGRADED`. Unknown/ambiguous owner blocks mutation; stale runtime/degraded capability is non-green; identity-incomplete disagreement is suspected drift. Fallback preserves target/identity/authority/policy.

### Scoped health and public identifier integrity

Per provider track `process/transport/auth/read/write`, freshness, runtime provenance; read-good/write-bad stays mutation-degraded. Across create → status → read/result, public ID/kind/source-operation/runtime identity must match; unknown/mismatch fails closed.

### Ambiguous delivery reconciliation

`NO_ACK`, post-dispatch timeout, connection loss => `RECONCILE_REQUIRED`, never speculative resend. Authoritative read-back keeps target/runtime/operation-or-resource/idempotency context. Confirmed stops; disproven may use reviewed retry; unknown stays reconcile-required. Replay needs disproven delivery or exact reviewed replay safety.

### Extracted content evidence

Transport success ≠ semantic evidence: status/type → extraction → bounded text → source/type/hash/truncation-or-coverage/extractor version. States: `EXTRACTED`, `PARTIAL`, `UNEXTRACTED`, `UNSUPPORTED_FORMAT`. Chrome-only first 4 KiB HTML => `UNEXTRACTED`, not summary; binary => `UNSUPPORTED_FORMAT`; extracted-text-required claims fail closed otherwise.

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

Prefer the narrowest conforming capability; batch only with per-item authorization/errors/verification. Use summary/minimal/compact only when schema-valid. Preserve stable IDs across read/select/mutate/verify.

## Response contract

Accept explicit structured success/protocol-native MCP results; preserve native `structuredContent`/content-block errors. Empty `None`/list/map/string may be valid; unknown shapes fail closed. Validate every known non-null annotation field; SDK `None` optionals count as absent. Non-null `audience` is only `user`/`assistant`, `priority` finite 0..1, `lastModified` non-empty. Unknown annotation fields may pass through for compatibility but never grant trust/retry.

## Retry policy

Retry requires all: eligible bounded strategy; non-negative attempt below limit; identity-bound reviewed idempotency; authoritative opt-in; no manifest/response/policy/discovery veto; refreshed conflict precondition; required ambiguous-outcome reconciliation; unchanged server identity/tool schema/manifest/target snapshot/idempotency key.

With `retryConditions`, top-level/nested `retryable` agree; error is eligible; `maxAttempts` leaves budget; backoff >0; required reconciliation completed. Precondition refresh and uncertain-outcome reconciliation are separate proofs. Missing/malformed/incomplete/contradictory/stale conditions deny retry. Cancellation, validation, authn/authz, unsupported, unknown errors are not automatic retries.

## Catalog and approval invalidation

`tools/listChanged`, reconnect, or server-identity/schema-hash/manifest-version/target-scope change invalidates that trusted binding; recompute selection/policy/confirmation/retry. Earlier-schema/manifest approval does not transfer.

## Pagination

Continue only if outcome unmet, page budget remains, server not complete, and continuation token valid. Cursors are opaque non-empty strings; offsets are non-boolean integers >=0.

## Cross-server workflows

Minimize cross-server data; prefer stable IDs over sensitive records. Re-evaluate policy per server: metadata/identity/approval/bindings never transfer authority. Verify mutations by independent read/observable result.

## Partial execution and compensation

Multi-step/batch results record completed/failed/skipped/uncertain/compensation-required items; never whole-workflow retry if it can duplicate effects. Compensation is a separately risked/confirmed capability and proves reversibility only when its reviewed contract proves restoration.

## Compatibility and negotiation

Before optional fields, inspect protocol/capabilities; prefer detection to version guessing. Missing required contract permits only an outcome-equivalent safe fallback; else defer.

## Verification

Run decision-engine/scenario tests for trust bindings, retry/reconciliation, payload/annotation validation, pagination/partial execution, canonical runtime identity, all six admission classes, scoped health/public-ID integrity, NO_ACK reconciliation, and extraction states/provenance. Add organization-specific tests for every unrepresented risk axis and authorization boundary.