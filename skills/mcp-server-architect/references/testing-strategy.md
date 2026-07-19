---
description: Layered MCP server testing strategy covering generation, domain, manifests, invocation parity, targets, lifecycle, transports, races, filesystems, tasks, browsers, real clients, upstreams, artifacts, and migration simulations.
doc_id: reference.mcp-server-testing-strategy
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Generate a clean project and execute its real-client suite, demonstrate one independently failing test at each applicable layer, and run conformance smoke tests against every advertised transport in the built artifact.
---

# MCP server testing strategy

## Layer responsibilities

### Generator acceptance

Generate two projects with identical inputs and compare every byte. Refuse invalid names and existing targets. Compile all generated source and tests, install the stable official SDK lane, and execute the generated suite through an official in-memory MCP client.

Assert the project contains typed immutable settings, application-owned manifests, a transport-independent domain service, one invocation kernel, official registration, stdio and loopback Streamable HTTP, tools, resources, prompts, server instructions, packaging, Docker, security guidance, and pinned CI. Prohibit private SDK registries, fake context, direct raw-wrapper invocation, unbounded HTTP bodies, optimistic write defaults, and mutable action tags.

### Configuration and composition

Load configuration through the production entry point in a fresh process. Prove secret or environment sources are loaded before modules capture values, invalid settings fail before transport bind, and one immutable snapshot reaches every dependency. Test working-directory changes, absent optional files, worker startup, and packaged execution.

### Domain unit

Call typed application operations directly. Cover validation, domain values, success, failure, cancellation, concurrency preconditions, target identity, partial results, compensation, and no-I/O branches. Do not import the server host merely to test business logic.

### Schema and serialization

Validate input schemas, optional fields, enum behavior, structured outputs, content blocks, empty success, stable codes, pagination, target metadata, confidentiality, task state, artifact handles, and additive compatibility. Test producer serialization and consumer-visible representation.

Money tests use decimal or minor-unit edge cases, currency and rounding. Date tests use ISO 8601, timezone, and date-only boundaries. Pagination tests cover empty, partial, full-final, changing-data, invalid-cursor, and maximum-page scenarios; a non-empty page must not cause infinite continuation.

### Manifest and version policy

Enumerate supported, active, registered, and governed catalogs. Enforce complete coverage, names, required fields, multi-axis classification, conservative write defaults, schema version, deprecation, timeout, target binding, authorization class, confidentiality, cost, artifact impact, and concurrency mapping.

Each positive `idempotent`, `retryable`, `reversible`, `concurrent_safe`, cache, expected-disconnect, long-running, persistent-artifact, and profile-sharing claim has an operation-specific test. Missing metadata is a failure, never an implicit read classification.

### Invocation-kernel parity

Call the same representative capability through the direct application adapter, MCP stdio, MCP HTTP, and any convenience REST bridge. Compare target resolution, auth decision, operator gate, validation, deadline, rate limit, lock, error code, sanitization, correlation, task or artifact ownership, and response semantics.

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

Risk inference tests combine every signal regardless of order. A weaker metadata value followed by a stronger name prefix or annotation must retain the stronger result; safe classifications from untrusted metadata never lower unknown risk.

### Filesystem and artifact safety

Test lexical sibling-prefix escapes, `..`, alternate separators, case behavior where relevant, symlink and reparse-point escape, symlink swap between validation and write, archive traversal, link entries, special files, decompression bombs, filename normalization, and atomic replacement.

Artifact tests verify opaque identity, principal and target ownership, MIME type, byte limit, checksum when applicable, partial-file invisibility, bounded preview and download, retention, expiry, deletion, cleanup failure, and absence of host paths in public responses.

### Public registration and profiles

Start real composition and inspect components through a supported client API. Assert names, real schemas, descriptions, manifests, resources, prompts, server instructions, supported catalog, active profile, unavailable reasons, and deliberate count contracts. Private registry probes are tested only inside a compatibility adapter.

Install a wrapper that changes a callable signature and prove the schema-stability test detects it. Capability discovery must remain zero-I/O. Profiles and disabled capabilities update tool listing, manifests, resources, prompts, instructions, and health consistently.

### Lifecycle and partial startup

Cover mandatory dependency failure, partial optional failure, all targets failed, configured default failed, explicit replacement target, readiness transitions, resource initialization count, cleanup after failed startup, normal shutdown, cancellation, and transport disconnect.

Assert liveness can remain healthy while readiness is false. Tool count and port binding must not make readiness true. Test capability and task health for optional integrations and privileged adapters. A session disconnect closes session-owned resources only; process and tenant clients survive until their owner shuts down.

### Concurrency, quota, and scheduler affinity

Overlap calls sharing a client, cache, lock, principal, target, timeout, request ID, quota, executor, browser context, profile transition, or task state. Prove non-concurrent-safe operations serialize by resource while unrelated operations remain parallel.

Python tests use `contextvars` and one owning event loop for persistent async resources. A regression test runs the server with multiple tasks on one thread and fails if thread-local request context crosses calls. Request paths reject `asyncio.run`, `run_until_complete`, and new-loop compatibility helpers.

Test lock cancellation, deadline while queued, shutdown while waiting, rate-limiter races, `Retry-After`, jitter bounds, quota scope, bounded executor saturation, blocking-call timeout, and discarded late results.

### Retry, ambiguity, and workflow state

For every retryable operation, test eligible and ineligible errors, explicit manifest and response vetoes, deadline exhaustion, target preservation, attempt bound, backoff, and reconciliation.

