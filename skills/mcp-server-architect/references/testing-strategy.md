---
description: Layered MCP server testing strategy covering domain, manifests, registration, lifecycle, transport conformance, races, real clients, upstreams, and artifacts.
doc_id: reference.mcp-server-testing-strategy
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Demonstrate one independently failing test at each applicable layer and run a real-client conformance smoke test against every advertised transport in the built artifact.
---

# MCP server testing strategy

## Layer responsibilities

### Domain unit

Call typed application operations directly. Cover validation, success, failure, cancellation, concurrency preconditions, partial results, and no-I/O branches. Do not import the server host merely to test business logic.

### Schema and serialization

Validate input schemas, optional fields, enum behavior, structured outputs, content blocks, empty success, stable codes, pagination, and additive compatibility. Test producer serialization and consumer-visible representation.

### Manifest and version policy

Enumerate the governed manifest registry. Enforce complete coverage, names, required fields, risk consistency, schema version, deprecation, timeout, authorization class, and concurrency mapping. Missing metadata is a failure, never an implicit read classification.

### Policy and sanitization

Exercise authentication, per-resource authorization, operator write gates, confirmation metadata, idempotency, conflict preconditions, blocked data, command/path allowlists, Origin/CORS, rate limits, and recursive response/log redaction.

### Public registration

Start real composition and inspect components through a supported client API. Assert names, schemas, descriptions, manifests, and deliberate count contracts. Private registry probes are tested only inside a compatibility adapter.

### Lifecycle and partial startup

Cover mandatory dependency failure, partial optional failure, valid default selection, readiness transitions, resource initialization count, cleanup after failed startup, normal shutdown, cancellation, and transport disconnect.

### Concurrency and scheduler affinity

Overlap calls sharing a client, cache, lock, principal, target, timeout, or correlation state. Prove non-concurrent-safe operations serialize by resource while unrelated operations remain parallel.

Python tests keep persistent async resources on one owning event loop. .NET tests use one host lifetime and reject sync-over-async. Test queue bounds, lock cancellation, and shutdown while waiting.

### Transport conformance

Use real stdio and Streamable HTTP. Verify initialization, protocol version, listing with real schemas, invocation, malformed messages, protocol-native errors, cancellation, disconnect, session behavior, and shutdown. Stdio additionally asserts protocol-only stdout.

Legacy SSE receives a separate compatibility suite and is not allowed to stand in for Streamable HTTP.

### Transport parity

For each advertised transport, compare component set, manifests, schemas, auth decisions, deadlines, errors, sanitization, correlation, and capability health. A REST convenience bridge must pass the same application-policy tests but is not counted as MCP conformance.

### Real-client workflow

Use an official client, inspector, or conformance tester to run discover-select-invoke-verify flows. Include a read, an authorized mutation when applicable, a controlled error, and an unavailable capability.

### Upstream contract

Use fakes, mock HTTP handlers, recorded fixtures, emulators, or test containers according to the integration. Verify timeout, cancellation, host identity, mapping, and partial failure rather than mocking the final return value.

### Deployment artifact

Build the package or container, start the exact artifact, wait for readiness, verify representative behavior, terminate during an in-flight call, and confirm cleanup. Production user, filesystem, network, and environment restrictions are preserved.

## Test doubles

Mock stable application-owned interfaces. Avoid patching SDK internals or `sys.modules`. Python decorator fakes return the original callable. .NET replaces services through DI. A compatibility adapter has its own SDK-version tests.

## CI matrix

Run minimum and preferred supported SDK versions. Keep unit, integration, smoke, e2e, conformance, and live-backend suites separately visible. A skipped suite declares its prerequisite and does not contribute misleading coverage.

## Verification

Break one manifest, registration, lifecycle, race, schema, transport, sanitization, and deployment path in a disposable branch and confirm the intended layer fails with actionable evidence.
