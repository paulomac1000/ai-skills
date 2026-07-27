---
description: Trust-boundary and provenance model for MCP capability risk classification, idempotency, and confirmation.
doc_id: reference.mcp-consumer-risk-and-trust
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Run malicious and conflicting metadata scenarios proving untrusted signals cannot reduce risk, claim replay safety, alter provenance silently, or bypass confirmation.
---

# MCP consumer risk and trust

## Sources

The decision engine emits one or more stable provenance values joined with `+`:

- `consumer-policy`: a typed consumer-owned policy supplied an authoritative risk;
- `consumer-contract`: a typed reviewed capability contract supplied an authoritative risk;
- `untrusted-risk-escalation`: discovered metadata raised the classification conservatively;
- `side-effect-escalation`: canonical `sideEffects` or legacy `side_effects` metadata raised compatibility risk conservatively;
- `name-prefix-escalation`: a public capability-name prefix raised the classification conservatively;
- `trusted-annotation`: a display annotation from an independently trusted server changed an otherwise unknown classification;
- `untrusted-annotation-escalation`: an untrusted annotation raised the classification;
- `sensitive`: discovered metadata conservatively raised confidentiality risk;
- `unknown`: no authoritative or conservative signal classified the capability.

Every new provenance value requires a documented contract and a regression test. Policy and audit consumers must not infer authority from a string that the server can supply.

## Trust-channel separation

Discovered capability metadata is always untrusted. Keys named `trusted_policy`, `trusted_contract`, `trusted_server`, `consumer_policy`, or similar have no authority inside that mapping.

Authoritative values arrive through typed consumer-owned objects:

- `TrustedCapabilityPolicy` for local reviewed policy;
- `TrustedCapabilityContract` for a pinned and separately verified contract.

Those objects carry the trusted risk and idempotency values themselves. A boolean must never upgrade fields from the untrusted metadata map. Server identity trust is a separate input used only for annotation interpretation; it does not make every metadata field authoritative.

## Monotonic classification

Every signal is combined monotonically. It may preserve or raise the current compatibility risk projection but cannot replace it with a weaker result. A destructive annotation cannot turn an already dangerous capability into merely destructive. A trusted local risk also does not suppress stronger conservative evidence discovered at runtime.

Confidentiality is partly orthogonal to side effects, so the profile retains a separate `sensitive` fact. A single compatibility enum is not a substitute for the server manifest's multi-axis safety contract.

## Downgrade rule

Only an explicit risk carried by typed consumer-owned policy or contract, or a read-only annotation from an independently trusted server, may classify an otherwise unknown tool as read-only. A tool named `[READ] export_all`, a description claiming no side effects, or `readOnlyHint: true` from an untrusted server remains unknown.

## Elevation rule

Untrusted evidence may raise risk. A destructive or dangerous prefix, a schema accepting command text, an explicit unsafe risk value, canonical or legacy side-effect metadata, or an annotation indicating destructive behavior is sufficient to require stronger handling. Canonical camelCase safety fields such as `requiresConfirmation` and supported snake_case compatibility aliases are interpreted monotonically: a positive confirmation signal or the highest side-effect class wins. Fail closed on disagreement and preserve the highest inferred class.

## Idempotency trust

A positive `idempotent: true` claim is safety-reducing because it can authorize automatic replay after an ambiguous failure. Accept it only from the `idempotent` field of a typed `TrustedCapabilityPolicy` or `TrustedCapabilityContract`. Never read positive replay safety from discovered metadata, even when the server itself is trusted for display annotations.

An untrusted `idempotent: false` claim may be retained because it only disables retry. Any explicit negative signal from policy, contract, manifest, or response wins over a positive signal.

Retry still requires a retry-eligible error, an explicit positive retry signal, remaining attempt and deadline budget, preserved target identity, proven operation idempotency, and any required refreshed precondition. Trusted idempotency alone never authorizes a retry.

## Sensitive reads

Read-only does not mean low-risk. Credentials, personal data, private messages, financial records, and internal configuration are sensitive even without mutation. Minimize fields, require purpose, preserve server-side authorization, and avoid caching protected output merely because the operation is read-only.

## Confirmation

Confirmation names the exact effect, target, scope, and irreversibility. It is obtained close to invocation and is not silently reused for a broader operation. Confirmed workflows may cover repetitive bounded writes only when the user approved that exact workflow.

A model-controlled boolean or arbitrary tool argument is not confirmation. Runtime authorization consumes trusted caller or session context, or a server-side approval record created through a separate trusted host, UI, or transport. Any presented approval handle is opaque, short-lived, bounded, and bound to the exact operation, principal, target, and resource.

## Verification

Test misleading names, every emitted provenance value, conflicting typed policy and discovered metadata, forged trust keys, wrong trust-object types, malicious annotations, dangerous-plus-destructive conflicts, canonical and compatibility side-effect fields, untrusted positive idempotency, explicit negative idempotency, malformed legacy failures, public package imports, sensitive reads, model-supplied confirmation attempts, and cross-server attempts to transfer authority.
