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
| private tool storage changed between SDK releases | public registration is the contract | public provider/client API; one tested compatibility adapter | public client enumeration; explicit or assembly registration |
| unclassified tools were auto-marked read-only | missing safety metadata fails closed | governed manifest registry; startup and CI coverage gate | typed manifest registry plus options/startup validation |
| risk prefix and manifest drifted | one source owns capability semantics | generate projection from manifest | generate annotations or descriptors from typed manifest |
| lifespan ran at a different scope than expected | every resource has one declared owner scope | application lifespan separate from connection callback | Generic Host and DI lifetime |
| partial backend startup was hidden by healthy status | readiness and capability health are distinct | failed-target registry and readiness gate | health checks with per-capability state |
| all backends failed but transport started | no useful workload means not ready | fail startup when mandatory client set is empty | startup validation prevents host readiness |
| shared SSH client timeout was mutated per call | shared clients do not carry mutable request options | immutable call options or keyed client/lock | request message or typed client; no singleton option mutation |
| manifest said non-concurrent-safe but calls overlapped | declared safety is enforced | keyed `asyncio.Lock`, semaphore, queue, or isolated client | keyed lock, `SemaphoreSlim`, `Channel`, actor, or transaction |
| integration test created a new event loop per call | async resources remain on their owning scheduler | shared loop for persistent async clients | one host and async test lifetime; no sync-over-async |
| sync tool ran directly in an async HTTP route | blocking work never stalls the event loop | true async client or bounded `to_thread` | true async API; no `.Result` or `.Wait()` |
| request ID leaked across concurrent tasks | request context is scoped and concurrency-safe | `contextvars` with reset | `Activity`, scope, explicit context; limited `AsyncLocal` |
| logging was sanitized but responses leaked secrets | every egress boundary is sanitized | formatter plus recursive response sanitizer | logging redaction plus result filter/DTO sanitizer |
| operator write flag was confused with user consent | enablement, authorization, and confirmation are independent | pre-I/O write gate plus auth policy and manifest hint | options gate plus authorization filter and manifest hint |
| custom HTTP endpoint returned dummy schemas | advertised transport must be protocol-conformant | maintained FastMCP HTTP transport and real schema tests | `WithHttpTransport` and `MapMcp` plus public client tests |
| wildcard CORS contradicted Origin checks | browser and DNS-rebinding policy is coherent | explicit Origin and minimal CORS | AllowedHosts, endpoint auth, Origin/CORS policy |
| SDK content blocks were treated as raw JSON | protocol representation is asserted explicitly | normalize content blocks only in test adapter | test typed content blocks and serialized DTOs |
| broad exception handling swallowed cancellation | cancellation remains a first-class result | re-raise runtime cancellation | preserve `OperationCanceledException` |
| shell command was built from model text | agent input never becomes shell syntax | fixed executable, argument list, allowlist | `ProcessStartInfo.ArgumentList`, allowlist, sandbox |
| integration fixture depended on private SDK internals | compatibility code is isolated and temporary | wrapper with supported-version matrix | host/client integration, no reflection |
| old standard URL was removed | stable documentation entry points are compatibility contracts | deprecation stub links to canonical docs | same language-neutral repository rule |

The map transfers the invariant, not the mechanism. Platform-specific code is correct only when runtime enforcement and tests prove equivalent behavior under that platform's lifecycle, transport, and concurrency model.
