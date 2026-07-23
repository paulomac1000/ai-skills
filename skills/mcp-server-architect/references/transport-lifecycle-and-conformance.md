---
description: Transport parity, invocation-kernel, lifecycle ownership, target safety, readiness, and protocol-conformance rules for MCP servers.
doc_id: reference.mcp-transport-lifecycle
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run handshake, listing, invocation-kernel, malformed-message, cancellation, disconnect, session, Origin, target-failure, shutdown, legacy-transport absence, and policy-parity tests for each advertised transport.
---

# MCP transport, lifecycle, and conformance

## Supported transports

Use stdio for local subprocess servers and Streamable HTTP for remote servers. The deprecated two-endpoint HTTP+SSE transport from protocol revision 2024-11-05 is forbidden in every new server and generated project. Do not set an SDK's legacy-SSE compatibility switch in normal configuration, even to `false`, when the switch is obsolete and its default already disables the endpoints.

Existing L2+ services migrate to Streamable HTTP. A temporary legacy compatibility adapter is permitted only for a named client that cannot migrate yet. It is disabled by default, isolated from the primary host, restricted to an explicit client or network allowlist, covered by dedicated conformance and policy-parity tests, assigned an owner and removal deadline, and receives no new capabilities. Remove the adapter as soon as the final client migrates.

Do not use the shorthand “ban SSE” because modern Streamable HTTP may still use `text/event-stream` responses or a GET stream. That framing is part of Streamable HTTP and is not the deprecated split `/sse` plus `/message` transport. There is no protocol-wide removal date for legacy HTTP+SSE. Do not invent one; follow normative MCP deprecation policy and reviewed SDK release notes.

A custom REST bridge may be useful operationally, but it is not an MCP transport and cannot justify advertising MCP transport support. Do not hand-roll a partial `/mcp` JSON-RPC endpoint when the maintained SDK transport is available. Placeholder streams, dummy schemas, incomplete initialization, custom session semantics, or flattened error codes create false compatibility.

## One invocation kernel

One composition root creates typed settings, domain services, target resolvers, manifests, policy, lifecycle resources, and one invocation kernel. Transport entry points consume that same composition.

The invocation kernel owns target resolution, authentication, authorization, operator policy, validation, deadline, idempotency, retry, rate limiting, concurrency, execution, error mapping, sanitization, and telemetry. Tool names, schemas, active profiles, and policy results remain identical across transports.

A convenience endpoint delegates to the same kernel through an application adapter or public MCP client. It never invokes raw tool callables through private SDK fields, fabricates request context, reconstructs weaker schemas, bypasses policy, or converts a domain failure into transport-specific success. Policy-parity tests compare kernel inputs and outputs, not only status codes.

## Configuration and startup order

Load secret sources and environment files before importing or constructing components that capture configuration. Validate one immutable settings snapshot before binding transports.

Startup proceeds through explicit states:

1. settings validated;
2. mandatory resources initialized;
3. optional resources classified;
4. supported and active capabilities reconciled;
5. registration and manifest coverage verified;
6. transport bound;
7. readiness published.

A repository test suite is not a startup phase. Bounded dependency diagnostics may run at startup, but development test dependencies cannot be required by the production artifact.

## Lifecycle ownership

Document an owner and scope for every resource:

| Resource | Typical owner |
| --- | --- |
| configuration snapshot | process |
| HTTP or SSH client pool | process, tenant, or target |
| authenticated principal | request or protocol session |
| resolved stable target | request, revalidated before side effects |
| protocol session state | session only when required |
| correlation and cancellation | request |
| cache | process, tenant, target, or resource key |
| lock, semaphore, quota, executor | mutable resource or upstream quota it protects |
| long-running task | host lifecycle or durable task store |
| generated export | task plus explicit retention owner |

Initialize each resource once at its owner scope. Close initialized resources during startup-failure cleanup; close request- and session-owned resources on cancellation or transport disconnect, and close target-, tenant-, process-, and host-owned resources only during their owner-scope shutdown. An individual disconnect must not tear down shared clients.

Subprocess timeout or cancellation terminates the process group, drains bounded output, and awaits exit. Async connection closure waits on the owning scheduler. Background work is supervised; no daemon thread, untracked coroutine, or fire-and-forget `Task.Run` remains outside host shutdown.

## Targets and partial startup

Mandatory dependency failure prevents readiness. Optional dependency failure produces `degraded` or `unavailable` capability state while unrelated capabilities remain usable.

An unavailable requested target returns a controlled error. An unavailable configured default does not silently select the first healthy target. The operator must configure a replacement or the caller must select one explicitly. This applies to reads when confidentiality or tenant boundaries differ.

