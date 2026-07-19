---
description: Normative language-neutral architecture and production rules for MCP servers.
doc_id: reference.mcp-server-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Generate a fresh server and run its real-client suite, then run layered domain, manifest, policy, registration, lifecycle, race, transport-conformance, upstream-contract, and deployment-artifact tests for every advertised transport.
---

# MCP server standard

## Purpose

Define language-neutral invariants for servers consumed by agents. SDK profiles explain how to realize them without turning framework internals into architecture. The standard is hardened by migration simulations across read-only aggregators, device controllers, network appliances, multi-backend administrators, financial adapters, and browser-automation servers.

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
- Process, tenant, target, session, request, dependency-client, cache, lock, executor, artifact, and background-task ownership are explicit.
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

Use server-level instructions for cross-tool ordering, stable ID flow, async polling, profile limitations, and reconciliation. Instructions improve agent behavior but do not replace runtime validation or authorization.

## Multi-axis safety classification

A single risk label is insufficient. Every capability independently declares:

- side effects: none, read, write, or destructive;
- confidentiality: public, internal, personal, sensitive, credential, or a stricter domain class;
- operational impact: none, transient, persistent, outage, safety-critical, or financial;
- cost and abuse potential;
- reversibility and compensation;
- idempotency mechanism and retry conditions;
- target-binding and concurrency scope;
- artifact, task, browser-profile, or privileged-adapter ownership when applicable.

`READ`, `WRITE`, `DESTRUCTIVE`, `DANGEROUS`, and `SENSITIVE` may remain compatibility or UI projections, but policy evaluates every axis. Read-only financial data, logs, configuration, snapshots, browser profiles, and credentials are still confidential. A low-side-effect operation may still be expensive, privacy-sensitive, persistent, or capable of network abuse.

## Side effects, retries, and workflows

Write operations define idempotency, reversibility, concurrency preconditions, and conflict tokens. Never infer that every write is idempotent, retryable, reversible, or concurrent-safe from a factory name. Each positive claim has operation-specific evidence.

Automatic retry requires all of the following: an eligible error category, an unexpired deadline, a proven idempotency mechanism, no explicit veto, and preserved target identity. Create, publish, copy, payment-state, command, browser-action, OTA, restart, and update operations default to no automatic retry unless a durable idempotency key, deduplication record, or equivalent proof exists.

Multi-step changes use plan, execute, verify, and compensate phases. Per-step results preserve partial success. Operations that intentionally disconnect a target or continue after the request return an accepted or in-progress state, a verification window, and a follow-up method instead of disguising expected disconnect as a generic timeout.

Destructive and dangerous operations require narrow allowlists and explicit server-side authorization. Filesystem paths, commands, URLs, service names, network targets, content sizes, and resolved addresses are validated before I/O. Arbitrary command execution is exceptional and uses fixed executables, argument arrays, isolation, output limits, deadlines, and audit events. A read execution path cannot reach write commands.

## Transport and lifecycle

The standard transports are stdio and Streamable HTTP. Legacy HTTP+SSE is compatibility-only and must not be presented as equivalent to Streamable HTTP. A server advertises only transports that pass protocol conformance and policy-parity tests.

Stdio reserves stdout for protocol messages and sends diagnostics to stderr. Remote HTTP validates canonicalized Origin values, binds intentionally, authenticates before capability execution, and applies restrictive host and CORS policy. Stateless HTTP is preferred when server-to-client or cross-request state is unnecessary.

Startup, readiness, liveness, capability health, task health, and shutdown have separate meanings. Tool count or successful transport binding alone never means ready. Resources initialize once at their declared owner scope and close once on every owner-scope exit path. Partial startup reports unavailable capabilities and targets; it does not silently mark the entire workload healthy or redirect operations. See [Transport, lifecycle, and conformance](references/transport-lifecycle-and-conformance.md).

## Deadlines, cancellation, retries, and concurrency

- Propagate request deadlines and cancellation to every cancellable I/O operation.
- Never use unbounded external calls, request bodies, headers, executor queues, subprocess output, sessions, caches, scans, task registries, or generated exports.
- Cleanup after cancellation is bounded and does not mask cancellation.
- Rate limiters are concurrency-safe and scoped to the actual upstream quota key such as credential, tenant, target, or endpoint.
- Honor upstream retry hints within the remaining deadline and apply jittered bounded backoff.
- Conflict retry requires a refreshed precondition or re-read.
- `concurrent_safe` is an enforced runtime property, not documentation.
- Shared mutable clients use immutable per-call options, a pool, a keyed lock, or a narrow semaphore.
- Blocking work is offloaded to a bounded executor from asynchronous hosts.
- Request-scoped identifiers and principals use request context, not process-global or thread-local mutable state in asynchronous code.
- Session and task identifiers use a cryptographically secure generator with at least 128 bits of entropy and remain bound to the authenticated principal.

## Data, errors, and responses

Errors distinguish validation, authentication, authorization, not found, conflict, rate limit, timeout, cancellation, unavailable dependency, upstream failure, UI drift, ambiguous outcome, and internal failure. Preserve upstream status and retry guidance without leaking secrets or raw protected bodies. Returning `None`, `False`, or generic `API_ERROR` for every failure is not a stable error contract.

Responses preserve protocol-native content, structured content, correlation identifiers, target identity, data provenance, freshness, and partial-result state. Central boundaries sanitize logs and model-visible responses separately. Confidential output is minimized before serialization; sensitive exports define retention, destination, maximum size, and deletion policy.

Domain values use unambiguous contracts. Money uses decimal or minor units plus currency and rounding policy. Dates use ISO 8601 with timezone or explicit date-only semantics. Localized upstream formats are converted only inside the upstream adapter.

