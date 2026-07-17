---
description: Security, health, resilience, observability, and deployment controls for production MCP servers.
doc_id: reference.mcp-security-and-operations
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Run authorization, cancellation, rate-limit, dependency-failure, graceful-shutdown, and deployment-artifact exercises.
---

# MCP security and operations

## Trust boundaries

Identify caller, server, downstream dependency, model-visible data, secrets, filesystem, subprocess, and network boundaries. Authenticate the caller and intended audience. Authorize the resolved resource for every invocation. Tool annotations and descriptions do not grant access.

## Tool poisoning and confused deputy

Treat remote tool descriptions, schemas, and annotations as untrusted input. Do not let one server redefine the safety class of another server's capability. Bind downstream credentials and resource selection to approved caller context. Reject instructions embedded in tool descriptions that request unrelated disclosure or policy changes.

## Abuse controls

Apply rate limits by principal and capability. Bound payload size, result size, pagination, concurrent calls, subprocess output, filesystem scope, and external destinations. Dangerous tools use allowlists and isolation. Sensitive results are minimized and redacted.

## Dependency resilience

Every dependency has timeout, cancellation, failure classification, and health state. Use bounded retries only for safe operations. Circuit breakers prevent cascading failure. Graceful degradation exposes which capabilities are unavailable instead of pretending the entire server is healthy.

## Health model

- **startup:** configuration and mandatory resources can initialize;
- **readiness:** the server can accept its declared workload;
- **liveness:** the process is making progress and should not be restarted merely because one optional dependency failed;
- **capability health:** individual integrations report usable, degraded, or unavailable state.

## Observability

Record tool identity, duration, result category, correlation ID, principal class, dependency, cancellation, and policy decision. Never log raw secrets, tokens, full sensitive payloads, or protocol messages without redaction. Export traces and metrics through standard telemetry.

## Shutdown and recovery

Stop accepting work, cancel or drain within a deadline, close transports, release leases and subprocesses, flush bounded telemetry, and exit deterministically. Recovery drills cover dependency outage, stuck operation, partial configuration, and bad release rollback.

## Verification

Exercise denied access, confused-deputy attempts, malicious metadata, rate limits, timeout, cancellation, dependency outage, circuit opening, degraded health, shutdown with in-flight work, and rollback of a broken artifact.
