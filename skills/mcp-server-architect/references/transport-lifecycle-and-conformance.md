---
description: Transport parity, invocation-kernel, lifecycle ownership, target safety, readiness, and protocol-conformance rules for MCP servers.
doc_id: reference.mcp-transport-lifecycle
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run handshake, listing, invocation-kernel, malformed-message, cancellation, disconnect, session, Origin, target-failure, shutdown, and policy-parity tests for each advertised transport.
---

# MCP transport, lifecycle, and conformance

## Supported transports

Use stdio for local subprocess servers and Streamable HTTP for remote servers. Legacy HTTP+SSE is compatibility-only. A custom REST bridge may be useful operationally, but it is not an MCP transport and cannot justify advertising MCP transport support.

Do not hand-roll a partial `/mcp` JSON-RPC endpoint when the maintained SDK transport is available. Placeholder streams, dummy input schemas, incomplete initialization, custom session semantics, or flattened error codes create false compatibility.

## One invocation kernel

One composition root creates typed settings, domain services, target resolvers, manifests, policy, lifecycle resources, and one invocation kernel. Transport entry points consume that same composition.

The invocation kernel owns target resolution, authentication, authorization, operator policy, validation, deadline, idempotency, retry, rate limiting, concurrency, execution, error mapping, sanitization, and telemetry. Tool names, schemas, active profiles, and policy results remain identical across transports.

A REST convenience endpoint delegates to the same kernel through an application adapter or public MCP client. It never:

- invokes raw tool callables through private SDK fields;
- monkey-patches or fabricates an SDK request context;
- reconstructs a weaker schema from a Python signature;
- bypasses middleware, authorization, concurrency, or response minimization;
- converts a domain failure into a transport-specific success.

Policy-parity tests compare kernel inputs and outputs, not only response status codes.

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

Initialize each resource once at its owner scope. Close every initialized resource during startup-failure cleanup; close request- and session-owned resources on cancellation or transport disconnect, and close target-, tenant-, process-, and host-owned resources only during their owner-scope shutdown. An individual client disconnect must not tear down shared clients needed by other sessions. Do not let an SDK callback create a second process-level client per connection.

Subprocess timeout or cancellation terminates the process group, drains bounded output, and awaits exit. Async connection closure waits for completion on the owning event loop. Background tasks are tracked; no fire-and-forget task is left outside host shutdown.

## Targets and partial startup

Mandatory dependency failure prevents readiness. Optional dependency failure produces a capability or target state of `degraded` or `unavailable` while unrelated capabilities remain usable.

An unavailable requested target returns a controlled error. An unavailable configured default does not silently select the first healthy target. The operator must configure a replacement or the caller must select one explicitly. This applies to reads as well as writes when confidentiality or tenant boundaries differ.

Every invocation records the resolved target identity and backend kind. Authorization occurs after target resolution. Mutable address-to-identity bindings are revalidated immediately before side effects.

If all configured backends fail and the server has no useful zero-I/O capability, fail startup. If some succeed, report failed targets without leaking credentials and expose only capabilities that can actually execute.

## Health semantics

- startup reports initialization progress and terminal startup failure;
- readiness proves mandatory capabilities and declared workload can be accepted;
- liveness proves the process and event loop are making progress;
- capability health reports each optional integration, target, and privileged adapter;
- task health reports saturation and stuck work;
- registration count or successful port binding alone never means ready;
- readiness is withdrawn when a mandatory dependency or invocation kernel becomes unusable.

Health payloads are bounded and do not expose credentials, private endpoints, or sensitive inventory.

## Stateless and stateful HTTP

Prefer stateless HTTP when server-to-client requests, subscriptions, resumability, per-client isolation, or cross-request state are unnecessary. Stateful servers bound session count, idle time, storage, cleanup, migration, and distributed deployment behavior.

Validate canonicalized `Origin` values on incoming HTTP connections, bind to loopback by default for local deployment, authenticate remote connections, and align host policy, reverse-proxy trust, TLS, and CORS. Wildcard CORS must not undermine an Origin allowlist.

