---
description: Executable migration simulation for .NET MCP servers derived from four materially different production archetypes.
doc_id: reference.dotnet-mcp-migration-simulation
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Generate the .NET baseline, build and invoke it through the official client, then apply every applicable archetype scenario and prove each failure is caught at the intended test layer.
---

# .NET MCP migration simulation

## Purpose

Transfer reusable experience into .NET without copying Python mechanics or retaining project-specific names. Each archetype starts from the generated .NET baseline and replaces only application-owned ports and adapters. The simulation asks whether Generic Host, ASP.NET Core, the official C# SDK, DI, cancellation, identity, packaging, and concurrency controls preserve the language-neutral standard.

## Archetype A: read-only aggregator with exports

### Read-only aggregator shape

A large catalog reads configuration, diagnostics, state, and bounded filesystem data. Some operations generate snapshots or exports that finish after the request.

### Read-only aggregator design

- `ClaimsPrincipal` and target identity flow into one invocation kernel;
- read-only does not suppress confidentiality, purpose, or authorization;
- capability discovery is zero-I/O and filtered by active dependencies and caller scopes;
- export generation uses a bounded principal-bound task registry and opaque principal-bound artifact handle, never a daemon thread or host path;
- process-scoped clients survive an individual protocol-session disconnect;
- liveness stays healthy while readiness reflects mandatory dependency failure.

### Read-only aggregator failure simulations

- remove one manifest while keeping the attributed tool;
- return a local path instead of an artifact handle;
- cancel after export admission and verify partial output is invisible;
- restart while a non-durable task is running and verify the server does not claim recovery;
- disconnect one client and prove shared process clients remain usable;
- request a confidential field outside the caller scope.

## Archetype B: physical-device controller

### Physical-device controller shape

The server discovers devices and can issue switch, gate, firmware, media, or raw-protocol operations. Address assignment can change independently of device identity.

### Physical-device controller design

- stable device identity is resolved before authorization and revalidated before a physical effect;
- ordinary write, physical effect, firmware update, and outage are separate manifest axes;
- every write defaults to non-retryable and non-idempotent unless the operation proves a durable key or natural idempotency;
- non-concurrent-safe operations serialize by device or controller through a keyed lock, `SemaphoreSlim`, `Channel`, or actor;
- firmware and media inputs have byte, type, checksum, destination, and retention limits;
- expected disconnect returns an accepted state and verification deadline instead of a generic retryable timeout.

### Physical-device controller failure simulations

- change the address-to-device mapping between discovery and mutation;
- send the same command after an ambiguous timeout and prove no blind replay occurs;
- overlap two firmware operations for one device and one operation for another;
- let the operator write flag be on while the caller lacks resource authorization;
- present a model-created approval token and verify rejection;
- simulate a device restart that temporarily drops the transport but later satisfies the postcondition.

## Archetype C: financial API adapter

### Financial API adapter shape

The server reads accounts and transactions and may create, transition, or delete financial records.

### Financial API adapter design

- money uses `decimal` or minor units plus currency and explicit rounding;
- dates have ISO 8601 or explicit date-only semantics;
- every financial read remains confidential even when side-effect free;
- API credentials never appear in URLs, logs, exceptions, capability discovery, or model-visible errors;
- create uses a caller- or server-owned idempotency key only when the upstream contract proves deduplication;
- deletion approval is bound to principal, account, target, and exact record;
- pagination terminates on explicit continuation state, including empty and full-final pages.

### Financial API adapter failure simulations

- dependency metadata claims `idempotent=true` while the trusted contract does not;
- a timeout occurs after the upstream accepted a create;
- a decimal value crosses a midpoint rounding boundary;
- a deleted record belongs to another account or principal;
- a query secret appears in a captured `HttpRequestMessage`, log, or trace;
- a non-empty final page has no continuation token.

## Archetype D: multi-backend SSH administrator

### Multi-backend SSH administrator shape

The server manages several named backends or hosts and exposes bounded diagnostics, configuration, and restart operations.

### Multi-backend SSH administrator design

