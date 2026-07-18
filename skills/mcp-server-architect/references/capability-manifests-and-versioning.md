---
description: Governed MCP capability manifest, multi-axis safety, runtime evidence, discovery, and compatibility rules.
doc_id: reference.mcp-capability-manifests
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Enumerate every public tool through a supported client API and validate manifest coverage, schema identity, multi-axis consistency, active-profile state, target binding, version compatibility, and runtime policy enforcement.
---

# MCP capability manifests and versioning

## Manifest purpose

A manifest is the server-owned machine contract used by policy, discovery, tests, and consumers. Descriptions and protocol annotations are projections of that contract, not independent sources of truth.

At L2 and above, every registered public tool has exactly one manifest. Registration and CI fail when a manifest is missing, duplicated, malformed, or attached to a different tool name. Never auto-register an unclassified tool as `READ`.

## Required fields

| Field | Meaning |
| --- | --- |
| `name` | Stable public tool identifier |
| `version` | Tool contract version |
| `risk` | Compatibility/UI projection such as `READ`, `WRITE`, `DESTRUCTIVE`, `DANGEROUS`, or `SENSITIVE` |
| `side_effects` | `none`, `read`, `write`, or `destructive` |
| `confidentiality` | `public`, `internal`, `personal`, `sensitive`, `credential`, or stricter domain class |
| `idempotent` | Repeating the same completed operation has no additional effect |
| `idempotency_mechanism` | `natural`, `idempotency_key`, `precondition`, `deduplication`, or `none` |
| `retryable` | Server policy explicitly permits retry for named eligible failures |
| `retry_conditions` | Allowed error categories, attempt limit, backoff, deadline, and reconciliation rule |
| `concurrent_safe` | Runtime permits overlapping calls without corruption or cross-talk |
| `concurrency_scope` | Resource key, target key, credential quota, global gate, or isolated client |
| `timeout_ms` | Maximum operation budget enforced downstream |
| `requires_confirmation` | Consumer consent hint; not server authorization |
| `determinism` | `deterministic`, `probabilistic`, `env-dependent`, or `eventually-consistent` |
| `latency` | Bounded operational class |
| `cost` | Relative resource and abuse class |
| `impact` | `none`, `transient`, `persistent`, `service_outage`, `financial`, or stricter class |
| `reversible` | Whether application-level compensation can undo the effect |
| `target_binding` | Stable identity and revalidation rule used before execution |
| `active_state` | `active`, `disabled`, `degraded`, `unavailable`, or `deprecated` |

Servers may add fields such as required scopes, output limit, data provenance, freshness, retention, cache policy, capability-health identifier, long-running mode, expected-disconnect state, and deprecation window.

## Risk is multi-axis

`risk` is not sufficient for authorization or retry decisions. A tool can be read-only and credential-bearing, write-only and reversible, destructive but fixed, or dangerous without immediate mutation. Runtime policy evaluates side effects, confidentiality, impact, cost, reversibility, target binding, and execution isolation independently.

| Compatibility label | Required interpretation |
| --- | --- |
| `READ` | no mutation; confidentiality and cost still evaluated |
| `WRITE` | bounded known mutation; operation-specific idempotency and compensation |
| `DESTRUCTIVE` | irreversible or outage-causing fixed operation; no blind retry |
| `DANGEROUS` | arbitrary or broadly parameterized execution; strongest isolation and authorization |
| `SENSITIVE` | protected model-visible output or credential handling; may also be read, write, or destructive |

A fixed reboot is destructive, not automatically dangerous. An account listing or log search may be sensitive despite read-only side effects. A network scan may be read-only while still expensive and abuse-prone.

## Evidence-driven positive claims

Factories may provide syntax and conservative defaults, but they cannot prove semantics for a whole operation class.

