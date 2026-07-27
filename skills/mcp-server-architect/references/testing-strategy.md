---
description: Layered MCP server testing strategy covering generation, domain, manifests, invocation parity, targets, lifecycle, transports, races, filesystems, tasks, browsers, real clients, upstreams, artifacts, and migration simulations.
doc_id: reference.mcp-server-testing-strategy
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Generate clean Python and .NET projects, execute each official-client suite, demonstrate one independently failing test at every applicable layer, and run conformance smoke against every advertised transport in the exact built artifact.
---

# MCP server testing strategy

## Layer responsibilities

### Generator acceptance

Generate two projects with identical inputs and compare every byte. Refuse invalid names and existing targets. Compile generated source and tests, install or restore the stable official SDK lane, and execute the generated suite through an official MCP client.

Python uses the official in-memory MCP client where appropriate. .NET uses the official C# MCP client, launches the built stdio host through the public `StdioClientTransport`, and also smokes the exact `dotnet publish` output. Both generators must produce typed immutable settings, application-owned manifests, a transport-independent domain service, one invocation kernel, official registration, stdio and loopback Streamable HTTP, structured outputs, protocol-native errors, packaging, Docker, security guidance, and pinned CI.

Prohibit private SDK registries, fake request context, direct raw-wrapper invocation, unbounded HTTP bodies, model-controlled approval, optimistic write defaults, mutable action tags, assembly scanning in an advertised Native AOT path, and deprecated legacy HTTP+SSE endpoints.

### Configuration and composition

Load configuration through the production entry point in a fresh process. Prove secret or environment sources load before modules capture values, invalid settings fail before transport bind, and one immutable snapshot reaches every dependency. Test working-directory changes, absent optional files, worker startup, and packaged execution.

For .NET, run warnings as errors and analyzers. Verify an obsolete compatibility property such as `EnableLegacySse` is absent rather than suppressed. For Python, verify imports do not construct the server or clients before validated configuration exists.

### Domain unit

Call typed application operations directly. Cover validation, domain values, success, failure, cancellation, concurrency preconditions, target identity, partial results, compensation, and no-I/O branches. Do not import or start the server host merely to test business logic.

### Schema and serialization

Validate input schemas, optional fields, enum behavior, structured outputs, content blocks, empty success, stable codes, pagination, target metadata, confidentiality, task state, artifact handles, and additive compatibility.

A typed return value or data annotation is not sufficient evidence. Assert the public client sees the intended input schema, output schema, `structuredContent`, and `isError`. A DTO containing `success=false` must fail this layer unless the protocol-native error flag is present.

Money tests use decimal or minor-unit edge cases, currency, and rounding. Date tests use ISO 8601, timezone, and date-only boundaries. Pagination tests cover empty, partial, full-final, changing-data, invalid-cursor, and maximum-page scenarios.

### Manifest and version policy

Enumerate supported, active, registered, and governed catalogs. Enforce complete coverage, names, required fields, multi-axis classification, conservative write defaults, schema version, deprecation, timeout, target binding, authorization class, confidentiality, cost, artifact impact, and concurrency mapping.

Each positive `idempotent`, `retryable`, `reversible`, `concurrent_safe`, cache, expected-disconnect, long-running, persistent-artifact, task-support, and profile-sharing claim has operation-specific evidence. Missing metadata is a failure, never an implicit read classification.

### Invocation-kernel parity

Call the same representative capability through the direct application adapter, MCP stdio, MCP Streamable HTTP, and any convenience REST bridge. Compare target resolution, authentication, authorization, operator gate, validation, deadline, rate limit, lock, error code, sanitization, correlation, task or artifact ownership, and response semantics.

Inject a raw-function bypass into a disposable adapter and prove parity tests fail. No adapter-specific policy implementation is accepted.

### Policy, targets, and sanitization

Exercise authentication, per-target authorization, operator gates, trusted approval, idempotency, conflict preconditions, blocked data, command and path policy, URL resolution, Origin/CORS, rate limits, and recursive response/log minimization.

Target tests cover requested target unavailable, configured default unavailable, prohibition of silent fallback, identity changing between discovery and mutation, DNS rebinding, redirect escape, IPv4/IPv6/IDNA normalization, host-key or certificate mismatch, and resolved target in audit and response metadata.

Risk inference tests combine every signal monotonically. Untrusted metadata may escalate but cannot prove read-only, replay safety, trusted confirmation, or consumer policy. Typed consumer-owned trust values are separate objects, not booleans that upgrade fields from the same untrusted map.

