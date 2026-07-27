---
description: Mapping from production MCP incidents to language-neutral invariants and correct Python and .NET controls.
doc_id: reference.mcp-cross-language-invariant-map
type: reference
status: active
rigor: informative
owners: [repository-maintainers]
---

# MCP cross-language invariant map

| Production incident | Language-neutral invariant | Python realization | .NET realization |
| --- | --- | --- | --- |
| private tool storage changed between SDK releases | public registration is the contract | public provider/client API; one tested compatibility adapter | public `McpClient`; generic `WithTools<T>()`; no reflection into registries |
| unclassified tools were auto-marked read-only | missing safety metadata fails closed | governed manifest registry; startup and CI coverage gate | typed immutable manifest registry plus startup validation |
| risk prefix and manifest drifted | one source owns capability semantics | generate projections from manifest | project annotations/descriptors from typed manifest and compare real schemas |
| lifespan ran at a different scope than expected | every resource has one declared owner scope | application lifespan separate from connection callback | Generic Host and DI lifetime; session disconnect does not dispose process clients |
| partial backend startup was hidden by healthy status | readiness and capability health are distinct | failed-target registry and readiness gate | tagged health checks with separate liveness/readiness and per-capability state |
| all backends failed but transport started | no useful workload means not ready | fail startup when mandatory client set is empty | startup validation prevents readiness; bound port is not proof |
| shared SSH client timeout was mutated per call | shared clients do not carry mutable request options | immutable call options or keyed client/lock | request message or typed client; never mutate singleton timeout or headers |
| manifest said non-concurrent-safe but calls overlapped | declared safety is enforced | keyed `asyncio.Lock`, semaphore, queue, or isolated client | keyed lock, `SemaphoreSlim`, `Channel`, actor, or transaction |
| integration test created a new event loop per call | async resources remain on their owning scheduler | shared loop for persistent async clients | one host and async test lifetime; no `.Result`, `.Wait()`, or sync-over-async |
| request ID leaked across concurrent tasks | request context is scoped and concurrency-safe | `contextvars` with reset | `Activity`, request scope, explicit context; limited cleared `AsyncLocal` |
| logging was sanitized but responses leaked secrets | every egress boundary is sanitized | formatter plus recursive response sanitizer | logging redaction plus result filter/DTO sanitizer |
| operator write flag was confused with user consent | enablement, authorization, and approval are independent | pre-I/O write gate plus auth policy and principal-bound approval | options gate plus `ClaimsPrincipal`, resource authorization, and principal-bound approval registry |
| custom HTTP endpoint returned dummy schemas | advertised transport must be protocol-conformant | maintained FastMCP Streamable HTTP and real-schema tests | `WithHttpTransport`, explicit `Stateless`, `MapMcp`, public client tests |
| legacy HTTP+SSE remained the default | new servers use only standard current transports | stdio or Streamable HTTP; no legacy `/sse` + `/message` | stdio or Streamable HTTP; do not touch obsolete `EnableLegacySse` |
| “ban SSE” also rejected modern streaming | terminology distinguishes transport from framing | legacy transport forbidden; `text/event-stream` within Streamable HTTP allowed | same; test endpoint shape, not MIME substring alone |
| wildcard CORS contradicted Origin checks | browser and DNS-rebinding policy is coherent | explicit Origin and minimal CORS | exact `AllowedHosts`, auth, Origin/CORS policy, loopback default |
| SDK content blocks were treated as raw JSON | protocol representation is asserted explicitly | normalize content blocks only in test adapter | inspect typed content blocks, `StructuredContent`, `OutputSchema`, and `IsError` |
| typed DTO returned `success=false` but client saw success | application failure uses protocol-native error contract | structured error/result with SDK-native error flag | `CallToolResult.IsError=true` or controlled `McpException` |
| data annotations were assumed to validate input | schema guidance does not enforce runtime policy | explicit validator before approval or I/O | explicit application validation before approval or I/O |
| broad exception handling swallowed cancellation | cancellation remains first-class | re-raise runtime cancellation | preserve `OperationCanceledException` and request abort |
| shell command was built from model text | agent input never becomes shell syntax | fixed executable, argument list, allowlist | `ProcessStartInfo.ArgumentList`, allowlist, sandbox |
| integration fixture depended on private SDK internals | compatibility code is isolated and temporary | wrapper with supported-version matrix | host/client integration, no reflection |
| assembly scanning broke trimming/AOT | registration strategy matches deployment artifact | explicit supported SDK registration | generic `WithTools<T>()`; assembly scan requires reviewed non-AOT evidence |
| `[Authorize]` attributes had no effect | declarative policy must be activated and tested | explicit middleware/dependency policy | call `AddAuthorizationFilters()` and verify filtered listing/invocation |
| rate limiting ran before authentication | quota partitions use the authenticated identity | auth context before limiter key | authentication/principal middleware before `UseRateLimiter()` |
| stdio child inherited unrelated credentials | subprocess environment is an allowlist | explicit env for child process | `InheritEnvironmentVariables=false` plus default/runtime allowlist |
| async tool silently advertised task support | protocol task support is capability policy | explicit task registry and execution contract | review `Forbidden`/`Optional`/`Required`; async return alone is not approval |
| in-memory task metadata was called durable | protocol task store and executor have explicit durability | bounded in-memory only for local; durable queue for promises | `InMemoryMcpTaskStore` only for local/test; principal-bound durable store and supervised worker |
| package allowlist read dependency identity | artifact identity comes from direct package metadata | inspect direct wheel metadata | read direct `package/metadata/id` and `version`, never arbitrary descendants |
| server metadata self-asserted trusted policy | trusted values travel outside discovered metadata | typed consumer-owned policy object | same; do not use a boolean to upgrade fields from the untrusted map |
| old standard URL was removed | stable documentation entry points are compatibility contracts | deprecation stub links to canonical docs | same language-neutral repository rule |

The map transfers the invariant, not the mechanism. Platform-specific code is correct only when runtime enforcement and tests prove equivalent behavior under that platform's lifecycle, transport, concurrency, authorization, and artifact model.
