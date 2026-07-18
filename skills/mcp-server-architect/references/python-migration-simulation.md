---
description: Migration simulation for Python MCP server archetypes, with ambiguity resolutions, failure modes, and future-proof acceptance evidence.
doc_id: reference.python-mcp-migration-simulation
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Apply the simulation checklist to a representative server of each archetype and prove that the named regression tests fail before the unsafe pattern is corrected.
---

# Python MCP migration simulation

## Purpose and method

This document simulates migration of five Python server archetypes to the normative MCP standard. It does not prescribe one repository layout. It identifies assumptions that become failures during a real rewrite and converts each failure into a reusable control and test.

For each archetype, perform the migration in this order:

1. inventory supported and currently active capabilities;
2. identify every invocation path and downstream dependency;
3. freeze typed configuration before client construction;
4. separate domain operations from SDK registration;
5. build one invocation kernel;
6. classify each capability across independent safety axes;
7. assign lifecycle, target, concurrency, and task ownership;
8. move transports onto public SDK APIs;
9. compare old and new behavior with contract, race, and artifact tests;
10. remove compatibility code only after all consumers migrate.

A migration is incomplete when the new transport starts but policy, failure semantics, or target identity differ from the old server.

## Archetype A: large read-only aggregator

### Aggregator rewrite

Move a large collection of configuration, log, history, graph, diagnostic, batch, and export tools behind typed application services. Replace post-registration wrapper mutation and private registry enumeration with an application-owned capability registry registered through supported SDK APIs. Split the full supported catalog from smaller active profiles and progressive discovery.

### Aggregator ambiguities

“Read-only” describes side effects, not confidentiality, cost, or abuse potential. Logs, histories, configuration, network identifiers, and generated snapshots may contain protected data even when no mutation occurs. A full context export is not equivalent to a cheap point read: it may scan many files, call multiple APIs, produce a durable artifact, and exceed an agent context budget.

A tool count cannot prove readiness. Registration can succeed while credentials, filesystem mounts, or upstream APIs are unavailable. Running the repository test suite during process startup is also not a health check; it couples production boot to development dependencies and may hang without a bound.

### Aggregator controls

- Every read capability declares confidentiality, output bound, freshness, and cost.
- Bulk exports use explicit selection, size limits, destination policy, atomic write, provenance, retention, cancellation, and deletion.
- Missing manifests fail registration; no unknown tool is auto-classified as read.
- Wrappers and middleware are installed before registration or through supported transforms so schemas and signatures remain stable.
- Active profiles are validated against the supported catalog and exposed through MCP discovery.
- Startup diagnostics are bounded and dependency-oriented; full tests remain CI or deployment gates.

### Aggregator regression evidence

Test confidential read classification, omitted-manifest failure, active-profile discovery, wrapper-preserved schemas, partial dependency readiness, export cancellation, output limits, and startup without test-only packages.

## Archetype B: heterogeneous local-device controller

### Device-controller rewrite

Place network discovery, HTTP devices, message brokers, cloud adapters, raw TCP protocols, cameras, file transfer, firmware update, and container integration behind separate capability groups. Route all MCP and REST calls through one invocation kernel and isolate high-privilege adapters such as a container socket.

### Device-controller ambiguities

An IP address is not a stable device identity. DHCP reuse can cause an agent to discover one device and mutate another later. An agent-provided host or URL can also become an SSRF primitive through DNS changes, redirects, alternate address forms, or unexpected ports.

One global write switch is too coarse. Enabling a harmless light change must not implicitly enable raw commands, firmware updates, factory reset, file upload, or container restart. Device protocols also differ: one shared tool name may hide different validation, acknowledgement, and rollback guarantees.

Long operations commonly disconnect the target. OTA, restart, hardware tests, and network reconfiguration must not surface expected disconnect as an ordinary timeout that invites retry.

### Device-controller controls

- Discovery returns a stable identity and observed address; mutation re-resolves and revalidates their binding before I/O.
- Network policy validates scheme, normalized host, resolved addresses, CIDR, port, redirects, and DNS rebinding behavior.
- Operator enablement is capability- and target-scoped, with separate profiles for raw, firmware, filesystem, cloud, and container access.
- Backend adapters publish a capability matrix; unsupported semantics fail explicitly rather than silently degrading.
- Long operations return accepted state, task identity, progress, cancellation support, expected-disconnect state, and post-reconnect verification.
- Composite device changes expose plan, per-step result, verification, and compensation.

