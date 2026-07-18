---
description: Layered MCP server testing strategy covering domain, manifests, invocation parity, targets, lifecycle, transports, races, real clients, upstreams, artifacts, and migration simulations.
doc_id: reference.mcp-server-testing-strategy
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Demonstrate one independently failing test at each applicable layer and run a real-client conformance smoke test against every advertised transport in the built artifact.
---

# MCP server testing strategy

## Layer responsibilities

### Configuration and composition

Load configuration through the production entry point in a fresh process. Prove secret or environment sources are loaded before modules capture values, invalid settings fail before transport bind, and one immutable snapshot reaches every dependency. Test working-directory changes, absent optional files, worker startup, and packaged execution.

### Domain unit

Call typed application operations directly. Cover validation, domain values, success, failure, cancellation, concurrency preconditions, target identity, partial results, compensation, and no-I/O branches. Do not import the server host merely to test business logic.

### Schema and serialization

Validate input schemas, optional fields, enum behavior, structured outputs, content blocks, empty success, stable codes, pagination, target metadata, confidentiality, task state, and additive compatibility. Test producer serialization and consumer-visible representation.

Money tests use decimal or minor-unit edge cases, currency and rounding. Date tests use ISO 8601, timezone, and date-only boundaries. Pagination tests cover empty, partial, full-final, changing-data, invalid-cursor, and maximum-page scenarios; a non-empty page must not cause infinite continuation.

### Manifest and version policy

Enumerate supported, active, registered, and governed catalogs. Enforce complete coverage, names, required fields, multi-axis classification, conservative write defaults, schema version, deprecation, timeout, target binding, authorization class, confidentiality, cost, and concurrency mapping.

Each positive `idempotent`, `retryable`, `reversible`, `concurrent_safe`, cache, expected-disconnect, and long-running claim has an operation-specific test. Missing metadata is a failure, never an implicit read classification.

### Invocation-kernel parity

Call the same representative capability through the direct application adapter, MCP stdio, MCP HTTP, and any convenience REST bridge. Compare target resolution, auth decision, operator gate, validation, deadline, rate limit, lock, error code, sanitization, correlation, and response semantics.

Inject a raw-function bypass into a disposable test adapter and prove parity tests fail. No adapter-specific policy implementation is accepted.

### Policy, targets, and sanitization

Exercise authentication, per-target authorization, operator capability gates, confirmation metadata, idempotency, conflict preconditions, blocked data, command and path policy, URL resolution, Origin/CORS, rate limits, and recursive response/log minimization.

Target tests cover:

- requested target unavailable;
- configured default unavailable;
- prohibition of silent fallback;
- address identity changing between discovery and mutation;
- DNS rebinding and redirect escape;
- IPv4, IPv6, IDNA, scheme, port, and CIDR normalization;
- host-key or certificate identity mismatch;
- resolved target included in audit and response metadata.

### Public registration and profiles

Start real composition and inspect components through a supported client API. Assert names, schemas, descriptions, manifests, supported catalog, active profile, unavailable reasons, and deliberate count contracts. Private registry probes are tested only inside a compatibility adapter.

Install a wrapper that changes a callable signature and prove the schema-stability test detects it. Capability discovery must remain zero-I/O.

### Lifecycle and partial startup

Cover mandatory dependency failure, partial optional failure, all targets failed, configured default failed, explicit replacement target, readiness transitions, resource initialization count, cleanup after failed startup, normal shutdown, cancellation, and transport disconnect.

Assert liveness can remain healthy while readiness is false. Tool count and port binding must not make readiness true. Test capability health for optional integrations and privileged adapters.

### Concurrency, quota, and scheduler affinity

Overlap calls sharing a client, cache, lock, principal, target, timeout, request ID, quota, executor, or task state. Prove non-concurrent-safe operations serialize by resource while unrelated operations remain parallel.

Python tests use `contextvars` and one owning event loop for persistent async resources. A regression test runs the server with multiple tasks on one thread and fails if thread-local request context crosses calls. Request paths reject `asyncio.run`, `run_until_complete`, and new-loop compatibility helpers.

Test lock cancellation, deadline while queued, shutdown while waiting, rate-limiter races, `Retry-After`, jitter bounds, quota scope, bounded executor saturation, blocking-call timeout, and discarded late results.

### Retry, ambiguity, and workflow state

