---
description: Credential isolation, authority-preserving API-key failover, affinity, and provider/model substitution policy for MCP Stewards.
doc_id: reference.mcp-steward-credentials-failover
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Test rate-limit and credential-specific fallback, denied authorization/policy fallback, delivery-unknown veto, remote-handle affinity, bounded cooldown, and provider/model provenance without exposing secret values.
---

# Credentials and failover

Credential routing is policy, not exception handling.

## Secret boundary

Resolve secrets at adapter execution through a credential broker/secret provider. Persist only logical slot IDs and minimum non-secret provider/account fingerprints required for audit or affinity. Never store raw keys in jobs, evidence, logs, prompts, tool schemas, discovery, or model-visible errors.

## Credential failover

A second key is eligible only when policy preserves the intended principal/scope/tenant/target semantics and retry/replay is independently safe. Rate limit, quota exhaustion, or credential-specific unavailability may be eligible. Authorization/policy/safety denial and target prohibition are not reasons to try a more privileged key.

After `delivery-unknown`, do not resubmit through another credential. Reconcile first. After a durable remote handle is known, preserve credential affinity unless the upstream contract explicitly permits equivalent credentials to resume it.

## Provider/model failover

Changing model/provider is a different execution capability, not merely another credential. It can change context/output bounds, tool behavior, cost, privacy, jurisdiction, and assurance. Make it an explicit policy/routing decision and preserve actual provider/model identity in provenance.

Bound fallback attempts and circuit/cooldown transitions. Prevent key ping-pong.