### Device-controller regression evidence

Test DHCP identity change, DNS rebinding, redirect escape, IPv4 and IPv6 normalization, denied target CIDR, scoped operator policy, disabled privileged adapter, concurrent scan bounds, OTA cancellation, and post-restart verification.

## Archetype C: SSH network appliance

### Network-appliance rewrite

Replace mutable shared SSH options and shell-fragment construction with immutable per-call requests, typed command builders, explicit target locks, verified host identity, and bounded command execution. Migrate legacy SSE to standard stdio or Streamable HTTP while preserving a compatibility window.

### Network-appliance ambiguities

Declaring `concurrent_safe: false` does not serialize anything. Mutating a shared timeout immediately before an `await` lets concurrent calls overwrite one another. A compatibility helper that creates and runs a new event loop from a request path can also fail when an event loop is already active.

A public-bind acknowledgement does not secure a privileged router. Host-key verification described as optional leaves the highest-value downstream identity unauthenticated. Denying a list of shell metacharacters is not a complete command model, especially when user values are interpolated into a shell program.

Configuration workflows are transactional. Setting a value, committing it, restarting an interface, and verifying connectivity span several states and may temporarily remove the management channel.

### Network-appliance controls

- `concurrent_safe: false` maps to a tested keyed lock or isolated connection.
- Per-call timeout, target, and credentials are immutable.
- Request paths never call `run_until_complete`, `asyncio.run`, or a newly created event loop.
- Hardened deployments require pinned host identity or an explicit first-use enrollment workflow.
- Commands use fixed executable and argument models where possible; remaining shell templates are closed, quoted, bounded, and fuzz-tested.
- Configuration changes use read-version, plan, apply, commit, reconnect, verify, and rollback semantics.
- Readiness includes downstream identity and connectivity, not merely tool registration.

### Network-appliance regression evidence

Overlap calls with different timeouts and targets, cancel while waiting for a lock, invoke through a running event loop, reject host-key mismatch, fuzz command arguments, simulate expected management disconnect, and prove rollback or explicit partial state.

## Archetype D: multi-backend privileged administrator

### Multi-backend rewrite

Model every configured backend as a stable target with its own identity, credential set, health, capability matrix, quota, client lifecycle, and lock scope. Keep partial startup, but remove implicit fallback. Split read-only inspection from privileged administration when deployment boundaries permit.

### Multi-backend ambiguities

Selecting the first healthy backend when the configured default fails is convenient for reads but catastrophic for writes. A caller that omitted a target may unknowingly mutate a different server. The resolved target must therefore be an explicit part of authorization, telemetry, and response metadata.

A shared API client can have a race in its request-spacing timestamp even when its cache has a lock. Retrying every rate-limited endpoint is unsafe for command, restart, domain assignment, file write, or service mutation. Upstream `Retry-After`, credential-scoped quotas, and the remaining request deadline matter.

Caching credential-returning endpoints creates an additional secret store. Passing credentials through environment JSON or command-line examples may expose them through process inspection, history, diagnostics, or crash reporting.

### Multi-backend controls

- An unavailable requested or default target produces a controlled error; it never selects another target implicitly.
- Every response and audit event includes resolved target identity and backend kind.
- Common tools declare backend-specific semantic differences or split into separate capabilities.
- Rate limiters are concurrency-safe and scoped to the upstream quota key.
- Retry policy is operation-specific, honors upstream hints, includes jitter, and cannot outlive the request deadline.
- Credential and other highly confidential results are not cached by default.
- Secret files or managed stores are preferred over command-line or aggregate JSON credentials.
- Privileged subprocesses are terminated and awaited on timeout or cancellation; client shutdown waits for closure.

### Multi-backend regression evidence

Test failed-default behavior, explicit target authorization, backend capability mismatch, concurrent rate limiting, retry veto for mutations, `Retry-After`, deadline exhaustion, secret-cache prohibition, timeout process cleanup, and partial-startup reporting.

## Archetype E: financial API adapter

### Financial-adapter rewrite

