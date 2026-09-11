---
afds_schema_version: 2
description: Stable classification rules for runtime facts and symbolic capability ownership in AGENTS.md.
doc_id: reference.agents-md-runtime-facts
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Run runtime-fact classification and AGENTS.md audit regressions.
---

# Runtime facts in AGENTS.md

## Fact classes

Classify runtime guidance as one of: stable invariant, compatibility contract, logical capability owner, volatile observation, or private binding. AGENTS.md may state durable invariants and compatibility ranges. A volatile observation may be recorded only when explicitly labeled as an observation rather than timeless routing truth. Private IP/port bindings require a scoped justification such as a local fixture or runtime discovery rule.

## Symbolic capability ownership

Prefer a symbolic capability-owner contract: name the logical capability owner, then resolve the live endpoint through canonical `RuntimeIdentity` at execution time. Do not freeze the current MCP host, server version, IP address, or port into a timeless instruction merely because it is true during authoring.

The stable audit finding is `VOLATILE_RUNTIME_BINDING_REQUIRES_OWNER`. Resolve it by proving that the statement is a stable compatibility contract, labeling it as a bounded volatile observation where appropriate, or replacing the binding with logical capability ownership plus live `RuntimeIdentity` resolution.
