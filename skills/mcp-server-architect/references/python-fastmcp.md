---
description: Python MCP implementation profile with generation, configuration, lifecycle, invocation-kernel, transport, manifest, concurrency, artifact, browser, and SDK-upgrade controls.
doc_id: reference.python-fastmcp-profile
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Generate a fresh project and run its official in-memory client suite, then run configuration-order, unit, manifest, registration, invocation-parity, lifecycle, transport, cancellation, executor, race, path, task, content-shape, browser-profile, and artifact regressions against every supported SDK lane.
---

# Python and FastMCP profile

## Generated baseline

For a new Python server, start with `tools/generate_python_server.py`. The generator is stdlib-only, deterministic, atomic, refuses existing targets, and emits an installable project using the stable official MCP Python SDK lane. The generated server contains typed immutable settings, domain code, application-owned manifests, one invocation kernel, official SDK registration, stdio and loopback Streamable HTTP, tools, resources, a prompt, server instructions, structured errors, packaging, Docker, pinned CI, and a real-client test.

The repository CI installs the pinned stable SDK, generates a fresh project, compiles it, and runs its own suite through `mcp.shared.memory.create_connected_server_and_client_session`. Text inspection alone is not generator verification. A generated project becomes production code only after replacing the sample adapter, reviewing manifests, adding principal and resource authorization, and implementing applicable upstream, transport, artifact, task, filesystem, browser, and deployment tests.

## Project shape

Keep typed settings, domain services, target resolvers, validators, policy, task state, artifact state, and response models independent from the MCP SDK. A composition root loads and validates settings, creates application-owned dependencies, builds one invocation kernel, registers components, installs middleware, and selects stdio or Streamable HTTP.

Do not use module import as configuration or lifecycle. Modules that call `os.getenv`, create clients, register tools, or perform network validation at import time make `.env` loading order, tests, workers, and reload behavior unpredictable. Load settings first, freeze a typed snapshot, then construct the application explicitly. Import-time construction may expose a local test application only when it performs no secret loading, I/O, or process resource allocation.

## SDK lanes and dependency policy

Record the exact SDK family and import surface. The official MCP Python SDK and the separately distributed FastMCP package are not treated as interchangeable because similarly named classes can have different lifecycle, provider, middleware, transport, and content APIs.

For production, use the stable official SDK line with an upper bound that excludes the next major until migration is complete. The generated baseline uses `mcp>=1.27.2,<2`, while repository verification uses an exact stable pin. While official SDK v2 is pre-release, it belongs to a separate experimental CI lane with an exact pin and cannot define the production artifact. A candidate major becomes production-supported only after registration, lifecycle, transport, policy parity, content, cancellation, and artifact matrices pass.

Pin direct dependencies and record the minimum and preferred tested versions. Do not write broad compatibility claims such as “supports version 2 and 3” without package identity, exact ranges, and evidence.

## Lifecycle ownership

Use an async lifespan or application-owned async context manager for process resources. Account for SDK versions whose lifespan callback is connection-scoped: process clients must not be recreated per legacy SSE or HTTP connection.

Initialize mandatory clients before readiness. Keep successful clients when optional targets fail, record unavailable targets, and close every initialized client on startup failure and shutdown. Do not assign application state through private SDK attributes outside a temporary compatibility adapter.

Every target has stable identity, health, capability matrix, credential context, rate-limit scope, client owner, and concurrency key. An unavailable requested or configured default target returns a controlled error. It never falls back to the first healthy target for mutation, dangerous execution, or confidential reads.

Request context is read only inside live invocations. Pass application context into domain services explicitly. Use `contextvars.ContextVar` for request ID, principal, target, and deadline in asynchronous code. Capture and reset tokens in `finally`; `threading.local` is not request isolation when multiple asyncio tasks share a thread.

## Invocation kernel

Build one application-owned async entry point that accepts component name, typed arguments, caller context, transport metadata, and deadline. In this order it:

1. resolves the manifest and active capability;
2. validates and normalizes input;
3. resolves and revalidates stable target identity;
4. authenticates and authorizes the principal;
5. checks operator policy and confirmation metadata;
6. applies deadline, rate limit, concurrency, and idempotency controls;
7. invokes the domain operation;
8. maps errors and ambiguous outcomes;
9. minimizes and sanitizes output;
10. emits correlation, target, policy, and result telemetry.

MCP, REST, tests, and compatibility transports delegate to this kernel. They may translate protocol envelopes, but they never call a raw registered function, monkey-patch request context, synthesize a fake SDK context, or duplicate policy.

## Transport parity

Use stdio for local subprocess integration and Streamable HTTP for remote integration. Treat legacy SSE as a separate compatibility transport with an expiry plan. Build an ASGI app when production needs middleware, workers, reverse-proxy integration, or shared HTTP hosting.

The same registration, manifests, active profile, target resolution, auth policy, error mapping, sanitization, and invocation kernel serve every transport. A REST bridge uses an application adapter or a public MCP client; it does not inspect private tool wrappers or reconstruct schemas from `inspect.signature` when the SDK already owns the public schema.