Convert a synchronous API client into a lifecycle-owned adapter or isolate it behind a bounded executor. Preserve upstream status classes instead of collapsing failures to null. Make financial types, dates, pagination, idempotency, confidentiality, and write verification explicit in application contracts.

### Financial-adapter ambiguities

Financial reads are sensitive even when they are side-effect free. Query-string API keys may be an upstream requirement but can leak through URL logging, proxies, traces, and exceptions. A recursive regular-expression sanitizer is not a substitute for data minimization and field classification.

Generic write factories often mark create, copy, or status-transition operations idempotent and retryable. This is valid only when the upstream accepts a durable idempotency key or the server owns a deduplication record. An ambiguous API failure after a timeout may mean the mutation completed.

Pagination cannot infer `has_more` from a non-empty page. Without a stable order and termination rule, an agent can loop forever. Localized date strings and free-form money strings also create silent interpretation differences.

Configuration loaded after importing constants can be ignored because modules already captured environment values. A health endpoint that always reports healthy while credentials are invalid makes orchestration unsafe.

### Financial-adapter controls

- Financial accounts, transactions, wealth, and schedules use an explicit confidentiality class and minimization policy.
- URL, query, trace, exception, and proxy logging are sanitized at source when credentials appear in query parameters.
- Money uses decimal or integer minor units, currency, range, sign, and rounding rules.
- Public dates use ISO 8601 and explicit timezone or date-only semantics; locale conversion stays in the adapter.
- Create and state-transition retries require durable idempotency evidence; ambiguous completion returns unknown outcome plus reconciliation guidance.
- Pagination defines page size, stable ordering, cursor or page semantics, and a terminating signal verified by tests.
- Typed configuration is loaded before importing or constructing environment-bound dependencies.
- Readiness reflects credentials and required API reachability; liveness remains independent.
- Blocking adapters use a bounded executor and a downstream timeout that fits inside the MCP deadline.

### Financial-adapter regression evidence

Test confidential output minimization, query-secret redaction, decimal and currency edges, locale date rejection, duplicate create after timeout, ambiguous mutation reconciliation, empty and final pagination pages, configuration import order, executor saturation, and readiness under invalid credentials.

## Cross-cutting ambiguity resolutions

### Risk is a vector

A capability can be read-only and sensitive, write-only and reversible, destructive but fixed, or dangerous without immediately mutating state. Policies consume the complete vector rather than selecting one optimistic label.

### Retry is an executable proof

`retryable: true` is valid only when runtime code can name the eligible error classes, idempotency mechanism, maximum attempts, backoff, deadline, target binding, and verification. Factory defaults do not provide that proof.

### Readiness is a declared service promise

Readiness is evaluated against mandatory capabilities and dependencies. Liveness only proves process progress. Capability health explains optional degradation. A successful bind, tool count, or registry load is insufficient.

### One invocation kernel prevents policy drift

MCP, REST, test adapters, and compatibility transports use the same kernel. Adapter-specific parsing is allowed; adapter-specific authorization, validation, retry, sanitization, or target resolution is not.

### Compatibility is explicit and temporary

SDK family, package, version range, public API surface, transport, and protocol version are recorded. Private compatibility code is isolated, fail-closed, covered by a matrix, and removed on a scheduled boundary.

## Migration acceptance checklist

A migrated Python server is accepted only when:

- configuration is loaded and validated before dependency construction;
- supported and active capability catalogs are complete and consistent;
- every capability has multi-axis classification and runtime evidence;
- all transports share one invocation kernel;
- target identity is explicit and cannot silently fall back;
- async context uses `contextvars`, not thread-local state;
- blocking work and executor queues are bounded;
- clients, subprocesses, sessions, tasks, and caches have deterministic ownership and cleanup;
- retries, pagination, long-running work, and expected disconnects have terminating state machines;
- confidential output and exports are minimized, bounded, and retained intentionally;
- health distinguishes startup, readiness, liveness, and capability state;
- stable and candidate SDK lanes are pinned and tested separately;
- real-client conformance and artifact tests exercise the final deployment path.

## Verification

Apply the archetype regressions to each migration. Add a new regression whenever implementation work reveals an assumption not represented here; generalize the finding to an invariant, runtime control, and independently failing test before declaring the migration complete.