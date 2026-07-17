---
description: Mapping from Python and FastMCP incidents to language-neutral invariants and correct .NET controls.
doc_id: reference.mcp-cross-language-invariant-map
type: reference
status: active
rigor: informative
owners: [repository-maintainers]
---

# MCP cross-language invariant map

| Python or FastMCP incident | Language-neutral invariant | .NET realization |
| --- | --- | --- |
| private `_tools` locations changed | Public registration is the contract | Register with supported `WithTools<T>` APIs and verify through a client |
| global request ID leaked across tasks | Request state is scoped and concurrency-safe | `Activity`, `ILogger.BeginScope`, scoped service; `AsyncLocal` only when unavoidable |
| lifespan context unavailable in tests | Resource lifecycle belongs to the host | Generic Host lifecycle and DI scopes |
| decorator mock returned `None` | Test doubles preserve public composition semantics | Replace services through DI rather than mocking attributes or reflection |
| context fetched outside a request | Transport context does not leak into domain code | Inject supported request context only at tool boundary |
| `ContentBlock` mistaken for JSON | Assert protocol representation explicitly | Test typed MCP result and serialized wire shape separately |
| blocking I/O inside async tool | Async boundaries remain asynchronous | true async APIs and `CancellationToken`; no `.Result` or `.Wait()` |
| broad exception handler swallowed cancellation | Cancellation remains a first-class outcome | rethrow `OperationCanceledException`; central exception mapping |
| shell command built from model text | Agent input never becomes shell syntax | fixed executable, argument list, allowlist, timeout, output bound |
| REST bridge mocked at function level | Transport behavior needs real integration evidence | ASP.NET Core test host and public MCP client |
| fixtures hidden in `__init__.py` | Test discovery is explicit | normal test project fixtures and collection attributes |
| one lock serialized the entire service | Synchronization matches state ownership | narrow `SemaphoreSlim`, immutable state, or concurrent collections |

The map transfers the lesson, not the Python mechanism. A platform-specific solution is correct only when it enforces the same invariant under that platform's lifecycle and concurrency model.