### Filesystem and artifact safety

Test lexical sibling-prefix escapes, `..`, alternate separators, case behavior, symlink or reparse-point escape, symlink swap between validation and write, archive traversal, link entries, special files, decompression bombs, filename normalization, and atomic replacement.

Artifact tests verify opaque identity, principal and target ownership, MIME type, byte limit, checksum, partial-file invisibility, bounded preview and download, retention, expiry, deletion, cleanup failure, and absence of host paths in public responses.

### Public registration and profiles

Start real composition and inspect components through a supported client API. Assert names, real schemas, descriptions, manifests, resources, prompts, server instructions, supported catalog, active profile, unavailable reasons, and deliberate count contracts. Private registry probes are tested only inside a compatibility adapter.

For .NET, generic `WithTools<T>()` registration is the default hardened path. Build advertised trimming and Native AOT artifacts and fail if `WithToolsFromAssembly()` or another `RequiresUnreferencedCode` path is used without explicit evidence.

Capability discovery remains zero-I/O and caller-filtered. Profiles and disabled capabilities update tool listing, manifests, resources, prompts, instructions, and health consistently.

### Lifecycle and partial startup

Cover mandatory dependency failure, partial optional failure, all targets failed, configured default failed, explicit replacement target, readiness transitions, resource initialization count, cleanup after failed startup, normal shutdown, cancellation, and transport disconnect.

Assert liveness can remain healthy while readiness is false. Registration count and port binding must not make readiness true. A session disconnect closes session-owned resources only; process and tenant clients survive until their owner shuts down.

### Concurrency, quota, and scheduler affinity

Overlap calls sharing a client, cache, lock, principal, target, timeout, request ID, quota, executor, browser context, profile transition, or task state. Prove non-concurrent-safe operations serialize by resource while unrelated operations remain parallel.

Python tests use `contextvars` and one owning event loop. Request paths reject `asyncio.run`, `run_until_complete`, and unbounded thread offload. .NET tests reject `.Result`, `.Wait()`, mutable singleton request options, and untracked `Task.Run`.

Authenticate before principal-partitioned rate limiting. Test lock cancellation, deadline while queued, shutdown while waiting, rate-limiter races, `Retry-After`, jitter bounds, quota scope, bounded executor saturation, blocking-call timeout, and discarded late results.

### Retry, ambiguity, and workflow state

For every retryable operation, test eligible and ineligible errors, explicit manifest and response vetoes, deadline exhaustion, target preservation, attempt bound, backoff, and reconciliation.

Create, publish, copy, status transition, browser action, command, update, restart, firmware, and task launch default to no retry. A positive test requires a trusted idempotency key, deduplication record, natural idempotency proof, or conflict precondition.

Simulate a timeout after the upstream commits a mutation. Return ambiguous or unknown outcome with reconciliation guidance rather than blindly retrying. Expected-disconnect tests cover accepted state, target identity, verification deadline, reconnect, final postcondition, and no duplicate execution.

### Task registry

Test at least 128 bits of identifier entropy, authenticated-principal binding, active and queued admission limits, progress bounds, result size, cancellation, unknown outcome, verification, expiry, retained-result limits, cleanup, shutdown grace, and durable recovery when promised.

Protocol Tasks are not an executor. Python daemon threads, untracked `create_task`, .NET fire-and-forget `Task.Run`, and in-memory task stores advertised as fault tolerant fail the architecture test. Verify task support is forbidden, optional, or required per capability rather than inherited accidentally from an async return type.

### Browser automation

Test normalized account names, profile path containment, restrictive permissions, two-process profile locking, stale-lock recovery, account isolation, interactive-auth states, and explicit cleanup. Simulate login, consent, quota, selector drift, missing citation panel, ambiguous click completion, and browser crash as separate categories.

Treat returned webpage and AI-generated content as provenance-bearing untrusted input. Capture only bounded sanitized diagnostics.

### Transport conformance

Use real stdio and Streamable HTTP. Verify initialization, protocol version, listing with real schemas, invocation, malformed messages, protocol-native errors, cancellation, disconnect, explicit stateless/stateful behavior, and shutdown. Stdio additionally asserts protocol-only stdout and an allowlisted environment.

The deprecated two-endpoint HTTP+SSE transport is forbidden in new servers and generated artifacts. Test that `/sse` and `/message` are absent. When a documented temporary compatibility adapter exists, run a separate suite against it and prove it is disabled by default, isolated, allowlisted, policy-equivalent, owned, and scheduled for removal. Do not reject legitimate `text/event-stream` framing inside Streamable HTTP.

