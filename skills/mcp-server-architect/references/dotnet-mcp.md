---
description: .NET MCP implementation profile for official SDK hosting, lifecycle, transport parity, manifests, concurrency, security, and tests.
doc_id: reference.dotnet-mcp-profile
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Build analyzer-clean stdio and ASP.NET Core hosts, enumerate and invoke tools through the public C# MCP client, cancel and overlap calls, and run packaged-artifact conformance tests.
---

# .NET MCP profile

## Project shape

Use the official C# SDK package matching the host:

- `ModelContextProtocol.Core` for low-level client or server APIs;
- `ModelContextProtocol` for hosting, dependency injection, and stdio;
- `ModelContextProtocol.AspNetCore` for Streamable HTTP.

Application and domain projects do not reference MCP packages. The host registers typed services and exposes thin `[McpServerToolType]` classes with `[McpServerTool]` methods. Pin a tested stable SDK range and treat obsolete or experimental diagnostics as reviewed build failures.

## Lifecycle ownership

Let Generic Host or ASP.NET Core own process resources. Register immutable configuration with options validation, reusable `HttpClient` instances through `IHttpClientFactory`, and disposable clients with the correct DI lifetime.

Singleton services must be thread-safe and must not hold caller identity, request cancellation, mutable target selection, or per-call timeout. Scoped services belong to the supported request or HTTP scope. Hosted services own background loops and stop them through host cancellation.

Startup validates mandatory dependencies before readiness. Optional backends expose capability health. Shutdown stops accepting work, cancels or drains within a bound, disposes scopes, and closes clients exactly once.

## Transport parity

For stdio, use `AddMcpServer().WithStdioServerTransport()` and configure console logging to stderr. For HTTP, use `ModelContextProtocol.AspNetCore`, `WithHttpTransport`, and `MapMcp` on one Streamable HTTP endpoint.

Prefer stateless HTTP when sampling, elicitation, resumability, or cross-request state is unnecessary. Stateful mode configures bounded idle sessions, maximum session count, authorized session migration when required, and deterministic disposal.

The same tool types, manifests, filters, authorization, validation, result mapping, and telemetry serve both transports. Legacy SSE is opt-in compatibility only and receives its own regression tests.

## Manifest coverage

Store governed manifests in typed immutable records keyed by public tool name. Use one registration extension or source-generated registry to associate manifests with tools. Missing metadata fails startup and tests; it never receives a read-only default.

Enumerate tools with the public MCP client and compare names and schemas with the registry. Expose a zero-I/O capability tool when consumers need manifest data over MCP. Protocol annotations may be projected from the registry but remain advisory.

Use `IOptions` validation or dedicated validators for manifest fields and risk consistency. Runtime filters enforce scopes, write gates, timeouts, concurrency, and redaction described by the manifest.

## Concurrency enforcement

Accept `CancellationToken` on every tool that performs I/O and pass it to EF Core, `HttpClient`, streams, process execution, channels, locks, and delays. Never use `.Result`, `.Wait()`, or sync-over-async.

Do not mutate `HttpClient.Timeout`, shared headers, client target, or singleton options per request. Use request messages, typed clients, immutable option objects, or separate keyed clients.

Map non-concurrent-safe operations to a narrow `SemaphoreSlim`, keyed lock, `Channel`, actor, or resource-specific transaction. A manifest flag without enforcement is invalid. Add race tests for target selection, correlation, timeout, cache updates, and disposal.

Use `Activity` and explicit request objects for context propagation. `AsyncLocal` is infrastructure-only and must be cleared; caller identity is obtained from the supported request context or `ClaimsPrincipal`.

## Boundary sanitization

Use structured `ILogger` messages and redaction before values reach a sink. `ILogger.BeginScope` may carry safe correlation and principal classes, never raw tokens or protected payloads.

Sanitize model-visible result DTOs independently. Central filters or result adapters redact secrets, authorization headers, credentials, private key material, and bounded upstream details before serialization.

Operator write enablement, caller authorization, and consumer confirmation metadata are separate controls. Authorization resolves the target resource and intended audience before the tool service performs I/O.

## SDK compatibility

Use public builder, transport, filter, client, and protocol APIs. Do not reflect over private tool registries. Assembly scanning with `WithToolsFromAssembly` is acceptable when tests enumerate the resulting public contract; explicit `WithTools<T>` registration is preferable for security-sensitive hosts.

Keep SDK-specific code in the host and one adapter. When upgrading:
- review release notes and compiler diagnostics;
- verify package selection and transport defaults;
- test stateless capability advertisement and legacy transport behavior;
- serialize protocol DTOs round-trip;
- run the official client and conformance suite;
- verify transport-closure diagnostics and graceful shutdown.

Do not copy Python decorator or lifespan mechanisms into .NET. Enforce the same invariant through DI, host lifetime, filters, and typed request context.

## Errors and schemas

Use typed records and `System.Text.Json` compatible schemas. Add application validation for cross-field, authorization, path, command, and content-size rules before I/O.

Central filters or adapters map domain exceptions to stable validation, authentication, authorization, not-found, conflict, rate-limit, timeout, cancellation, unavailable dependency, upstream, and internal categories. Preserve `OperationCanceledException` and transport abort semantics.

Return typed content or structured results deliberately. Test protocol content blocks and serialized wire shape separately.

## Test host

Build the real Generic Host and ASP.NET Core test host. Replace application-owned interfaces through DI. Use mock HTTP handlers, in-memory test servers, recorded fixtures, or Testcontainers at the appropriate layer.

Use the public C# MCP client to initialize, list, invoke, cancel, and close. Add stdio tests that reject non-protocol stdout, HTTP tests for Origin, AllowedHosts, CORS, authentication, stateless/stateful behavior, and race tests for shared services.

## Deployment

Expose startup, readiness, liveness, and capability health through ASP.NET Core health checks where HTTP hosting is used. Container tests run the exact published artifact, non-root when production does, and verify termination during in-flight work.

## Verification

Run analyzer-enabled build, manifest and policy tests, real-host registration and invocation, cancellation propagation, concurrency enforcement, structured error mapping, response/log redaction, stdio isolation, Streamable HTTP conformance, and packaged-artifact smoke tests.
