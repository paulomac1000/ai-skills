---
description: Python and FastMCP implementation profile with lifecycle, transport, manifest, concurrency, and SDK-upgrade controls.
doc_id: reference.python-fastmcp-profile
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Run unit, manifest, registration, lifecycle, transport-parity, cancellation, race, and content-shape regressions against every supported FastMCP major version.
---

# Python and FastMCP profile

## Project shape

Keep domain services, typed models, validators, and policy independent from FastMCP. A composition root loads validated settings, creates application-owned clients, registers components, installs middleware, and selects stdio or Streamable HTTP.

Use current public FastMCP concepts for new code. FastMCP 3 providers, transforms, authorization, middleware, and stateless HTTP are preferred when they solve the requirement. Supporting FastMCP 2 and 3 simultaneously requires an explicit compatibility adapter and CI matrix; do not scatter `hasattr` probes through the server.

## Lifecycle ownership

Use an async lifespan or an application-owned async context manager for process resources. Account for SDK versions whose lifespan callback is connection-scoped: process clients must not be recreated per SSE or HTTP connection.

Initialize mandatory clients before readiness. Keep successful clients when optional targets fail, record unavailable targets, and close every initialized client on startup failure and shutdown. Do not assign application state through private SDK attributes outside the compatibility adapter.

Request context is read only inside live invocations. Pass application context into domain services explicitly. Use `contextvars` for async request correlation and reset tokens in `finally`.

## Transport parity

Use `stdio` for local subprocess integration and `http` for Streamable HTTP. Treat `sse` as legacy compatibility. Build an ASGI app when production needs middleware, workers, or an existing web host.

The same registration, manifests, auth policy, error mapping, and sanitization serve every transport. A REST bridge delegates through an application adapter or public MCP client; it never calls private tool wrappers directly.

Stdio logs only to stderr. HTTP binds to loopback by default, validates Origin, authenticates remote calls, and uses restrictive CORS only when a browser client requires it. Use stateless HTTP for horizontal scaling unless the server needs session-bound protocol features.

## Manifest coverage

Keep manifests in an application-owned registry keyed by stable component name. Generate descriptions or annotations from the registry when useful, but never infer a missing safe manifest from a docstring prefix.

After registration, enumerate components through public APIs or one compatibility adapter. Fail startup and CI on missing, orphaned, or inconsistent manifests. Capability introspection is zero-I/O and exposes the governed registry over MCP.

Registration wrappers may add `_meta`, tracing, or sanitization centrally. Wrapper order is tested, and argument-binding or protocol exceptions are not accidentally converted into successful content.

## Concurrency enforcement

Do not mutate shared client settings such as timeout, target, headers, or credentials immediately before `await`. Pass immutable per-call options or use separate clients.

Map `concurrent_safe: false` to a narrow keyed `asyncio.Lock`, semaphore, queue, or isolated client. Bound executor work and queues. Use `asyncio.to_thread` or a bounded executor for blocking libraries.

Async connection pools are event-loop-affine. Integration helpers reuse one owning event loop for persistent clients instead of creating a loop per tool call. Add overlap tests that prove request IDs, targets, timeouts, and results cannot cross.

Cancellation is re-raised after bounded cleanup. Broad exception handling must not swallow the runtime's cancellation exception.

## Boundary sanitization

Configure logging once and send it to stderr. Sanitize credentials and protected network or identity data at the logging formatter or handler boundary.

Sanitize model-visible responses separately and recursively. Sensitive dictionary keys, bearer tokens, passwords, private keys, and upstream error bodies are redacted before serialization. Log sanitization alone is not sufficient.

Operator write enablement is checked before any I/O in every mutating path. It is distinct from manifest confirmation metadata and caller authorization.

## SDK compatibility

Pin a tested SDK range. Prefer supported `list_tools`, client, provider, transform, middleware, and transport APIs. Private `_tools`, `_tool_manager`, or provider internals belong only in a compatibility adapter with version tests and fail-closed behavior.

Decorator fakes preserve the callable. `call_tool` and content-block representations are normalized only at the test adapter boundary. Do not assume a raw JSON string when the SDK returns protocol content blocks or structured content.

Run tests against the minimum and preferred supported versions. An SDK upgrade must prove registration, schema, middleware state, lifespan behavior, transport parity, and cleanup before release.

## Errors and schemas

Use typed parameters and generated schemas, then add application validation for cross-field, resource, path, command, and content-size rules before I/O. Do not publish placeholder object schemas.

Return or raise errors according to the SDK's protocol contract. Preserve validation, auth, conflict, timeout, cancellation, unavailable dependency, and internal categories. Structured application errors include stable code, retryability, suggestion, and bounded alternatives.

## Test strategy

- domain tests call application services directly;
- manifest tests enumerate every public component;
- lifecycle tests cover all-failed and partially-failed startup;
- race tests overlap calls sharing clients, locks, and correlation state;
- transport tests use real stdio and HTTP;
- content tests cover text blocks and structured content;
- deployment tests start the built wheel or container;
- unit, integration, smoke, and e2e markers are reported separately.

## Verification

Run the profile matrix against each supported FastMCP major version. Invoke representative tools through a real client over stdio and Streamable HTTP, cancel an in-flight call, overlap non-concurrent-safe calls, and verify deterministic cleanup and redaction.