Stdio logs only to stderr. HTTP binds to loopback by default, canonicalizes and validates Origin, authenticates remote calls, and uses restrictive CORS only when a browser client requires it. A boolean acknowledgement that permits `0.0.0.0` does not replace TLS, authentication, authorization, host policy, and network isolation.

Bound request body, header size, JSON depth, response size, concurrency, queues, and sessions. Reject an oversized body before buffering it completely. Session and task identifiers use `secrets` or UUID4-class generators with at least 128 bits of entropy and remain principal-bound.

Origin tests cover scheme, host canonicalization, default and explicit ports, IPv4, bracketed IPv6, IDNA, empty Origin policy, malformed input, configured wildcards, reverse-proxy headers, and DNS rebinding. Do not feed wildcard ports into parsers that only accept numeric ports.

## Manifest coverage

Keep manifests in an application-owned registry keyed by stable component name. Generate descriptions or annotations from the registry when useful, but never infer a missing safe manifest from a docstring prefix.

Manifest factories provide conservative syntax, not semantic proof. Write, create, publish, copy, command, restart, browser action, update, OTA, and state-transition operations default to non-retryable and non-idempotent until their mechanism is declared and tested. Read operations still declare confidentiality, output bounds, cost, artifact impact, and retry conditions.

After registration, enumerate components through public APIs or one compatibility adapter. Fail startup and CI on missing, orphaned, duplicated, inactive-but-invokable, or inconsistent manifests. Capability introspection is zero-I/O and exposes supported and active catalogs over MCP.

Install wrappers or transforms before registration whenever schema generation depends on the callable. Preserve signatures, annotations, schemas, cancellation, and protocol-native errors. Wrapper order is tested, and argument-binding or protocol exceptions are not converted into successful text content.

## Concurrency enforcement

Do not mutate shared client settings such as timeout, target, headers, credentials, retry mode, browser visibility, or active account immediately before `await`. Pass immutable per-call options, serialize a coordinated transition, or use separate clients and profiles.

Map `concurrent_safe: false` to a narrow keyed `asyncio.Lock`, semaphore, queue, actor, or isolated client. The key follows the protected resource: device identity, host, account, credential quota, file, browser profile, or global upstream. Lock acquisition is cancellable and deadline-bound.

Rate limiters use a lock-safe token bucket or reservation model. A shared `last_request_at` timestamp without serialization does not enforce an upstream quota. Honor `Retry-After` only within the remaining deadline, add jitter, and never let a response-level hint override a manifest retry veto.

Async connection pools are event-loop-affine. Reuse one owning event loop for persistent clients. Request code must not call `asyncio.run`, `run_until_complete`, or create a new loop to reach an async SDK API.

Use true async clients where practical. Blocking libraries run through a bounded executor with queue limits, deadlines, saturation metrics, and shutdown. `asyncio.to_thread` without an executor policy is not a production capacity control. Cancellation cannot stop an already running blocking call, so the downstream timeout must be shorter than the MCP deadline and late results must be discarded safely.

Add overlap tests proving request IDs, principals, targets, timeouts, rate limits, browser contexts, and results cannot cross. Cancellation is re-raised after bounded cleanup; broad exception handling must not swallow the runtime cancellation exception.

## Filesystem, artifacts, and task state

Use `Path.resolve` plus component-aware containment such as `is_relative_to`; lexical `startswith` checks are prohibited. Define no-follow, symlink, reparse-point, archive extraction, and time-of-check/time-of-use behavior for every write or delete. Use atomic replacement and server-owned roots.

Persistent results are governed artifacts. Record opaque artifact ID, owner, target, operation, MIME type, byte size, checksum when useful, creation, expiry, and deletion. Do not expose host paths as public handles. Bound previews, downloads, retention, and cleanup.

Long-running work uses a bounded task registry or durable store, not daemon threads or untracked `create_task`. Track accepted, running, verifying, succeeded, failed, cancelled, unknown-outcome, and expired states. Shutdown stops admission and deterministically cancels, persists, or waits for owned work.

## Browser automation profile

Treat a writable browser profile as a credential store. Use a normalized per-account directory, restrictive permissions, a process lock, explicit cleanup, and an encryption or OS-store policy when required. A client-supplied account name cannot become a filesystem path.

Serialize shared browser context transitions such as visible/headless mode, reauthentication, account switching, profile cleanup, and browser recreation. One request cannot close a context used by another request. Model interactive authentication as explicit states and never have the agent submit a password.

Centralize selectors and expected semantic landmarks. Run a low-cost canary, detect consent/login interstitials, capture sanitized diagnostics, and classify selector or DOM drift separately from auth, quota, timeout, and upstream errors. A state-changing browser action with an ambiguous result is reconciled before retry.

External AI or webpage content carries provenance and is treated as untrusted. Server instructions document cross-tool ID flows, polling chains, and profile limitations without granting authority.

## Boundary sanitization

Configure logging once and send it to stderr. Sanitize credentials and protected network or identity data at the logging formatter or handler boundary. Disable or filter URL logging when an upstream protocol places credentials in query parameters.