Create, publish, copy, status transition, browser action, command, update, restart, firmware, and task launch default to no retry. A positive test requires an idempotency key, deduplication record, natural idempotency proof, or conflict precondition.

Simulate a timeout after the upstream commits a mutation. The server must return an ambiguous or unknown outcome with reconciliation guidance rather than blindly retrying. Multi-step workflows preserve plan, per-step results, commit boundary, partial state, verification, and compensation.

Expected-disconnect tests cover accepted state, target identity, verification deadline, reconnect, final postcondition, and no duplicate execution.

### Task registry

Test at least 128 bits of identifier entropy, authenticated-principal binding, active and queued admission limits, progress bounds, result size, cancellation, unknown outcome, verification, expiry, retained-result limits, cleanup, shutdown grace, and durable recovery when promised. Daemon threads and untracked `create_task` calls fail the architecture test.

### Browser automation

Test normalized account names, profile path containment, restrictive permissions, two-process profile locking, stale-lock recovery, account isolation, interactive-auth states, and explicit cleanup. Overlap session creation, visible/headless transitions, reauthentication, account switching, and shared-context closure.

Version selector fixtures and semantic landmarks. Simulate login, consent, quota, DOM drift, missing citation panel, ambiguous click completion, and browser crash as separate categories. Capture only bounded sanitized diagnostics. Treat returned webpage and AI-generated content as provenance-bearing untrusted input.

### Transport conformance

Use real stdio and Streamable HTTP. Verify initialization, protocol version, listing with real schemas, invocation, malformed messages, protocol-native errors, cancellation, disconnect, session behavior, and shutdown. Stdio additionally asserts protocol-only stdout.

Legacy SSE receives a separate compatibility suite and is not allowed to stand in for Streamable HTTP. A hand-written JSON-RPC or REST endpoint cannot satisfy MCP conformance.

Origin tests include malformed values, wildcard policy, explicit and default ports, bracketed IPv6, IDNA, reverse-proxy headers, empty Origin behavior, and wildcard syntax that must not crash URL parsing. HTTP tests also enforce request-body, header, JSON-depth, response, concurrency, queue, session, and rate limits before unbounded buffering.

### Long-running work and exports

Test synchronous and task-based scans, updates, media generation, hardware checks, browser generation, and exports. Bound progress, task count, status payload, cancellation, expiry, cleanup, and restart behavior.

Export tests verify selection, maximum size, atomic destination, component-aware path allowlist, secure permissions, provenance, retention, confidential-field minimization, cancellation, and cleanup of partial files.

### Real-client workflow

Use an official client, inspector, or conformance tester to run discover-select-invoke-verify flows. Include a read, an authorized mutation when applicable, confidential output policy, controlled error, unavailable capability, failed target, pagination termination, task polling, artifact retrieval, and cancellation.

### Upstream contract

Use fakes, mock HTTP handlers, recorded fixtures, emulators, browser fixtures, canaries, or test containers according to the integration. Verify timeout, cancellation, host identity, credential placement, status mapping, retry hints, pagination, ambiguous completion, UI drift, and partial failure rather than mocking the final return value.

For shell or device protocols, fuzz validated arguments and verify fixed executable or closed template behavior. For API keys in query parameters, inspect captured logs, traces, exceptions, and proxy requests for leakage.

### Deployment artifact

Build the package or container, start the exact artifact, wait for readiness, verify representative behavior, terminate during an in-flight call, and confirm cleanup. Production user, filesystem, network, secret, browser-profile, and environment restrictions are preserved. Test startup without repository tests or development-only packages.

## Archetype migration matrix

Every substantial migration runs the applicable regressions:

| Archetype | Mandatory migration regressions |
| --- | --- |
| large read-only aggregator | confidential reads, active profiles, missing manifest, safe paths, artifact and task bounds, dependency readiness |
| heterogeneous device controller | target identity revalidation, SSRF and redirects, scoped privileges, upload and artifact limits, long operation state |
| SSH network appliance | host identity, immutable call options, keyed serialization, closed command model, expected disconnect |
| multi-backend administrator | no silent target fallback, backend capability matrix, quota race, secret cache policy, process cleanup |
| financial API adapter | decimal and date semantics, query-secret redaction, client idempotency key, pagination termination, config order |
| browser automation | profile isolation and lock, shared-context race, interactive auth, body and session bounds, UI drift, provenance, generated artifact flow |

A new migration finding becomes a reusable test category when it can recur in another server. Repository-specific names and fixtures stay in implementation repositories; the invariant and failure shape belong here.

## Test doubles

Mock stable application-owned interfaces. Avoid patching SDK internals, production request context, or `sys.modules`. Python decorator fakes return the original callable. .NET replaces services through DI. A compatibility adapter has its own package and SDK-version tests.

## CI matrix

Run the stable production SDK lane at minimum and preferred versions. Run prerelease or next-major SDKs in a separate candidate lane with exact pins and allowed failure only when explicitly time-bounded. Candidate success does not replace stable production evidence.

Keep generator, unit, integration, smoke, e2e, conformance, live-backend, browser, artifact, and migration suites separately visible. A skipped suite declares its prerequisite and does not contribute misleading coverage.

## Verification

Break one generator, configuration-order, manifest, registration, invocation-parity, risk-order, target, path, artifact, task, browser-profile, lifecycle, race, retry, pagination, schema, transport, sanitization, long-task, and deployment path in a disposable branch and confirm the intended layer fails with actionable evidence.
