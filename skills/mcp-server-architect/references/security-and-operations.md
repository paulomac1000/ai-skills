---
description: Security, health, resilience, observability, and deployment controls for production MCP servers.
doc_id: reference.mcp-security-and-operations
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Run authorization, sanitization, Origin, rate-limit, concurrency, dependency-failure, audit-identity, healthcheck-negative-path, graceful-shutdown, and deployment-artifact exercises.
---

# MCP security and operations

## Trust boundaries

Identify caller, server, transport, reverse proxy, downstream dependency, model-visible data, secrets, filesystem, subprocess, and network boundaries. Authenticate the caller and intended audience. Authorize the resolved resource for every invocation. Tool annotations and descriptions do not grant access.

## Independent safety controls

Treat these as separate controls:

- operator enablement decides whether a class of mutation exists at runtime;
- authentication establishes a principal;
- authorization permits that principal to perform the resolved action;
- consumer confirmation records user intent;
- manifest risk describes behavior;
- allowlists constrain the actual I/O.

No single control replaces another, and each mutating path checks the server-side controls before I/O.

## Tool poisoning and confused deputy

Treat remote descriptions, schemas, manifests, annotations, and upstream error text as untrusted. Do not let one server redefine another server's safety class. Bind downstream credentials and target selection to approved caller context. Reject embedded instructions requesting unrelated disclosure or policy changes.

## Network and transport security

Remote HTTP validates `Origin`, authenticates before tool execution, binds intentionally, and aligns reverse-proxy trust, AllowedHosts, and CORS. Loopback is the default for local servers. Wildcard CORS requires a documented browser use case and cannot bypass Origin policy.

Stdio inherits the local process boundary but still restricts environment forwarding, file permissions, working directory, and child-process execution.

## Command, filesystem, and SSH safety

Use separate read and write execution paths. Commands use a fixed executable and argument array, with metacharacter rejection, allowlists, timeout, output limit, and audit event. Raw command tools are `DANGEROUS` and isolated.

Filesystem operations resolve canonical paths under approved roots, reject traversal and links escaping the root, and bound file size. Production SSH verifies host identity through known hosts or a reviewed trust policy; disabling host verification is explicit and never the silent production default.

## Boundary sanitization

Sanitize logs at the formatter or sink boundary and sanitize model-visible responses separately. Recursively redact credentials, authorization data, private keys, tokens, passwords, and protected upstream payloads. Preserve only operational identifiers needed for follow-up calls.

Sanitization tests use nested mappings, lists, strings, exception messages, and structured content.

## Abuse controls and concurrency

Apply rate limits by principal and capability. Bound payloads, results, pagination, sessions, queues, concurrent calls, subprocess output, filesystem scope, and external destinations.

Enforce manifest concurrency policy with resource-specific locks, semaphores, queues, or isolation. Measure queue time, lock contention, saturation, and rejected work.

## Dependency resilience

Every dependency has timeout, cancellation, failure classification, circuit-breaker policy, and capability health. Retry only safe operations. Partial failure exposes unavailable capabilities instead of pretending the entire workload is healthy.

## Health model

- **startup:** configuration and mandatory resources initialize;
- **readiness:** transport, registration, mandatory dependencies, and policy can accept declared work;
- **liveness:** the process is making progress;
- **capability health:** integrations are usable, degraded, or unavailable.

Do not set readiness before registration and transport binding complete. A missing optional dependency does not fail liveness; all mandatory backends failing does fail readiness.

A deployment or container health command is a fail-closed operational boundary, not a happy-path smoke alias. When the command accepts runtime configuration, its tests cover invalid port or equivalent configuration, unsafe target scope for a loopback-only server, missing required authentication, unreachable readiness, non-ready HTTP status, correctly formatted IPv6 loopback literals when supported, and unknown transport values. Stdio process-liveness health and HTTP authenticated readiness are distinct modes and are tested independently.

## Observability

Record component identity, duration, result category, correlation ID, principal class, dependency, policy decision, retry, cancellation, queueing, and saturation. Never log raw secrets or full sensitive payloads. Export traces and metrics through standard telemetry.

One correlation ID is created at request entry and reused in logs, traces, audit, and response metadata. Audit events preserve principal identity across the authentication boundary: an event emitted after successful authentication carries the authenticated principal, while a rejection emitted before authentication carries an explicit unauthenticated or null principal rather than inheriting stale request state. Audit sink failure follows a declared fail-open or fail-closed policy and remains observable.

## Shutdown and recovery

Stop accepting work, cancel or drain within a deadline, close transports, sessions, clients, leases, subprocesses, and background tasks, flush bounded telemetry, and exit deterministically. Recovery drills cover dependency outage, stuck operation, partial startup, lock contention, session exhaustion, and bad release rollback.

## Verification

Exercise denied access, confused-deputy attempts, malicious metadata, public-bind refusal, Origin/CORS mismatch, secret leakage, command/path bypass, rate limits, timeout, cancellation, race conditions, dependency outage, degraded health, audit identity before and after authentication, audit-sink failure, healthcheck invalid configuration and readiness failures, shutdown with in-flight work, and rollback of a broken artifact.