- A write defaults to `idempotent: false`, `retryable: false`, and `concurrent_safe: false` unless reviewed evidence overrides it.
- A read may be naturally idempotent, but retry still requires eligible error categories and deadline policy.
- Create, publish, copy, command, restart, update, payment-state, firmware, and task-launch operations require explicit idempotency evidence.
- `idempotency_key` is valid only when uniqueness scope, retention, replay response, and ambiguous-completion behavior are defined.
- `reversible: true` names and tests the compensation action and its limits.
- `concurrent_safe: true` names the protected mutable resources and supplies overlap evidence.
- `retryable: true` names error categories, attempt bound, backoff, target preservation, and reconciliation.

An ambiguous timeout after a mutation returns an unknown-outcome state when completion cannot be proven. It is not converted into a generic retryable failure.

## Runtime enforcement

- Server authorization, operator enablement, target allowlists, and consumer confirmation are separate controls.
- Target identity is resolved before authorization and remains unchanged throughout retry and execution.
- An unavailable requested or default target never falls back silently to another target.
- `concurrent_safe: false` maps to a keyed lock, semaphore, serialized actor, queue, or isolated client.
- `timeout_ms` maps to a real deadline passed to downstream I/O and task execution.
- `retry_conditions` map to explicit error categories, idempotency checks, and upstream hints.
- `confidentiality` maps to minimization, redaction, retention, cache, and audit policy.
- `active_state` maps to discovery and readiness; inactive capabilities cannot remain silently invokable.

Tests prove these mappings. Merely returning the manifest is not compliance.

## Supported and active catalogs

The supported catalog describes every capability implemented by the artifact. The active catalog is the subset enabled for the current configuration, dependency health, profile, principal, and operator policy.

Discovery returns both states or enough information to distinguish them. A profile that hides tools, an unavailable optional backend, or an isolated privileged adapter cannot create orphaned manifests or misleading counts. Zero-I/O capability discovery must not contact sensitive or unavailable upstream systems.

## Exposure and discovery

Expose manifests through a protocol-visible capability tool or another supported MCP discovery mechanism. A REST-only manifest endpoint is insufficient for an agent connected solely through MCP.

Capability discovery returns a schema version, server version, SDK family and version, protocol versions, supported and active transports, supported and active component counts, profile, and manifests. Large catalogs support minimal listings, categories, search, or on-demand schema retrieval.

Use public SDK APIs for enumeration. If a supported SDK generation lacks a public enumeration API, isolate the compatibility probe in one adapter, pin the version range, and test it. Private registry layout is never used by domain or policy code.

## Version compatibility

- Additive response fields and optional parameters are backward-compatible only when defaults preserve semantics.
- Existing field semantics do not change within a major version.
- Removed fields, newly required parameters, changed target selection, or changed retry behavior require a major version or versioned tool name.
- Deprecation includes replacement, migration instructions, active-state behavior, and removal window.
- Consumers ignore unknown response and `_meta` fields.
- Capability schema versions are independent from implementation package versions.
- Legacy documentation paths remain as deprecation stubs when external repositories link to them.
- SDK family and package identity are explicit; similarly named FastMCP implementations are not assumed compatible.

## Coverage gate

A manifest compliance test must:

1. discover components through a supported client or compatibility adapter;
2. compare discovered, supported, active, and governed sets;
3. reject missing, orphaned, duplicated, and silently inactive manifests;
4. validate required fields and allowed values;
5. enforce multi-axis consistency and conservative defaults;
6. compare public names, schemas, descriptions, and versions;
7. assert runtime gates for write, destructive, dangerous, confidential, expensive, and unavailable capabilities;
8. prove target binding, no-silent-fallback, timeout, and concurrency behavior;
9. prove every positive idempotency, retry, reversibility, cache, and long-running claim;
10. inspect the manifest through a real client on every advertised transport.

## Verification

Run the coverage gate against the stable and candidate SDK lanes. Verify representative read, write, destructive, confidential, expensive, unavailable, ambiguous-outcome, target-failure, and expected-disconnect paths when those classes exist.