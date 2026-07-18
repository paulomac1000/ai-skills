---
description: Normative language-neutral architecture and production rules for MCP servers.
doc_id: reference.mcp-server-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run layered domain, manifest, policy, registration, lifecycle, and race tests; repeat transport-conformance, representative real-client, and deployment-artifact tests for every advertised transport.
---

# MCP server standard

## Purpose

Define language-neutral invariants for servers consumed by agents. SDK profiles explain how to realize them without turning framework internals into architecture. The standard is hardened by migration simulations across read-only aggregators, device controllers, network appliances, multi-backend administrators, and financial adapters.

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
- One composition root owns validated configuration, dependencies, lifecycle, registration, middleware, and transport.
- One invocation kernel performs target resolution, authentication, authorization, operator policy, validation, deadlines, concurrency control, execution, error mapping, sanitization, and telemetry.
- Every MCP transport and convenience adapter delegates to that kernel; no adapter calls a raw tool function or private wrapper directly.
- Process, session, request, dependency-client, cache, lock, executor, and background-task ownership are explicit.
- Optional integrations fail independently; mandatory dependency failure prevents readiness.
- SDK compatibility logic is isolated behind one adapter and never spread through domain code.

## Configuration and identity

Load and validate configuration before importing modules that read environment variables or create clients. Freeze one typed settings snapshot for the process. Runtime mutation requires an explicit reload transaction and revalidation.

Secrets come from an intentional source and never from command-line arguments, example JSON, logs, capability discovery, or model-visible errors. A public-bind acknowledgement is not authentication, authorization, TLS, or network isolation.

Resolve the target resource before authorization and execution. Bind every mutation to a stable target identity such as account ID, device identity, host fingerprint, tenant, or resource version. Never silently replace an unavailable requested or default target with another target. Revalidate mutable address-to-identity mappings immediately before side effects.

## Public component contracts

Every public component has a stable name, bounded input, structured output, documented empty-success behavior, version policy, and machine-readable failure shape. Tool descriptions and annotations improve discovery but are not authorization.

At L2 and above, every public tool has a complete governed manifest. Missing or malformed metadata fails registration or CI; it never defaults to `READ`. The manifest, schema, description, runtime policy, and active profile must describe the same operation. See [Capability manifests and versioning](references/capability-manifests-and-versioning.md).

Distinguish the supported catalog from the active catalog. Profiles, unavailable dependencies, operator policy, and deployment topology may reduce the active set, but discovery must explain why a supported capability is inactive. Large catalogs provide bounded categories, search, minimal listings, or on-demand schemas.

List and search tools return identifiers accepted by detail or mutation tools. Large results support bounded summaries, fields, pagination, or progressive discovery. Pagination defines stable ordering, continuation semantics, and a terminating condition; a non-empty page alone never proves that another page exists.

## Multi-axis safety classification

A single risk label is insufficient. Every capability independently declares:

- side effects: none, read, write, or destructive;
- confidentiality: public, internal, personal, sensitive, credential, or a stricter domain class;
- operational impact: none, transient, persistent, outage, safety-critical, or financial;
- cost and abuse potential;
- reversibility and compensation;
- idempotency mechanism and retry conditions;
- target-binding and concurrency scope.

`READ`, `WRITE`, `DESTRUCTIVE`, `DANGEROUS`, and `SENSITIVE` may remain compatibility or UI projections, but policy evaluates every axis. Read-only financial data, logs, configuration, snapshots, and credentials are still confidential. A low-side-effect operation may still be expensive, privacy-sensitive, or capable of network abuse.

## Side effects, retries, and workflows

Write operations define idempotency, reversibility, concurrency preconditions, and conflict tokens. Never infer that every write is idempotent, retryable, reversible, or concurrent-safe from a factory name. Each positive claim has operation-specific evidence.

Automatic retry requires all of the following: an eligible error category, an unexpired deadline, a proven idempotency mechanism, no explicit veto, and preserved target identity. Create, publish, copy, payment-state, command, OTA, restart, and update operations default to no automatic retry unless a durable idempotency key, deduplication record, or equivalent proof exists.

Multi-step changes use plan, execute, verify, and compensate phases. Per-step results preserve partial success. Operations that intentionally disconnect a target return an accepted or in-progress state, a verification window, and a follow-up method instead of disguising expected disconnect as a generic timeout.

Destructive and dangerous operations require narrow allowlists and explicit server-side authorization. Filesystem paths, commands, URLs, service names, network targets, content sizes, and resolved addresses are validated before I/O. Arbitrary command execution is exceptional and uses fixed executables, argument arrays, isolation, output limits, deadlines, and audit events. A read execution path cannot reach write commands.

## Transport and lifecycle

The standard transports are stdio and Streamable HTTP. Legacy HTTP+SSE is compatibility-only and must not be presented as equivalent to Streamable HTTP. A server advertises only transports that pass protocol conformance and policy-parity tests.

Stdio reserves stdout for protocol messages and sends diagnostics to stderr. Remote HTTP validates canonicalized Origin values, binds intentionally, authenticates before capability execution, and applies restrictive host and CORS policy. Stateless HTTP is preferred when server-to-client or cross-request state is unnecessary.

