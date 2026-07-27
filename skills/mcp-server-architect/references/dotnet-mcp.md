---
description: .NET MCP implementation profile for official SDK hosting, lifecycle, transport parity, manifests, concurrency, security, and tests.
doc_id: reference.dotnet-mcp-profile
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Generate a fresh .NET server, restore and build analyzer-clean stdio and ASP.NET Core hosts, enumerate and invoke tools through the official C# MCP client, cancel and overlap calls, and smoke the exact published artifact.
---

# .NET MCP profile

## Supported lane and package selection

Use a reviewed stable release of the official C# SDK. At the time this profile was hardened, the tested production lane is `ModelContextProtocol` and `ModelContextProtocol.AspNetCore` 1.4.1 on .NET 10. Keep the exact version in central package management and exercise a separate non-publishing candidate lane before adopting future major or prerelease SDKs.

Choose the smallest package matching the host:

- `ModelContextProtocol.Core` for low-level client or server APIs;
- `ModelContextProtocol` for hosting, dependency injection, clients, and stdio;
- `ModelContextProtocol.AspNetCore` for Streamable HTTP.

Application and domain projects do not reference MCP packages. The host registers typed services and exposes thin `[McpServerToolType]` classes with `[McpServerTool]` methods. Treat obsolete or experimental diagnostics as reviewed build failures rather than suppressing them globally.

## Lifecycle ownership

Let Generic Host or ASP.NET Core own process resources. Register immutable configuration with validation before dependency construction, reusable `HttpClient` instances through `IHttpClientFactory`, and disposable clients with the correct DI lifetime.

Singleton services are thread-safe and do not hold caller identity, request cancellation, mutable target selection, per-call timeout, or request-specific headers. Tool instances created through generic registration are invocation adapters, not state stores. Hosted services own supervised loops and stop them through host cancellation.

Startup validates mandatory dependencies before readiness. Optional backends expose capability health. Shutdown stops accepting work, propagates cancellation, drains or terminates within a bound, disposes scopes, and closes clients exactly once. Do not start untracked `Task.Run` work from a tool and call it a task record.

## Transport parity

For stdio, use `AddMcpServer().WithStdioServerTransport()` and route every diagnostic to stderr. For HTTP, use `ModelContextProtocol.AspNetCore`, `WithHttpTransport`, explicit `options.Stateless = true` or `false`, and `MapMcp` on one Streamable HTTP endpoint.

The deprecated two-endpoint HTTP+SSE transport is forbidden in new .NET servers. Do not set `EnableLegacySse`, including setting it to `false`: the property is obsolete and can fail warnings-as-errors builds with `MCP9004`. Modern Streamable HTTP may legitimately return `text/event-stream`; that does not make it the legacy transport.

Prefer stateless HTTP when sampling, elicitation, roots, unsolicited notifications, subscriptions, or per-client cross-request state are unnecessary. Stateful mode is explicit and configures bounded idle sessions, maximum session count, principal-bound deletion or resumption, sticky-routing expectations, and deterministic disposal. Never rely on the SDK default because it may change.

The same tool types, manifests, invocation kernel, authorization, validation, result mapping, and telemetry serve both transports. A temporary legacy compatibility adapter is a separate, disabled-by-default deployment with a named owner, allowlisted clients, dedicated tests, and a removal deadline.

## Manifest coverage

Store governed manifests in typed immutable records keyed by public tool name. Use one registration extension or generated registry to associate manifests with tools. Missing metadata fails startup and tests; it never receives a read-only default.

Enumerate tools with the public `McpClient` and compare names and schemas with the registry. Expose a zero-I/O capability tool when consumers need manifest data over MCP. Filter discovery by caller scopes and active dependencies. Protocol annotations are projections from the governed registry and remain advisory.

Project `ReadOnly`, `Destructive`, `Idempotent`, `OpenWorld`, `UseStructuredContent`, and `OutputSchemaType` deliberately. A typed C# return type is not proof that structured content or an output schema is present on the wire. Tests inspect `Tool.OutputSchema`, `CallToolResult.StructuredContent`, and `CallToolResult.IsError` through the public client.

## Authentication and authorization

For HTTP, enforce authentication before principal-partitioned rate limiting and run authorization in between. Configure endpoint authorization and call `AddAuthorizationFilters()` when `[Authorize]` or `[AllowAnonymous]` attributes are used on tools, prompts, or resources. Without that activation, the attributes are not an enforcement boundary.

Prefer the SDK-supported `ClaimsPrincipal` parameter injection in tool methods. It is excluded from the model-visible schema and works with transport context. `IHttpContextAccessor` is HTTP-specific and must not leak into domain code. For stdio, establish identity and scopes from trusted process configuration or a message filter; never accept them as model-controlled arguments.

Authorize the resolved stable resource identity, not only the public tool name. Bind approvals, artifacts, tasks, browser profiles, and target handles to the principal. Operator write enablement, caller authorization, and trusted approval are independent controls.

## Concurrency enforcement

Accept `CancellationToken` on every tool that performs I/O and pass it to EF Core, `HttpClient`, streams, process execution, channels, locks, and delays. Never use `.Result`, `.Wait()`, or sync-over-async.

