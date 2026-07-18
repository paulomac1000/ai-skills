---
description: Governed MCP capability manifest, risk-consistency, discovery, and compatibility rules.
doc_id: reference.mcp-capability-manifests
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Enumerate every public tool through a supported client API and validate manifest coverage, schema identity, risk consistency, version compatibility, and runtime policy enforcement.
---

# MCP capability manifests and versioning

## Manifest purpose

A manifest is the server-owned machine contract used by policy, discovery, tests, and consumers. Descriptions and protocol annotations are projections of that contract, not independent sources of truth.

At L2 and above, every registered public tool must have exactly one manifest. Registration and CI fail when a manifest is missing, duplicated, malformed, or attached to a different tool name. Never auto-register an unclassified tool as `READ`.

## Required fields

| Field | Meaning |
| --- | --- |
| `name` | Stable public tool identifier |
| `version` | Tool contract version |
| `risk` | `READ`, `WRITE`, `DESTRUCTIVE`, `DANGEROUS`, or `SENSITIVE` |
| `side_effects` | `none`, `read`, `write`, or `destructive` |
| `idempotent` | Repeating the same completed operation has no additional effect |
| `retryable` | Server policy explicitly permits retry for eligible failures |
| `concurrent_safe` | Runtime permits overlapping calls without corruption or cross-talk |
| `timeout_ms` | Maximum expected operation budget, not an unbounded client hint |
| `requires_confirmation` | Consumer consent hint; not server authorization |
| `determinism` | `deterministic`, `probabilistic`, `env-dependent`, or `eventually-consistent` |
| `latency` | Bounded operational class |
| `cost` | Relative resource class |
| `impact` | `none`, `transient`, `persistent`, or `service_outage` |
| `privacy` | `none`, `metadata`, `personal`, or a stricter project class |
| `reversible` | Whether application-level compensation can undo the effect |

Servers may add fields such as required scopes, rate-limit class, concurrency key, output limit, deprecation state, cache policy, and capability-health identifier.

## Risk consistency

| Risk | Required profile |
| --- | --- |
| `READ` | no mutation; normally idempotent, retryable, reversible, no confirmation |
| `WRITE` | bounded known mutation; confirmation; explicit idempotency and compensation policy |
| `DESTRUCTIVE` | irreversible or outage-causing fixed operation; no blind retry; confirmation |
| `DANGEROUS` | arbitrary or broadly parameterized execution; strongest isolation and authorization |
| `SENSITIVE` | model-visible credentials, personal data, or protected metadata; minimization and disclosure policy |

A fixed reboot is `DESTRUCTIVE`, not `DANGEROUS`. A tool that returns protected data is `SENSITIVE` even when it performs no write.

Manifest fields are not independent. A destructive operation cannot claim `retryable: true` or `reversible: true` without a reviewed domain-specific proof. A write marked concurrent-safe must have tested enforcement.

## Runtime enforcement

- Server authorization, operator enablement, and consumer confirmation are separate controls.
- `concurrent_safe: false` maps to a keyed lock, semaphore, serialized actor, or isolated client.
- `timeout_ms` maps to a real deadline passed to downstream I/O.
- `retryable` maps to explicit error categories and idempotency checks.
- `privacy` maps to minimization, redaction, and audit policy.
- Required scopes and target constraints are evaluated after resolving the requested resource.

Tests must prove these mappings. Merely returning the manifest is not compliance.

## Exposure and discovery

Expose manifests through a protocol-visible capability tool or another supported MCP discovery mechanism. A REST-only manifest endpoint is insufficient for an agent connected solely through MCP.

Capability discovery returns a schema version, server version, supported transports, component count, and manifests. For large catalogs, support minimal listings, categories, search, or on-demand schema retrieval.

Use public SDK APIs for enumeration. If a supported SDK generation lacks a public enumeration API, isolate the compatibility probe in one adapter, pin the version range, and test it. Private registry layout is never used by domain or policy code.

## Version compatibility

- Additive response fields and optional parameters are backward-compatible.
- Existing field semantics do not change within a major version.
- Removed fields or newly required parameters require a major version or versioned tool name.
- Deprecation includes the replacement, migration instructions, and a removal window.
- Consumers ignore unknown response and `_meta` fields.
- Capability schema versions are independent from implementation package versions.
- Legacy documentation paths remain as deprecation stubs when external repositories link to them.

## Coverage gate

A manifest compliance test must:

1. discover components through a supported client or compatibility adapter;
2. compare the discovered set with the governed manifest set;
3. reject missing and orphaned manifests;
4. validate required fields and allowed values;
5. enforce the risk-consistency matrix;
6. compare public names and schemas;
7. assert runtime gates for write, destructive, dangerous, and sensitive tools;
8. run at least one concurrency and timeout proof for each policy class.

## Verification

Run the coverage gate against the minimum and preferred SDK versions, then inspect the manifest through a real MCP client and verify one read, write, destructive, sensitive, and unavailable-capability policy path when those classes exist.