Every invocation records the resolved target identity and backend kind. Authorization occurs after target resolution. Mutable address-to-identity bindings are revalidated immediately before side effects. If all configured backends fail and no useful zero-I/O capability remains, fail startup.

## Health semantics

- startup reports initialization progress and terminal startup failure;
- readiness proves mandatory capabilities and declared workload can be accepted;
- liveness proves the process and scheduler are making progress;
- capability health reports optional integration, target, and privileged-adapter state;
- task health reports saturation and stuck work;
- registration count or successful port binding alone never means ready;
- readiness is withdrawn when a mandatory dependency or invocation kernel becomes unusable.

Health payloads are bounded and do not expose credentials, private endpoints, or sensitive inventory.

## Stateless and stateful HTTP

Set the mode explicitly. Prefer stateless HTTP when server-to-client requests, subscriptions, resumability, per-client isolation, or cross-request state are unnecessary. Stateful servers bound session count, idle time, storage, cleanup, principal ownership, migration, and distributed deployment behavior.

Validate canonicalized `Origin`, bind to loopback by default locally, authenticate remote connections, and align host policy, reverse-proxy trust, TLS, and restrictive CORS. Wildcard CORS must not undermine an Origin allowlist. A flag acknowledging public exposure is never sufficient security.

Session identifiers are unguessable, expire, remain bound to the authenticated principal, and release rate-limit, task, and resource state on deletion or timeout. Session state is never the sole source of authorization. Stateless mode does not justify process-global principal or target state.

## Async, blocking work, and scheduler affinity

An async transport must not call blocking functions directly. Use a true async client or a bounded executor with explicit worker count, queue limit, deadline, saturation metrics, and shutdown.

`asyncio.to_thread` without executor policy does not bound capacity. Request code does not call `asyncio.run`, `run_until_complete`, or create a fresh event loop to reach an async SDK method. .NET request code does not use `.Result`, `.Wait()`, or untracked `Task.Run`.

Rate limiters and request-spacing state are concurrency-safe. Their key matches the upstream quota scope such as credential, principal, tenant, target, or endpoint. Authentication runs before principal-partitioned rate limiting.

## Long-running work and expected disconnect

A long operation declares synchronous or task-based execution. Task-based transports expose bounded status, progress, cancellation, final result, expiry, and cleanup through stable capabilities. Protocol Tasks are not an executor; durable continuation requires durable metadata and supervised work execution.

Restart, firmware, interface, service, and network changes may intentionally disconnect the target. The invocation kernel returns accepted or in-progress state with resolved target, verification deadline, and follow-up method. It does not turn expected disconnect into generic retryable timeout.

Multi-step changes preserve plan, pre-state or conflict token, per-step result, commit boundary, verification, partial state, and compensation. Transport disconnect does not erase a durable operation record.

## SDK compatibility boundary

Support a deliberate package and SDK range. Package identity matters: similarly named server classes from different distributions are not assumed compatible. Prefer public registration, client, provider, middleware, filter, and transport APIs.

When supported SDK lanes expose different APIs, one compatibility adapter normalizes registration, invocation, and content. Private fields may appear only inside a temporary, version-tested adapter. It contains no policy or domain decisions, fails closed, records package/version/path, and is removed when the old lane leaves support.

Never swallow registration, wrapper, manifest, lifecycle, or compatibility failure and continue with an apparently healthy server.

## Conformance and parity matrix

For each advertised transport, test:

1. initialization and protocol-version negotiation;
2. component listing with real schemas and active-profile state;
3. representative read and authorized mutation;
4. validation, structured output, and protocol-native errors;
5. cancellation, blocking deadline, and late-result handling;
6. malformed input and unknown method behavior;
7. authentication, authorization, target binding, rate limiting, host, and Origin policy;
8. response and log minimization;
9. disconnect, session expiry, long-task state, and shutdown cleanup;
10. identical invocation-kernel manifest, schema, policy, target, and error results;
11. failed-default and unavailable-target behavior;
12. expected-disconnect and postcondition workflow;
13. absence of legacy HTTP+SSE endpoints unless a documented compatibility exception is under test.

A convenience REST bridge passes the same invocation-kernel policy tests but is not counted as MCP conformance.

## Verification

Run the official client, inspector, or conformance tester against the exact packaged artifact. Remove a transport from capability discovery when any mandatory conformance or policy-parity test is skipped or failing. Prove health, active catalogs, target identity, legacy-endpoint absence, and cleanup under partial startup, concurrent calls, cancellation, and shutdown.
