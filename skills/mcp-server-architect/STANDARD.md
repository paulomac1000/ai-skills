---
description: Normative language-neutral architecture and production rules for MCP servers.
doc_id: reference.mcp-server-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run layered domain, schema, policy, registration, and transport tests; exercise representative end-to-end workflows with a real MCP client or inspector.
---

# MCP server standard

## Purpose

Define language-neutral invariants for servers consumed by agents. SDK profiles explain how to realize them without turning framework internals into architecture.

## Maturity levels

| Level | Use case | Required evidence |
| --- | --- | --- |
| L1 personal | local or experimental server | domain unit tests, schema validation, controlled errors |
| L2 team | shared internal server | L1 plus registration, integration, auth boundary, CI, health |
| L3 production | always-on critical service | L2 plus real-client smoke, observability, SLOs, cancellation, deployment artifact tests |
| L4 hardened | public, multi-tenant, or dangerous capabilities | L3 plus per-tool authorization, isolation, abuse controls, security tests, audit and recovery drills |

## Core architecture

- Domain operations do not depend on MCP transport types.
- Registration adapts typed domain operations to tool schemas and response contracts.
- Transport, hosting, authentication, policy, telemetry, and lifecycle are composed around registration.
- Tool identity, schema, and risk metadata are stable enough for consumers to reason about compatibility.
- Optional integrations fail independently and do not prevent unrelated tools from loading.

## Tool contracts

Every tool has a clear outcome, bounded inputs, structured output, documented empty-success behavior, stable identifiers, and a machine-readable error shape. List or search tools return identifiers accepted by detail or mutation tools. Large results support pagination or bounded summaries. Batch tools preserve authorization, per-item results, and verification boundaries.

Tool descriptions are not authorization. Risk and side-effect metadata are advisory to consumers and must not replace server-side policy.

## Side effects and safety

Classify operations as read, write, destructive, dangerous, or sensitive. Write operations define idempotency and concurrency preconditions. Destructive and dangerous operations require explicit server-side authorization and narrow allowlists. Filesystem paths, commands, URLs, service names, and content size are validated before I/O.

Arbitrary command execution is not a general-purpose MCP convenience. When unavoidable, use fixed executables, argument arrays, allowlists, sandboxing, output limits, deadlines, and audit events.

## Transport and lifecycle

Support only transports the deployment can operate safely. Stdio reserves stdout for protocol data and sends diagnostics to stderr. HTTP binds intentionally, authenticates before tool execution, and uses TLS at the appropriate boundary. Session state is avoided unless the capability requires it; stateless HTTP is the default for horizontally scalable request-independent servers.

Startup, readiness, liveness, and shutdown have separate semantics. A process can be alive but not ready. Shutdown stops accepting work, cancels or drains in-flight operations within a bound, and releases resources.

## Deadlines, cancellation, retries, and concurrency

- Propagate the request deadline and cancellation signal to every cancellable I/O operation.
- Never use unbounded external calls.
- Cleanup runs after cancellation and does not mask the cancellation outcome.
- Retry only idempotent operations with explicit positive policy and bounded backoff.
- Conflict retries require a refreshed precondition or re-read.
- Shared state uses an explicit synchronization and ownership model.
- Request-scoped identifiers are not global mutable variables.

## Error contract

Errors distinguish validation, authentication, authorization, not found, conflict, rate limit, timeout, cancellation, unavailable dependency, upstream failure, and internal failure. Responses preserve protocol-native error details and correlation identifiers without leaking secrets. Retry guidance is explicit and cannot override server-side safety.

## Authentication and authorization

Authenticate the calling principal and intended audience. Authorize each capability using resolved resource scope, not only the tool name. Prevent confused-deputy behavior by binding downstream credentials and resource access to the caller's approved context. Keep secrets out of tool descriptions, logs, and model-visible responses.

## Consumer ergonomics

Provide bounded discovery, capability summaries, stable names, concise default output, optional detail levels, pagination metadata, batch operations where policy remains intact, and explicit negative capability. Empty results are successful when the query legitimately matched nothing.

## Observability and operations

Emit structured logs, traces, duration, result category, dependency state, and sanitized audit events. Correlate transport and domain operations. Track per-tool latency, errors, cancellations, rate limits, and saturation. Define graceful degradation and circuit-breaker behavior for failing dependencies.

## Verification layers

1. domain unit tests;
2. schema and serialization tests;
3. policy and authorization tests;
4. public registration tests;
5. transport integration tests;
6. representative real-client or inspector workflows;
7. deployment-artifact smoke tests;
8. upstream contract tests with controlled fakes or test containers.

No one layer substitutes for the others. See [Testing strategy](references/testing-strategy.md).

## Implementation profiles

- [Python and FastMCP](references/python-fastmcp.md)
- [.NET MCP](references/dotnet-mcp.md)
- [Cross-language invariant map](references/cross-language-invariant-map.md)
- [Security and operations](references/security-and-operations.md)
- [Problem-solution matrix](references/problem-solution-matrix.md)

## Verification

Run all applicable layers, including a representative client against the built server artifact. Review the public contract and trust boundaries independently from framework-specific code.
