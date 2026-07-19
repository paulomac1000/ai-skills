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

The decision engine emits one of these stable base provenance values:

- `local-policy`: reviewed consumer-owned configuration supplied with `trusted_policy: true`;
- `untrusted-risk-escalation`: untrusted explicit risk metadata raised the classification;
- `name-prefix-escalation`: an untrusted risk prefix in the public capability name raised the classification;
- `trusted-annotation`: an annotation from a server explicitly trusted for classification changed the result;
- `untrusted-annotation-escalation`: an untrusted annotation conservatively raised the result;
- `unknown`: no authoritative or conservative signal classified the capability.

When a separate trusted `sensitive: true` fact promotes `READ` or `UNKNOWN` to `SENSITIVE`, the engine appends `+sensitive` to the existing base value. Consumers should parse this as a base provenance plus an additive confidentiality marker rather than inventing undocumented source names.

The decision engine exposes provenance so policy and audit logs can distinguish why a risk was selected. New source values require a documented contract and regression test before release.

## Monotonic classification

Every additional signal is combined monotonically. It may preserve or raise the current compatibility risk projection but cannot replace it with a weaker result. In particular, `destructiveHint: true` must not turn an already `DANGEROUS` capability into merely `DESTRUCTIVE`.

Because confidentiality is partly orthogonal to side effects, the profile also retains the separate `sensitive` fact. A single compatibility enum is not a substitute for the server manifest's multi-axis safety contract.

## Downgrade rule

Only consumer-owned local policy or an explicitly trusted server annotation may reduce unknown risk to read-only. A tool named `[READ] export_all`, a description claiming no side effects, or `readOnlyHint: true` from an untrusted server remains unknown.

## Elevation rule

Untrusted evidence may raise risk. A destructive or dangerous prefix, schema accepting command text, or annotation indicating destructive behavior is sufficient to require stronger handling. Fail closed on disagreement and preserve the highest inferred class.

## Idempotency trust

A positive `idempotent: true` claim is safety-reducing because it can authorize automatic replay after an ambiguous failure. Accept it only from reviewed consumer-owned policy marked `trusted_policy: true` or a separately verified capability contract marked `trusted_contract: true`. Generic server trust used for display annotations does not prove idempotency. An untrusted `idempotent: false` claim may be retained because it can only disable retry and make behavior more conservative.

Retry still requires a retry-eligible error, an explicit positive retry signal, remaining attempt and deadline budget, preserved target identity, and any required refreshed precondition. Trusted idempotency alone never authorizes a retry.

## Sensitive reads

Read-only does not mean low-risk. Credentials, personal data, private messages, financial records, and internal configuration are sensitive even without mutation. Minimize fields, require purpose, and preserve server-side authorization.

## Confirmation

Confirmation names the exact effect, target, scope, and irreversibility. It is obtained close to invocation and is not silently reused for a broader operation. Confirmed workflows may cover repetitive bounded writes only when the user approved that exact workflow.

A model-controlled boolean or arbitrary tool argument is not confirmation. Runtime authorization must consume trusted caller/session context or a server-side approval record created through a separate trusted host, UI, or transport. Any presented approval handle must be opaque, short-lived, single-use when appropriate, and bound to the exact operation, principal, target, and resource.

## Verification

Test misleading names, every emitted provenance value, `+sensitive`, conflicting metadata, malicious annotations, dangerous-plus-destructive conflicts, untrusted positive idempotency, explicit legacy failures, sensitive reads, model-supplied confirmation attempts, and cross-server attempts to transfer authority.
