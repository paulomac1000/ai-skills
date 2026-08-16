---
afds_schema_version: 2
description: Trust-boundary and provenance model for MCP capability risk classification, idempotency, and confirmation.
doc_id: reference.mcp-consumer-risk-and-trust
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification:
  kind: command
  value: Run malicious and conflicting metadata scenarios proving untrusted signals cannot reduce risk, claim replay safety, alter provenance silently, or bypass confirmation.
---

# MCP consumer risk and trust

## Sources

The decision engine emits one or more stable provenance values joined with `+`:

- `consumer-policy:<immutable-source>`: identity-bound consumer policy supplied an authoritative risk;
- `consumer-contract:<immutable-source>`: an identity-bound reviewed contract supplied an authoritative risk;
- `legacy-unbound-policy-escalation`: a compatibility-only 1.2 policy object raised risk conservatively without creating authority;
- `legacy-unbound-contract-escalation`: a compatibility-only 1.2 contract object raised risk conservatively without creating authority;
- `untrusted-risk-escalation`: discovered metadata raised classification conservatively;
- `side-effect-escalation`: canonical or compatibility side-effect metadata raised risk conservatively;
- `name-prefix-escalation`: a public capability-name prefix raised classification conservatively;
- `untrusted-annotation-escalation`: an untrusted destructive annotation raised classification;
- `sensitive`: the resulting profile carries confidentiality risk, whether that signal came from policy or discovered metadata and even when a stronger side-effect risk remains the ordered risk value;
- `unknown`: no authoritative or conservative signal classified the capability.

There is no `trusted-annotation` provenance. Server identity alone does not make annotations authoritative. Every new provenance value requires a documented contract and regression test. Policy and audit consumers must not infer authority from a string the server can supply.

## Trust-channel separation

Discovered capability metadata is always untrusted. Keys named `trusted_policy`, `trusted_contract`, `trusted_server`, `consumer_policy`, or similar have no authority inside that mapping.

Authoritative values arrive through immutable consumer-owned objects:

- `CapabilityIdentity` identifies the exact server, tool name, tool-schema SHA-256, manifest version, and optional target scope observed for the selected capability;
- `TrustedPolicyBinding` binds that identity to an immutable reviewed source digest;
- `TrustedCapabilityPolicy` carries local policy values under that binding;
- `TrustedCapabilityContract` carries separately reviewed contract values under that binding.

Conforming callers bind policy and contract values to the exact observed identity. For migration compatibility, the reference helper still accepts the 1.2 unbound policy/contract constructor shapes and `trusted_server=` keyword, but these legacy inputs are not authoritative: they may only raise risk, require confirmation, mark confidentiality, or veto positive replay safety. They cannot classify unknown risk as read-only or establish positive idempotency. A bound trusted value without the exact observed identity, or any mismatch in server identity, tool name, schema hash, manifest version, or target scope, is an error rather than a warning or fallback. A boolean can never upgrade fields from the untrusted metadata map.

## Monotonic classification

Every discovered signal combines monotonically. It may preserve or raise the current compatibility risk projection but cannot replace it with a weaker result. A destructive annotation cannot turn an already dangerous capability into merely destructive. A trusted local risk also does not suppress stronger conservative evidence discovered at runtime.

Confidentiality is partly orthogonal to side effects, so the profile retains a separate `sensitive` fact. A single compatibility enum is not a substitute for the server manifest's multi-axis safety contract.

## Downgrade rule

Only a risk carried by an identity-bound `TrustedCapabilityPolicy` or `TrustedCapabilityContract` may classify an otherwise unknown capability as read-only. A capability named `[READ] export_all`, a description claiming no side effects, discovered `risk: READ`, or `readOnlyHint: true` remains unknown without an exact trusted binding.

Trusting a server certificate, repository, package, or transport does not automatically trust every annotation. Pinning server identity and reviewing capability policy are separate decisions.

## Elevation rule

Untrusted evidence may raise risk. A destructive or dangerous prefix, a schema accepting command text, an explicit unsafe risk value, canonical or compatibility side-effect metadata, or a destructive annotation is sufficient to require stronger handling. Canonical camelCase safety fields such as `requiresConfirmation` and supported snake_case compatibility aliases are interpreted monotonically: a positive confirmation signal or the highest side-effect class wins. Fail closed on disagreement and preserve the highest inferred class.

## Idempotency trust

A positive `idempotent: true` claim is safety-reducing because it can authorize automatic replay after an ambiguous failure. Accept it only from the `idempotent` field of an identity-bound `TrustedCapabilityPolicy` or `TrustedCapabilityContract`. Never read positive replay safety from discovered metadata.

An untrusted `idempotent: false` claim may be retained because it only disables retry. Any explicit negative signal from policy, contract, manifest, or response wins over a positive signal.

Retry still requires a retry-eligible error, an explicit positive retry signal, remaining attempt and deadline budget, preserved target identity, proven operation idempotency, and any required refreshed precondition. Trusted idempotency alone never authorizes retry.

## Binding lifecycle

A binding is invalidated when any bound dimension changes, including:

- reconnect to a different server identity;
- `tools/listChanged` or another catalog change affecting the tool;
- input-schema hash change;
- manifest-version change;
- target-scope change;
- policy-source rotation or expiry.

The consumer re-evaluates policy and obtains a new binding before invocation. A previous approval or retry receipt is not automatically valid under the new binding.

## Sensitive reads

Read-only does not mean low-risk. Credentials, personal data, private messages, financial records, and internal configuration are sensitive even without mutation. Minimize fields, require purpose, preserve server-side authorization, and avoid caching protected output merely because the operation is read-only.

## Confirmation

Confirmation names the exact effect, target, scope, schema, manifest version, and irreversibility. It is obtained close to invocation and is not silently reused for a broader operation. Confirmed workflows may cover repetitive bounded writes only when the user approved that exact workflow.

A model-controlled boolean or arbitrary tool argument is not confirmation. Runtime authorization consumes trusted caller or session context, or a server-side approval record created through a separate trusted host, UI, or transport. Any presented approval handle is opaque, short-lived, bounded, and bound to the exact operation, principal, target, resource, normalized arguments digest, tool schema, and manifest version.

## Verification

Test misleading names, every emitted provenance value, conflicting bound policy and discovered metadata, forged trust keys, removed boolean trust channels, wrong trust-object types, mismatched server/tool/schema/manifest/target bindings, malicious annotations, dangerous-plus-destructive conflicts, canonical and compatibility side-effect fields, untrusted positive idempotency, explicit negative idempotency, malformed legacy failures, public package imports, sensitive reads, model-supplied confirmation attempts, catalog changes, and cross-server attempts to transfer authority.