- target namespaces remain explicit and equal tool names cannot transfer authority;
- an unavailable requested or configured default target never becomes the first healthy backend;
- SSH identity is a pinned host-key fingerprint or equivalent stable proof, not an address;
- diagnostics select from fixed executable and argument templates; model text is never shell syntax;
- per-call timeout and target are immutable request values, not mutations of a singleton client;
- restart is an outage operation with expected-disconnect and postcondition verification;
- process cleanup is owned by Generic Host and terminates process groups within a bound.

### Multi-backend SSH administrator failure simulations

- fail the configured default while another target is healthy;
- return the same hostname with a changed host-key fingerprint;
- inject shell metacharacters into a diagnostic argument;
- overlap a non-concurrent-safe restart with a read against the same and a different target;
- cancel while waiting for a keyed lock;
- terminate the host during a child process and verify bounded cleanup.

## .NET-specific ambiguity resolutions

- No silent target fallback is allowed. A failed requested or configured default target remains failed until an operator or caller selects a replacement explicitly.
- An MCP task store is not an executor. Durable work needs a supervised worker, bounded admission, principal-bound authorization, recovery, and shutdown behavior in addition to protocol task state.

### `ClaimsPrincipal` versus `IHttpContextAccessor`

Use `ClaimsPrincipal` injection for transport context and keep domain services transport independent. `IHttpContextAccessor` is reserved for narrow HTTP-only infrastructure. Stdio identity comes from trusted process configuration or a message filter, never a model parameter.

### Attributes versus runtime enforcement

`[McpServerTool]`, descriptions, and data annotations create discovery metadata. They do not enforce authorization, validation, idempotency, retry, or concurrency. `AddAuthorizationFilters()` activates declarative authorization, while the invocation kernel validates application rules before I/O.

### Async return type versus protocol Task

An async method is not automatically a durable operation. If task support is configured, review each tool as forbidden, optional, or required. `InMemoryMcpTaskStore` is not fault tolerant; durable work needs a principal-bound store and supervised executor or queue.

### Stateless versus stateful HTTP

Set `Stateless` explicitly. Use stateless for ordinary API, database, and computation tools. Choose stateful only for a proven sampling, elicitation, roots, subscription, notification, legacy-client, or per-client isolation requirement, then test session quotas, affinity, deletion, resumption, and shutdown.

### SSE terminology

The deprecated legacy HTTP+SSE transport uses separate SSE and message endpoints and is forbidden in new servers. Modern Streamable HTTP can use `text/event-stream` framing. Do not set obsolete `EnableLegacySse` merely to express that the legacy path is disabled.

### Package identity

NuGet release validation reads only direct `package/metadata/id` and `package/metadata/version`. A dependency entry cannot become package identity even when it appears first in document order.

The official C# MCP client is the source of truth for initialization, tool schemas, structured results, protocol errors, cancellation, and shutdown in this simulation.

## Migration acceptance checklist

- [ ] Domain projects have no MCP package reference.
- [ ] Public tools delegate to one invocation kernel.
- [ ] Generic registration is used; advertised AOT artifacts pass publish smoke.
- [ ] Every public tool has a complete typed manifest and tested annotation projection.
- [ ] Stdio stdout is protocol-only and child environment inheritance is allowlisted.
- [ ] Streamable HTTP sets stateless/stateful explicitly and exposes no legacy endpoints.
- [ ] Authentication precedes principal-partitioned rate limiting.
- [ ] Authorization-filter activation and caller-filtered listing are tested.
- [ ] `ClaimsPrincipal`, scopes, target identity, approval, tasks, and artifacts are principal-bound.
- [ ] Runtime validation happens before approval consumption and I/O.
- [ ] Structured output, output schema, and protocol-native errors are observed through the public client.
- [ ] Writes, retries, and concurrency use conservative per-operation evidence.
- [ ] Long work has bounded admission, progress, cancellation, expiry, recovery claims, and shutdown.
- [ ] Liveness, readiness, capability health, and task health have different predicates.
- [ ] Cancellation reaches `HttpClient`, EF Core, streams, locks, channels, processes, and delays.
- [ ] No `.Result`, `.Wait()`, mutable singleton timeout, reflection into private SDK state, or untracked `Task.Run` exists.
- [ ] The stable SDK lane and non-publishing candidate lane are separately visible.
- [ ] The official client verifies initialization, schemas, representative invocation, failure, cancellation, and closure.
- [ ] The exact published or container artifact passes the same representative workflow.
