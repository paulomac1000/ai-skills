---
description: Normative language-neutral architecture and production rules for MCP servers.
doc_id: reference.mcp-server-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run domain, manifest, policy, registration, lifecycle, transport-conformance, race, real-client, and deployment-artifact tests for every advertised transport.
---

# MCP server standard

## Purpose

Define language-neutral invariants for servers consumed by agents. SDK profiles explain how to realize them without turning framework internals into architecture.

## Maturity levels

| Level | Use case | Required evidence |
| --- | --- | --- |
| L1 personal | local or experimental server | domain unit tests, schema validation, controlled errors |
| L2 team | shared internal server | L1 plus complete manifests, registration, integration, auth boundary, CI, health |
| L3 production | always-on critical service | L2 plus real-client smoke, lifecycle and race tests, observability, SLOs, cancellation, artifact tests |
| L4 hardened | public, multi-tenant, sensitive, or dangerous capabilities | L3 plus per-resource authorization, isolation, abuse controls, security tests, audit and recovery drills |

## Core architecture

- Domain operations do not depend on MCP transport or SDK types.
- Registration adapts typed operations to public tools, resources, prompts, schemas, and response contracts.
- A composition root owns configuration, dependencies, lifecycle, registration, middleware, and transport.
- Process, session, request, dependency-client, cache, lock, and background-task ownership are explicit.
- Optional integrations fail independently; mandatory dependency failure prevents readiness.
- SDK compatibility logic is isolated behind one adapter and never spread through domain code.

## Public component contracts

Every public component has a stable name, bounded input, structured output, documented empty-success behavior, version policy, and machine-readable failure shape. Tool descriptions and annotations improve discovery but are not authorization.

At L2 and above, every public tool has a complete governed manifest. Missing or malformed metadata fails registration or CI; it never defaults to `READ`. The manifest, schema, description, and runtime policy must describe the same operation. See [Capability manifests and versioning](references/capability-manifests-and-versioning.md).

List and search tools return identifiers accepted by detail or mutation tools. Large results support bounded summaries, fields, pagination, or progressive discovery. Batch tools preserve authorization, per-item results, and verification boundaries.

## Side effects and safety

Classify operations as `READ`, `WRITE`, `DESTRUCTIVE`, `DANGEROUS`, or `SENSITIVE`. Server authorization and operator enablement are separate from consumer confirmation metadata.

Write operations define idempotency, reversibility, concurrency preconditions, and conflict tokens. Destructive and dangerous operations require narrow allowlists and explicit server-side authorization. Filesystem paths, commands, URLs, service names, network targets, and content sizes are validated before I/O.

Arbitrary command execution is exceptional. Use fixed executables, argument arrays, allowlists, isolation, output limits, deadlines, and audit events. A read execution path cannot reach write commands.

## Transport and lifecycle

The standard transports are stdio and Streamable HTTP. Legacy HTTP+SSE is compatibility-only and must not be presented as equivalent to Streamable HTTP. A server advertises only transports that pass protocol conformance and policy-parity tests.

Stdio reserves stdout for protocol messages and sends diagnostics to stderr. Remote HTTP validates `Origin`, binds intentionally, authenticates before capability execution, and applies restrictive host and CORS policy. Stateless HTTP is preferred when server-to-client or cross-request state is unnecessary.

Startup, readiness, liveness, capability health, and shutdown have separate meanings. Resources initialize once at their declared owner scope and close once on every exit path. Partial startup reports unavailable capabilities; it does not silently mark the entire workload ready. See [Transport, lifecycle, and conformance](references/transport-lifecycle-and-conformance.md).

## Deadlines, cancellation, retries, and concurrency

- Propagate request deadlines and cancellation to every cancellable I/O operation.
- Never use unbounded external calls, queues, subprocess output, sessions, or caches.
- Cleanup after cancellation is bounded and does not mask cancellation.
- Retry only explicitly retryable, idempotent operations with bounded backoff.
- Conflict retry requires a refreshed precondition or re-read.
- `concurrent_safe` is an enforced runtime property, not documentation.
- Shared mutable clients use immutable per-call options, a pool, a keyed lock, or a narrow semaphore.
- Blocking work is offloaded from asynchronous event loops.
- Request-scoped identifiers and principals are not process-global mutable values.

## Error and response contract

Errors distinguish validation, authentication, authorization, not found, conflict, rate limit, timeout, cancellation, unavailable dependency, upstream failure, and internal failure. Stable codes are machine-readable; messages and suggestions remain bounded and sanitized.

Responses preserve protocol-native content and correlation identifiers. A central boundary sanitizes secrets from model-visible responses as well as logs. Unknown response metadata remains forward-compatible.

## Authentication and authorization

Authenticate the calling principal and intended audience. Authorize every resolved resource and operation, not only a tool name. Bind downstream credentials and target selection to approved caller context to prevent confused-deputy behavior.

Operator write gates, user confirmation hints, and per-principal authorization are independent controls. One cannot substitute for another.

## Discovery, manifests, and compatibility

Expose bounded capability discovery over the same MCP transport used by the agent. For large catalogs, provide categories, search, minimal listings, or on-demand schemas instead of dumping every full schema.

Preserve stable documentation and tool entry points. Breaking schema changes require a major version or a versioned tool name, migration guidance, and a deprecation interval. Public response fields are additive within a major version.

## Observability and operations

Emit structured logs, traces, duration, result category, dependency state, policy decision, cancellation, and saturation. Correlate transport and domain operations with one request identifier. Track per-tool latency, errors, rate limits, queueing, and lock contention.

Health reports mandatory and optional dependencies separately. Circuit breakers and graceful degradation prevent cascading failure. Audit failures are observable but must follow the declared fail-open or fail-closed policy.

## Verification layers

1. domain unit tests;
2. schema, serialization, and manifest-consistency tests;
3. policy, authorization, and sanitization tests;
4. public registration and discovery tests;
5. lifecycle, cancellation, and concurrency/race tests;
6. transport conformance and transport-parity tests;
7. representative real-client or inspector workflows;
8. deployment-artifact smoke tests;
9. upstream contract tests with controlled fakes, recordings, or test containers.

No layer substitutes for another. See [Testing strategy](references/testing-strategy.md).

## Implementation profiles

- [Capability manifests and versioning](references/capability-manifests-and-versioning.md)
- [Transport, lifecycle, and conformance](references/transport-lifecycle-and-conformance.md)
- [Python and FastMCP](references/python-fastmcp.md)
- [.NET MCP](references/dotnet-mcp.md)
- [Cross-language invariant map](references/cross-language-invariant-map.md)
- [Security and operations](references/security-and-operations.md)
- [Problem-solution matrix](references/problem-solution-matrix.md)

## Verification

Run all applicable layers against every advertised transport and the built artifact. Review public contracts, lifecycle ownership, trust boundaries, and runtime enforcement independently from framework-specific code.