Origin policy handles scheme, normalized hostname, explicit and default ports, bracketed IPv6, IDNA, malformed values, empty Origin, and proxy forwarding. Wildcard syntax is parsed by a dedicated matcher, not by passing non-numeric ports to a generic URL parser. Redirects and resolved addresses are rechecked against network policy.

A flag acknowledging public exposure is never sufficient security. Privileged remote transports require authentication and authorization before capability execution, even on a trusted private network.

Session identifiers are unguessable, expire, and release rate-limit, task, and resource state on deletion or timeout. Session state is never the sole source of authorization. Stateless mode does not justify process-global principal or target state.

## Async, blocking work, and scheduler affinity

An async transport must not call blocking functions directly. Use a true async client or a bounded executor with explicit worker count, queue limit, deadline, saturation metrics, and shutdown.

`asyncio.to_thread` without an executor policy does not bound capacity. Cancellation cannot stop an already executing blocking function, so downstream timeouts fit inside the request deadline and late results cannot mutate response or task state.

Connection pools and async clients can be event-loop-affine. Tests and bridges reuse the owning loop instead of creating or running a new loop from a request path. Request code does not call `asyncio.run`, `run_until_complete`, or create a fresh event loop to reach an async SDK method.

Rate limiters and request-spacing state are concurrency-safe. Their key matches the upstream quota scope such as credential, tenant, target, or endpoint. Lock acquisition and queue waiting consume the request deadline and remain cancellable.

## Long-running work and expected disconnect

A long operation declares synchronous or task-based execution. Task-based transports expose bounded status, progress, cancellation, final result, expiry, and cleanup through stable capabilities.

Restart, firmware, interface, service, and network changes may intentionally disconnect the target. The invocation kernel returns accepted or in-progress state with resolved target, verification deadline, and follow-up method. It does not turn expected disconnect into a generic retryable timeout.

Multi-step changes preserve plan, pre-state or conflict token, per-step result, commit boundary, verification, partial state, and compensation. Transport disconnect does not erase the server-side operation record when durable continuation is promised.

## SDK compatibility boundary

Support a deliberate package and SDK range. Package identity matters: similarly named server classes from different distributions are not assumed compatible. Public registration, client, provider, middleware, transform, and transport APIs are preferred.

When supported SDK lanes expose different public APIs, one compatibility adapter normalizes enumeration, registration, invocation, and content. Private fields may appear only inside that adapter as a temporary measure. The adapter:

- has no policy, target, configuration, or domain decisions;
- fails closed when discovery or invocation is incomplete;
- never imports test mocks or fabricates production context;
- records package, version, and selected compatibility path;
- has contract tests for every supported lane;
- is removed when the old lane leaves support.

Never swallow registration, wrapper, manifest, lifecycle, or compatibility failure and continue with an apparently healthy server.

## Conformance and parity matrix

For each advertised MCP transport, test:

1. initialization and protocol-version negotiation;
2. component listing with real schemas and active-profile state;
3. representative read and authorized mutation;
4. validation and protocol-native errors;
5. cancellation, blocking deadline, and late-result handling;
6. malformed input and unknown method behavior;
7. auth, authorization, target binding, rate limit, and Origin policy;
8. response and log minimization and sanitization;
9. disconnect, session expiry, long-task state, and shutdown cleanup;
10. identical invocation-kernel manifest, schema, policy, target, and error results;
11. failed-default and unavailable-target behavior;
12. expected-disconnect and postcondition workflow when applicable.

A convenience REST bridge passes the same invocation-kernel policy tests but is not counted as MCP conformance.

## Verification

Run the official client, inspector, or conformance tester against the packaged artifact. Remove a transport from capability discovery when any mandatory conformance or policy-parity test is skipped or failing. Prove that health, active catalogs, target identity, and cleanup remain correct under partial startup, concurrent calls, cancellation, and shutdown.