Origin tests include malformed values, explicit/default ports, bracketed IPv6, IDNA, reverse-proxy headers, empty Origin behavior, and wildcard syntax. HTTP tests enforce request-body, header, JSON-depth, response, concurrency, queue, session, and rate limits before unbounded buffering.

### Authentication and authorization

For .NET, verify `ClaimsPrincipal` is injected without appearing in the tool schema, `[Authorize]` is ineffective without `AddAuthorizationFilters()`, unauthorized tools are filtered from listing, endpoint authorization is enforced, and principal rate-limit partitions are distinct. Stdio identity comes from trusted process configuration or a message filter, never tool arguments.

For every platform, bind approval, task, artifact, browser account, target handle, and downstream credential to the authenticated principal and intended audience.

### Long-running work and exports

Test synchronous and task-based scans, updates, media generation, hardware checks, browser generation, and exports. Bound progress, task count, status payload, cancellation, expiry, cleanup, and restart behavior.

Export tests verify selection, maximum size, atomic destination, component-aware path allowlist, secure permissions, provenance, retention, confidential-field minimization, cancellation, and partial-file cleanup.

### Real-client workflow

Use an official client, inspector, or conformance tester to run discover-select-invoke-verify flows. Include a read, authorized mutation when applicable, confidential output policy, controlled error, unavailable capability, failed target, pagination termination, task polling, artifact retrieval, and cancellation.

For .NET, use `StdioClientTransport` with `InheritEnvironmentVariables=false`, real `ListToolsAsync`, `CallToolAsync`, structured output, and controlled `IsError`. Repeat representative workflows against the exact published artifact.

### Upstream contract

Use fakes, mock HTTP handlers, recorded fixtures, emulators, browser fixtures, canaries, or Testcontainers according to the integration. Verify timeout, cancellation, host identity, credential placement, status mapping, retry hints, pagination, ambiguous completion, UI drift, and partial failure rather than mocking the final return value.

For shell or device protocols, fuzz validated arguments and verify fixed executable or closed-template behavior. For API keys in query parameters, inspect logs, traces, exceptions, and proxy requests for leakage.

### Deployment artifact

Build the package, self-contained binary, Native AOT binary, or container that production will run. Start that exact artifact, wait for readiness, verify representative behavior, terminate during an in-flight call, and confirm cleanup. Production user, filesystem, network, secret, browser-profile, and environment restrictions are preserved.

For NuGet packages, parse only direct package/metadata fields: `package/metadata/id` and `package/metadata/version`, compare them to an explicit allowlist and validated tag-derived version, and publish only the verified manifest. A dependency appearing before package identity must not spoof the package.

## Archetype migration matrix

Every substantial migration runs the applicable regressions:

| Archetype | Mandatory migration regressions |
| --- | --- |
| large read-only aggregator | confidential reads, active profiles, safe paths, artifact/task bounds, dependency readiness |
| heterogeneous device controller | stable target identity, physical effect, SSRF, scoped privileges, expected disconnect |
| SSH network appliance | host fingerprint, immutable call options, keyed serialization, closed commands, restart verification |
| multi-backend administrator | no silent target fallback, backend matrix, quota race, secret cache policy, cleanup |
| financial API adapter | decimal/date semantics, query-secret redaction, idempotency key, pagination termination |
| browser automation | profile isolation/lock, shared-context race, interactive auth, session bounds, UI drift |

Run both the Python migration simulation and .NET migration simulation. A new reusable finding becomes a test category here; repository-specific names and fixtures remain in implementation repositories.

## Test doubles

Mock stable application-owned interfaces. Avoid patching SDK internals or production request context. Python decorator fakes return the original callable. .NET replaces services through DI. A compatibility adapter has its own exact package and SDK-version tests.

## CI matrix

Run the stable production SDK lane at minimum and preferred versions. Run prerelease or next-major SDKs in a separate candidate lane with exact pins and no publication. Candidate success does not replace stable production evidence.

Keep generator, unit, integration, smoke, e2e, conformance, live-backend, browser, artifact, and migration suites separately visible. A skipped suite declares its prerequisite and does not contribute misleading coverage.

## Verification

Break one generator, configuration-order, manifest, registration, invocation-kernel parity, risk-order, target, path, artifact, task, browser-profile, lifecycle, race, retry, pagination, schema, transport, authorization, sanitization, long-task, package-identity, and deployment path in a disposable branch and confirm the intended layer fails with actionable evidence.
