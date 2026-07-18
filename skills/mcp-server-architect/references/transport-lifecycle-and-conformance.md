---
description: Transport parity, lifecycle ownership, session safety, readiness, and protocol-conformance rules for MCP servers.
doc_id: reference.mcp-transport-lifecycle
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run handshake, listing, invocation, malformed-message, cancellation, disconnect, session, Origin, shutdown, and policy-parity tests for each advertised transport.
---

# MCP transport, lifecycle, and conformance

## Supported transports

Use stdio for local subprocess servers and Streamable HTTP for remote servers. Legacy HTTP+SSE is compatibility-only. A custom REST bridge may be useful operationally, but it is not an MCP transport and cannot justify advertising MCP transport support.

Do not hand-roll a partial `/mcp` JSON-RPC endpoint when the maintained SDK transport is available. Placeholder GET streams, dummy input schemas, incomplete initialization, or flattened error codes create false compatibility.

## Transport factory

One composition root creates domain services, manifests, policy, registration, and lifecycle resources. Transport entry points consume that same composition. Tool names, schemas, authorization, deadlines, error mapping, sanitization, and telemetry are identical across transports.

A REST convenience endpoint delegates to the same application adapter and policy pipeline. It does not invoke raw tool callables through private SDK fields.

## Lifecycle ownership

Document an owner and scope for every resource:

| Resource | Typical owner |
| --- | --- |
| configuration snapshot | process |
| HTTP or SSH client pool | process or tenant |
| authenticated principal | request or session |
| protocol session state | session only when required |
| correlation and cancellation | request |
| cache | process, tenant, or resource key |
| lock or semaphore | the mutable resource it protects |
| background task | host lifecycle |

Initialize each resource once at its owner scope and close it once on normal shutdown, startup failure, cancellation, and transport disconnect. Do not let an SDK callback accidentally create a second process-level client per connection.

## Partial startup and health

Mandatory dependency failure prevents readiness. Optional dependency failure produces a capability state of `degraded` or `unavailable` while unrelated capabilities remain usable.

- startup proves configuration and mandatory initialization;
- readiness proves the declared workload can be accepted;
- liveness proves the process is making progress;
- capability health reports each optional integration;
- health never becomes ready before transport binding and registration checks finish.

If all configured backends fail and the server has no useful zero-I/O capability, fail startup. If some backends succeed, select a valid default explicitly and report failed targets without leaking credentials.

## Stateless and stateful HTTP

Prefer stateless HTTP when sampling, elicitation, resumability, or cross-request state is unnecessary. Stateful servers bound session count, idle time, storage, cleanup, and migration behavior.

Validate `Origin` on incoming HTTP connections, bind to loopback by default for local deployment, authenticate remote connections, and align AllowedHosts, reverse-proxy trust, and CORS. Wildcard CORS must not undermine an Origin allowlist.

Session identifiers are unguessable, expire, and release rate-limit and resource state on deletion or timeout. Session state is never the sole source of authorization.

## Async and blocking work

An async transport must not call blocking functions directly. Offload blocking filesystem, SSH, subprocess, or legacy HTTP work to a bounded executor, or use a true async client.

Connection pools and async clients can be event-loop-affine. Tests and bridges reuse the owning loop instead of creating a new loop for each call. Shutdown closes clients on that same lifecycle.

## SDK compatibility boundary

Support a deliberate SDK range. Public registration, client, provider, and transport APIs are preferred. When two supported major versions expose different public APIs, one compatibility adapter normalizes enumeration and invocation.

Private fields may appear only inside that adapter as a temporary compatibility measure. The adapter:
- has no policy or domain decisions;
- fails closed when discovery is incomplete;
- records the detected SDK path;
- has contract tests for every supported version;
- is removed when the old version leaves support.

Never swallow registration or manifest-injection failure and continue with an apparently healthy server.

## Conformance and parity matrix

For each advertised transport, test:

1. initialization and protocol-version negotiation;
2. component listing with real schemas;
3. representative read and authorized mutation;
4. validation and protocol-native errors;
5. cancellation and deadline propagation;
6. malformed input and unknown method behavior;
7. auth, authorization, rate limit, and Origin policy;
8. response and log sanitization;
9. disconnect, session expiry, and shutdown cleanup;
10. identical manifest, schema, and policy results across transports.

## Verification

Run the official client, inspector, or conformance tester against the packaged artifact. A transport is removed from capability discovery when any mandatory conformance or policy-parity test is skipped or failing.