Content returned by a webpage or another AI system is marked with provenance and treated as untrusted input. Citations, hidden text, page instructions, and generated answers cannot grant tool authority or reduce risk.

## Authentication and authorization

Authenticate the calling principal and intended audience. Authorize every resolved target, resource, operation, data classification, artifact, task, and browser account, not only a tool name. Bind downstream credentials and target selection to approved caller context to prevent confused-deputy behavior.

Operator write gates, user confirmation hints, per-principal authorization, target allowlists, and execution isolation are independent controls. One cannot substitute for another. High-privilege adapters such as container sockets, arbitrary SSH, writable browser profiles, or raw device protocols should be isolated into separate capability groups or processes.

## Runtime boundaries, artifacts, and browser automation

Filesystem containment uses resolved component-aware paths, not string prefixes. Writes define symlink and time-of-check/time-of-use policy. Archives, uploads, and generated files enforce byte, type, destination, and extraction limits.

Screenshots, reports, audio, backups, firmware, and exports are governed artifacts with owner, operation ID, MIME type, size, checksum when useful, retention, and deletion behavior. A host path is not returned as a public artifact identity.

Background work is tracked by a bounded task registry or durable store. Daemon threads and untracked tasks are not operation records. Expected-disconnect and browser-generation workflows expose status, progress, verification, cancellation, final result, expiry, and cleanup.

Persistent browser profiles are credential stores. Account isolation, directory permissions, process locking, interactive-auth state, shared-context serialization, selector-drift diagnostics, sanitized screenshots, and explicit cleanup are part of the security contract. See [Runtime boundaries and artifacts](references/runtime-boundaries-and-artifacts.md).

## Multi-backend and embedded hosting

Multi-backend servers preserve configured target identity and namespace. A failed default does not become the first healthy backend. Gateways preserve source-server and manifest provenance so equal tool names cannot collide or transfer authority.

An embedded MCP server does not own the host process, global event loop, global logging, dependency container, or unrelated listeners. It receives host services explicitly, participates in host lifecycle, avoids route and port collisions, closes only owned resources, and never exits the process from a request path.

## Observability and operations

Emit structured logs, traces, duration, result category, resolved target, dependency state, policy decision, cancellation, saturation, retry, artifact and task state, and partial success. Correlate transport and domain operations with one request identifier. Track per-tool latency, errors, rate limits, queueing, lock contention, task count, executor saturation, session count, and UI-drift category.

Health reports mandatory and optional dependencies separately. Circuit breakers and graceful degradation prevent cascading failure. Audit failures are observable but follow an explicit fail-open or fail-closed policy. Full repository test suites are CI or deployment gates, not unbounded production startup checks.

## Generated project acceptance

The bundled Python generator is part of the standard, not an illustrative snippet. A clean invocation must create a deterministic, installable project containing typed immutable settings, application-owned manifests, a transport-independent domain service, one invocation kernel, official SDK registration, stdio and loopback Streamable HTTP startup, tools, resources, prompts, server instructions, structured errors, conservative write controls, CI, packaging, security guidance, and tests.

The generated project must compile and pass its own tests through a real MCP client session using the supported stable SDK lane. Its tests prove tool listing with real schemas, representative invocation, complete manifest coverage, fail-closed writes, optimistic conflict handling, no private SDK fields, bounded HTTP body size, action pinning, and deterministic generation. A generator that emits text which is not installed and executed does not satisfy this standard.

Generation is atomic and refuses an existing target. Production adoption still requires replacing sample domain code, reviewing every manifest, adding real authentication and resource authorization, upstream contract tests, deployment-artifact smoke tests, and all applicable runtime-boundary scenarios.

## Verification layers

1. domain unit tests;
2. schema, serialization, domain-value, and manifest-consistency tests;
3. policy, authorization, target-binding, filesystem, artifact, and sanitization tests;
4. public registration, active-profile, resources, prompts, instructions, and discovery tests;
5. lifecycle, configuration-order, task, browser-profile, cancellation, executor, and concurrency tests;
6. transport conformance and invocation-kernel parity tests;
7. representative real-client workflows;
8. deployment-artifact smoke tests;
9. upstream contract tests with controlled fakes, recordings, canaries, or test containers;
10. migration simulations covering analogous server archetypes;
11. fresh-project generation followed by installation, compilation, and its own real-client suite.

No layer substitutes for another. See [Testing strategy](references/testing-strategy.md) and [Python migration simulation](references/python-migration-simulation.md).

## Implementation profiles

- [Capability manifests and versioning](references/capability-manifests-and-versioning.md)
- [Transport, lifecycle, and conformance](references/transport-lifecycle-and-conformance.md)
- [Runtime boundaries and artifacts](references/runtime-boundaries-and-artifacts.md)
- [Python and FastMCP](references/python-fastmcp.md)
- [Python migration simulation](references/python-migration-simulation.md)
- [.NET MCP](references/dotnet-mcp.md)
- [Cross-language invariant map](references/cross-language-invariant-map.md)
- [Security and operations](references/security-and-operations.md)
- [Problem-solution matrix](references/problem-solution-matrix.md)

## Verification

Generate a fresh Python project and execute its complete suite first. Then run all applicable layers once at their proper abstraction level; repeat transport conformance, invocation-kernel policy parity, representative client workflows, and artifact smoke tests for every advertised transport. Review public contracts, target identity, lifecycle ownership, trust boundaries, data classification, runtime enforcement, artifacts, tasks, profile isolation, and embedded-host ownership independently from framework-specific code.