Sanitize model-visible responses separately and recursively. Apply field-aware minimization before regular-expression redaction. Sensitive dictionary keys, bearer tokens, passwords, private keys, cookies, browser profiles, upstream error bodies, financial data, and durable exports follow their confidentiality policy before serialization.

Operator enablement is checked before any I/O in every mutating path. Prefer capability- and target-scoped policy to one global write flag. Isolate high-privilege capabilities such as raw shell, container sockets, firmware, browser profiles, and unrestricted filesystem access into separate profiles or processes.

## Target and network safety

A mutable address is not a stable resource identity. Discovery returns both stable identity and observed address. Mutating calls re-resolve and verify that the address still belongs to the authorized identity immediately before I/O.

For agent-supplied hosts and URLs, validate normalized scheme, hostname, resolved addresses, CIDR, port, redirect destinations, and DNS changes. Apply checks after every redirect and resolution. Bind authorization to the resolved target, not the original string alone.

SSH and other privileged remote transports verify host identity in hardened deployments. A disabled host-key check is a documented development exception, not a production default. A first-use enrollment flow records and confirms the fingerprint before privileged tools become active.

## Errors, schemas, and domain values

Use typed parameters and SDK-generated schemas, then add application validation for cross-field, target, path, command, URL, money, date, content-size, artifact, and task rules before I/O. Do not publish placeholder object schemas.

Preserve validation, auth, not-found, conflict, rate-limit, timeout, cancellation, unavailable dependency, upstream, UI-drift, ambiguous-outcome, and internal categories. Do not collapse all HTTP exceptions to `None`, `False`, or one generic code. Preserve safe upstream status and retry guidance without exposing raw protected bodies.

Money uses `Decimal` or integer minor units with currency, sign, range, and rounding policy. Public dates use ISO 8601 and explicit timezone or date-only semantics. Localized upstream formats are converted only inside the adapter.

Pagination declares stable ordering, page or cursor semantics, page size, continuation, and termination. A non-empty page does not imply `has_more`. Test empty, partial, full-final, changing-data, invalid-cursor, and maximum-page cases.

## Long-running and disconnecting operations

Scans, exports, updates, media generation, hardware tests, firmware operations, browser generation, and bulk workflows declare synchronous or task-based execution. Task-based operations expose status, bounded progress, cancellation, final result, expiry, and cleanup.

Operations expected to break connectivity return accepted or in-progress with resolved target, verification deadline, and follow-up capability. They are not reported as generic retryable timeouts. Multi-step changes expose plan, per-step result, postcondition, and compensation.

Generated files use destination allowlists, atomic replacement, secure permissions, maximum size, provenance, retention, and cancellation. Confidential results are not cached unless a reviewed cache policy defines encryption, scope, TTL, eviction, and audit.

## SDK compatibility

Prefer supported registration, client, provider, transform, middleware, and transport APIs. Private `_tools`, `_tool_manager`, provider internals, `_lifespan_data`, or raw server objects belong only in a compatibility adapter with explicit package/version tests and fail-closed behavior.

The compatibility adapter contains no target, auth, retry, manifest, or domain decisions. It does not monkey-patch SDK context or import test mocks into production. It records which path was selected and fails startup when enumeration or invocation is incomplete.

Normalize content blocks and structured content only at the transport or compatibility boundary. Preserve protocol-native errors and unknown metadata. An SDK upgrade proves registration, schemas, middleware state, active profiles, lifecycle, transport parity, cancellation, cleanup, and packaged execution before release.

## Test strategy

- generator tests create two byte-identical projects, compile them, and execute one through a real official MCP client;
- configuration-order tests prove `.env` or secret sources are loaded before settings capture;
- domain tests call application services directly;
- manifest tests enumerate supported, active, and registered components;
- invocation-kernel tests compare MCP, REST, and test adapters;
- lifecycle tests cover all-failed, partial, failed-default, owner-scoped disconnect, and cleanup paths;
- target tests cover identity changes, no-silent-fallback, and authorization after resolution;
- race tests overlap clients, locks, quotas, executors, browser contexts, profile transitions, and correlation state;
- retry tests cover mutation veto, idempotency keys, `Retry-After`, ambiguous completion, and deadline exhaustion;
- filesystem and artifact tests cover sibling-prefix, symlink swap, extraction, byte limits, retention, and opaque handles;
- task tests cover admission, entropy, progress, cancellation, restart or recovery, expiry, and shutdown;
- browser tests cover profile isolation, process lock, interactive auth, UI drift, provenance, and sanitized diagnostics;
- pagination tests prove termination;
- transport tests use real stdio and Streamable HTTP;
- content tests cover text blocks, structured content, confidentiality, and exports;
- deployment tests start the built wheel or container;
- stable and candidate SDK lanes remain separately visible.

## Verification

Run the generator and its real-client suite. Then run representative tools through a real client over stdio and Streamable HTTP. Cancel an in-flight async and blocking call, saturate the executor, overlap non-concurrent-safe calls, invalidate the default target, change a discovered address identity, force a rate limit, finish pagination, attempt path and symlink escapes, expire artifacts and tasks, rotate a browser profile, simulate UI drift and ambiguous mutation completion, and verify deterministic cleanup, policy parity, provenance, and redaction.
