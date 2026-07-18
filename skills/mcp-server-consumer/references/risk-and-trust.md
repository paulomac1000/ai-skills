---
description: Trust-boundary and provenance model for MCP capability risk classification and confirmation.
doc_id: reference.mcp-consumer-risk-and-trust
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Run malicious and conflicting metadata scenarios proving untrusted signals cannot reduce risk, alter provenance silently, or bypass confirmation.
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

## Sensitive reads

Read-only does not mean low-risk. Credentials, personal data, private messages, financial records, and internal configuration are sensitive even without mutation. Minimize fields, require purpose, and preserve server-side authorization.

## Confirmation

Confirmation names the exact effect, target, scope, and irreversibility. It is obtained close to invocation and is not silently reused for a broader operation. Confirmed workflows may cover repetitive bounded writes only when the user approved that exact workflow.

## Verification

Test misleading names, every emitted provenance value, `+sensitive`, conflicting metadata, malicious annotations, dangerous-plus-destructive conflicts, sensitive reads, and cross-server attempts to transfer authority.