Do not mutate `HttpClient.Timeout`, shared default headers, client target, or singleton options per request. Use request messages, typed clients, immutable option objects, or separate keyed clients.

Map non-concurrent-safe operations to a narrow `SemaphoreSlim`, keyed lock, `Channel`, actor, or resource-specific transaction. A manifest flag without runtime enforcement is invalid. Partition rate limiting only after the authenticated principal is available; otherwise all users collapse into an `anonymous` partition.

Use `Activity` and explicit request objects for context propagation. `AsyncLocal` is infrastructure-only and must be cleared; caller identity comes from the supported request context or `ClaimsPrincipal`.

## Boundary sanitization

Use structured `ILogger` messages and redaction before values reach a sink. `ILogger.BeginScope` may carry safe correlation and principal classes, never raw tokens or protected payloads.

Sanitize model-visible result DTOs independently. Central filters or result adapters redact secrets, authorization headers, credentials, private key material, and bounded upstream details before serialization.

Stdio clients should default `InheritEnvironmentVariables = false` and build an explicit environment allowlist with `StdioClientTransportOptions.GetDefaultEnvironmentVariables()`. Forward only required credentials and runtime variables.

## SDK compatibility

Use public builder, transport, filter, client, and protocol APIs. Do not reflect over private tool registries. Prefer generic `WithTools<T>()`, `WithPrompts<T>()`, and `WithResources<T>()` registration. `WithToolsFromAssembly()` and other non-generic scanning APIs require runtime reflection and carry `RequiresUnreferencedCode`; they are not the default for Native AOT or hardened hosts.

Keep SDK-specific code in the host and one adapter. When upgrading:

- review release notes, diagnostics, and transport defaults;
- verify exact package selection and lock or central-version resolution;
- test explicit stateless and stateful behavior;
- confirm legacy HTTP+SSE remains absent;
- serialize protocol DTOs round-trip;
- run the public client and conformance suite;
- verify authorization filters, tool-list filtering, cancellation, closure diagnostics, and graceful shutdown;
- publish and smoke the exact deployment artifact;
- keep future major or prerelease SDKs in a non-publishing candidate lane until parity evidence exists.

Do not copy Python decorator or lifespan mechanisms into .NET. Enforce the same invariant through DI, host lifetime, filters, typed request context, and supervised background services.

## Errors and schemas

Use typed records and `System.Text.Json` compatible schemas. Data annotations influence generated schema but are not runtime validation. Validate required fields, lengths, ranges, cross-field rules, authorization, paths, commands, and content size before approval consumption or I/O.

Tool execution, validation, and business errors are represented as `CallToolResult` with `IsError = true` or a controlled `McpException`. Returning a DTO such as `{ success = false }` is still a protocol-success unless the adapter sets the native error contract. Preserve `OperationCanceledException` and transport abort semantics.

Return typed content or structured results deliberately. Set `UseStructuredContent = true` and `OutputSchemaType` when a tool returns `CallToolResult` or when schema inference must remain stable. Test protocol content blocks and serialized wire shape separately.

## Tasks and long-running work

MCP Tasks are a protocol contract, not an executor. Async return types may advertise optional task augmentation after a task store is configured, so task support must be reviewed per capability rather than inherited accidentally.

`InMemoryMcpTaskStore` is acceptable only for tests and single-process non-durable deployments. Production work uses a principal-bound durable store and a supervised executor or external queue. Task status survives process ownership boundaries only when its metadata and work execution are both durable. Polling is primary; notifications are optional. Fire-and-forget examples do not satisfy production fault tolerance.

## Test host

Build the real Generic Host and ASP.NET Core test host. Replace application-owned interfaces through DI. Use mock HTTP handlers, in-memory test servers, recorded fixtures, or Testcontainers at the appropriate layer.

Use the official C# `McpClient` to initialize, list, invoke, observe structured output and `IsError`, cancel, and close. Add stdio tests that reject non-protocol stdout and environment leakage. Add HTTP tests for body limits, Origin, AllowedHosts, restrictive CORS, authentication, authorization-filtered listing, principal rate-limit partitioning, explicit stateless/stateful behavior, session ownership, and concurrency races.

Test generic registration under trimming and Native AOT when those artifacts are advertised. Test task support as forbidden, optional, or required per capability. A successful `dotnet build` does not substitute for real-client and exact-artifact execution.

## Deployment

Expose startup, readiness, liveness, capability health, and task health separately. Liveness is process health; readiness verifies mandatory domain dependencies. Registration count or a bound port never proves readiness.

Container and self-contained tests run the exact published artifact, non-root when production does, and verify termination during in-flight work. NuGet release workflows read package identity only from direct `package/metadata/id` and `package/metadata/version` elements, compare to an explicit allowlist and validated tag-derived version, and publish only the verified manifest.

## Verification

Run the bundled .NET generator first. Restore and build with analyzers and warnings as errors; enumerate real schemas through the public client; invoke representative read and fail-closed write paths; verify `structuredContent` and `isError`; test cancellation, authorization, target identity, approval binding, concurrency, stdio isolation, Streamable HTTP, body limits, readiness/liveness, and the exact published artifact. Run the .NET migration simulation against read-only, physical-device, financial, and multi-backend/SSH archetypes before claiming production parity.
