---
description: Trust-boundary and provenance model for MCP capability risk classification and confirmation.
doc_id: reference.mcp-consumer-risk-and-trust
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Run malicious-metadata scenarios proving untrusted signals cannot reduce risk or bypass confirmation.
---

# MCP consumer risk and trust

## Sources

Classifications have one of these sources:

- `local-policy`: reviewed consumer-owned configuration;
- `trusted-manifest`: contract from a server inside an explicit trust boundary;
- `trusted-annotation`: advisory metadata accepted because the server is trusted for classification;
- `untrusted-elevation`: remote text that raises concern but cannot prove safety;
- `unknown`: insufficient authoritative evidence.

The decision engine exposes provenance so policy and audit logs can distinguish why a risk was selected.

## Downgrade rule

Only consumer-owned local policy or an explicitly trusted server contract may reduce unknown risk to read-only. A tool named `[READ] export_all`, a description claiming no side effects, or `readOnlyHint: true` from an untrusted server remains unknown.

## Elevation rule

Untrusted evidence may raise risk. A destructive or dangerous prefix, schema accepting command text, or annotation indicating destructive behavior is sufficient to require stronger handling. Fail closed on disagreement.

## Sensitive reads

Read-only does not mean low-risk. Credentials, personal data, private messages, and internal configuration are sensitive even without mutation. Minimize fields, require purpose, and preserve server-side authorization.

## Confirmation

Confirmation names the exact effect, target, scope, and irreversibility. It is obtained close to invocation and is not silently reused for a broader operation. Confirmed workflows may cover repetitive bounded writes only when the user approved that exact workflow.

## Verification

Test misleading names, conflicting metadata, malicious annotations, sensitive reads, and cross-server attempts to transfer authority.