For every retryable operation, test eligible and ineligible errors, explicit manifest and response vetoes, deadline exhaustion, target preservation, attempt bound, backoff, and reconciliation.

Create, publish, copy, status transition, command, update, restart, firmware, and task launch default to no retry. A positive test requires an idempotency key, deduplication record, natural idempotency proof, or conflict precondition.

Simulate a timeout after the upstream commits a mutation. The server must return an ambiguous or unknown outcome with reconciliation guidance rather than blindly retrying. Multi-step workflows preserve plan, per-step results, commit boundary, partial state, verification, and compensation.

Expected-disconnect tests cover accepted state, target identity, verification deadline, reconnect, final postcondition, and no duplicate execution.

### Transport conformance

Use real stdio and Streamable HTTP. Verify initialization, protocol version, listing with real schemas, invocation, malformed messages, protocol-native errors, cancellation, disconnect, session behavior, and shutdown. Stdio additionally asserts protocol-only stdout.

Legacy SSE receives a separate compatibility suite and is not allowed to stand in for Streamable HTTP. A hand-written JSON-RPC or REST endpoint cannot satisfy MCP conformance.

Origin tests include malformed values, wildcard policy, explicit and default ports, bracketed IPv6, IDNA, reverse-proxy headers, empty Origin behavior, and wildcard syntax that must not crash URL parsing.

### Long-running work and exports

Test synchronous and task-based scans, updates, media generation, hardware checks, and exports. Bound progress, task count, status payload, cancellation, expiry, cleanup, and restart behavior.

Export tests verify selection, maximum size, atomic destination, path allowlist, secure permissions, provenance, retention, confidential-field minimization, cancellation, and cleanup of partial files.

### Real-client workflow

Use an official client, inspector, or conformance tester to run discover-select-invoke-verify flows. Include a read, an authorized mutation when applicable, confidential output policy, controlled error, unavailable capability, failed target, pagination termination, and cancellation.

### Upstream contract

Use fakes, mock HTTP handlers, recorded fixtures, emulators, or test containers according to the integration. Verify timeout, cancellation, host identity, credential placement, status mapping, retry hints, pagination, ambiguous completion, and partial failure rather than mocking the final return value.

For shell or device protocols, fuzz validated arguments and verify fixed executable or closed template behavior. For API keys in query parameters, inspect captured logs, traces, exceptions, and proxy requests for leakage.

### Deployment artifact

Build the package or container, start the exact artifact, wait for readiness, verify representative behavior, terminate during an in-flight call, and confirm cleanup. Production user, filesystem, network, secret, and environment restrictions are preserved. Test startup without repository tests or development-only packages.

## Archetype migration matrix

Every substantial Python migration runs the applicable regressions:

| Archetype | Mandatory migration regressions |
| --- | --- |
| large read-only aggregator | confidential reads, active profiles, missing manifest, export bounds, dependency readiness |
| heterogeneous device controller | target identity revalidation, SSRF and redirects, scoped privileges, long operation state |
| SSH network appliance | host identity, immutable call options, keyed serialization, closed command model, expected disconnect |
| multi-backend administrator | no silent target fallback, backend capability matrix, quota race, secret cache policy, process cleanup |
| financial API adapter | decimal and date semantics, query-secret redaction, idempotent create, pagination termination, config order |

A new migration finding becomes a reusable test category when it can recur in another server. Repository-specific names and fixtures stay in implementation repositories; the invariant and failure shape belong here.

## Test doubles

Mock stable application-owned interfaces. Avoid patching SDK internals, production request context, or `sys.modules`. Python decorator fakes return the original callable. .NET replaces services through DI. A compatibility adapter has its own package and SDK-version tests.

## CI matrix

Run the stable production SDK lane at minimum and preferred versions. Run prerelease or next-major SDKs in a separate candidate lane with exact pins and allowed failure only when explicitly time-bounded. Candidate success does not replace stable production evidence.

Keep unit, integration, smoke, e2e, conformance, live-backend, artifact, and migration suites separately visible. A skipped suite declares its prerequisite and does not contribute misleading coverage.

## Verification

Break one configuration-order, manifest, registration, invocation-parity, target, lifecycle, race, retry, pagination, schema, transport, sanitization, long-task, and deployment path in a disposable branch and confirm the intended layer fails with actionable evidence.