Startup, readiness, liveness, capability health, and shutdown have separate meanings. Tool count or successful transport binding alone never means ready. Resources initialize once at their declared owner scope and close once on every exit path. Partial startup reports unavailable capabilities and targets; it does not silently mark the entire workload healthy or redirect operations. See [Transport, lifecycle, and conformance](references/transport-lifecycle-and-conformance.md).

## Deadlines, cancellation, retries, and concurrency

- Propagate request deadlines and cancellation to every cancellable I/O operation.
- Never use unbounded external calls, executor queues, subprocess output, sessions, caches, scans, or generated exports.
- Cleanup after cancellation is bounded and does not mask cancellation.
- Rate limiters are concurrency-safe and scoped to the actual upstream quota key such as credential, tenant, target, or endpoint.
- Honor upstream retry hints within the remaining deadline and apply jittered bounded backoff.
- Conflict retry requires a refreshed precondition or re-read.
- `concurrent_safe` is an enforced runtime property, not documentation.
- Shared mutable clients use immutable per-call options, a pool, a keyed lock, or a narrow semaphore.
- Blocking work is offloaded to a bounded executor from asynchronous hosts.
- Request-scoped identifiers and principals use request context, not process-global or thread-local mutable state in asynchronous code.

## Data, errors, and responses

Errors distinguish validation, authentication, authorization, not found, conflict, rate limit, timeout, cancellation, unavailable dependency, upstream failure, and internal failure. Preserve upstream status and retry guidance without leaking secrets or raw protected bodies. Returning `None`, `False`, or generic `API_ERROR` for every failure is not a stable error contract.

Responses preserve protocol-native content, structured content, correlation identifiers, target identity, data provenance, freshness, and partial-result state. Central boundaries sanitize logs and model-visible responses separately. Confidential output is minimized before serialization; sensitive exports define retention, destination, maximum size, and deletion policy.

Domain values use unambiguous contracts. Money uses decimal or minor units plus currency and rounding policy. Dates use ISO 8601 with timezone or explicit date-only semantics. Localized upstream formats are converted only inside the upstream adapter.

## Authentication and authorization

Authenticate the calling principal and intended audience. Authorize every resolved target, resource, operation, and data classification, not only a tool name. Bind downstream credentials and target selection to approved caller context to prevent confused-deputy behavior.

Operator write gates, user confirmation hints, per-principal authorization, target allowlists, and execution isolation are independent controls. One cannot substitute for another. High-privilege adapters such as container sockets, arbitrary SSH, browser profiles, or raw device protocols should be isolated into separate capability groups or processes.

## Long-running work and exports

Scans, updates, media generation, context exports, hardware tests, and other long operations declare whether they are synchronous or task-based. Task-based operations expose bounded status, progress, cancellation, final result, expiry, and cleanup. Restart recovery does not rely solely on in-memory task state when durable continuation is promised.

Generated context and bulk exports apply least-data selection, output limits, atomic writes, destination allowlists, secure permissions, provenance, retention, and cancellation. They are not treated as ordinary cheap read tools.

## Observability and operations

Emit structured logs, traces, duration, result category, resolved target, dependency state, policy decision, cancellation, saturation, retry, and partial success. Correlate transport and domain operations with one request identifier. Track per-tool latency, errors, rate limits, queueing, lock contention, task count, and executor saturation.

Health reports mandatory and optional dependencies separately. Circuit breakers and graceful degradation prevent cascading failure. Audit failures are observable but follow an explicit fail-open or fail-closed policy. Full repository test suites are CI or deployment gates, not unbounded production startup checks.

## Verification layers

1. domain unit tests;
2. schema, serialization, domain-value, and manifest-consistency tests;
3. policy, authorization, target-binding, and sanitization tests;
4. public registration, active-profile, and discovery tests;
5. lifecycle, configuration-order, cancellation, executor, and concurrency tests;
6. transport conformance and invocation-kernel parity tests;
7. representative real-client workflows;
8. deployment-artifact smoke tests;
9. upstream contract tests with controlled fakes, recordings, or test containers;
10. migration simulations covering analogous server archetypes.

No layer substitutes for another. See [Testing strategy](references/testing-strategy.md) and [Python migration simulation](references/python-migration-simulation.md).

## Implementation profiles

- [Capability manifests and versioning](references/capability-manifests-and-versioning.md)
- [Transport, lifecycle, and conformance](references/transport-lifecycle-and-conformance.md)
- [Python and FastMCP](references/python-fastmcp.md)
- [Python migration simulation](references/python-migration-simulation.md)
- [.NET MCP](references/dotnet-mcp.md)
- [Cross-language invariant map](references/cross-language-invariant-map.md)
- [Security and operations](references/security-and-operations.md)
- [Problem-solution matrix](references/problem-solution-matrix.md)

## Verification

Run all applicable layers once at their proper abstraction level; repeat transport conformance, invocation-kernel policy parity, representative client workflows, and artifact smoke tests for every advertised transport. Review public contracts, target identity, lifecycle ownership, trust boundaries, data classification, and runtime enforcement independently from framework-specific code.