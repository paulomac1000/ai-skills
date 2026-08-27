---
description: Separate implementation profile for the independently distributed FastMCP package, including package routing, middleware, auth context, mounted-server state, transport, compatibility, and evidence boundaries.
doc_id: reference.python-fastmcp-package
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification:
  kind: ci-job
  value: Resolve the installed fastmcp distribution and run package-version-specific registration, middleware, auth-context, mounted-state, transport, official-client, and exact-artifact tests.
---

# Python FastMCP package profile

## Profile identity

This profile applies only to the independently distributed package whose installed distribution and import namespace are `fastmcp`.

It does not apply merely because code uses a class named `FastMCP`. The official Python MCP SDK and the FastMCP package are separate SDK families. Similar class names do not imply compatible middleware, lifecycle, providers, auth context, component APIs, or transports.

Before editing a project, record:

- distribution name from the lock or installed metadata;
- exact version and allowed range;
- import paths used by production code;
- registration API;
- middleware API;
- authentication provider and token access API;
- transport start and embedding API;
- mounted or composed server behavior;
- public APIs used for component enumeration and testing.

A project that cannot establish these facts is `unsupported-sdk-profile`. L2+ adoption requires either this reviewed profile for the exact package lane or an owned, expiring waiver. Do not silently route it through the official-SDK generator.

## Support boundary

The `ai-skills` canonical Python generator targets the official `mcp` package. This FastMCP profile currently governs assessment, migration, and hardening of existing FastMCP projects; it does not claim that the official generator emits a FastMCP project.

Do not translate code between the two SDK families by renaming imports. Migration requires a strangler plan around the application-owned kernel and executable parity tests.

## Architecture

FastMCP decorators, providers, transforms, middleware, and mounts remain adapters. Domain logic, target resolution, manifests, approval, retry, concurrency, tasks, artifacts, and response policy stay in application-owned components.

Every public component delegates to one invocation kernel. Middleware may reject, enrich, or observe calls, but it does not become the only location for authorization, target policy, idempotency, or audit semantics.

Do not call decorated functions directly as a substitute for transport tests. Do not inspect or mutate private component registries as the production architecture.

## Authentication and authorization

FastMCP authentication and authorization are package-specific contracts:

- an configured auth provider authenticates HTTP requests before component execution;
- authorization checks can filter component visibility and block direct execution;
- server-level `AuthMiddleware` and component-level checks compose and both must pass;
- token data is available through the package auth context only for authenticated HTTP transports;
- stdio has no OAuth token boundary and needs an explicit trusted process principal policy.

Normalize the package `AccessToken` or equivalent reviewed auth object into an immutable application `CallerContext`. Bind principal ID, client ID, scopes, audience/resource, target grants, correlation, and deadline per request.

Never store the first network principal as process-wide state. Add an overlap test with two principals proving that component visibility, execution, target access, task state, artifacts, and audit records cannot cross.

Authentication middleware must run before target/backend resolution and before principal-partitioned quotas. Authorization metadata supplied by a tool argument is untrusted.

## Middleware ordering and state

FastMCP middleware is a package feature, not an MCP protocol primitive. Record and test ordering explicitly:

1. controlled error boundary;
2. authentication and authorization;
3. request identity and deadline extraction;
4. quotas and concurrency admission;
5. application invocation;
6. response minimization and audit.

Initialization may run before an MCP session/request context exists. Code must check context availability and use reviewed HTTP helpers only when the transport is HTTP.

Mounted servers have distinct middleware and state ownership. Parent middleware may run for child requests, but request/session state does not automatically cross server boundaries. Sharing a state store is an explicit security and lifecycle decision, not a default convenience.

State stored for a request must be request-scoped. Serializable session state must not contain secrets, live clients, locks, filesystem handles, browser contexts, or process-global principals.

## Registration and manifests

Decorators may describe components but are not the capability policy source of truth. Every tool, resource, prompt, and public custom component has one application-owned manifest validated by the canonical schema.

At startup and CI, enumerate components through reviewed public package APIs. Fail on:

- registered component without a manifest;
- manifest without a component;
- duplicate stable identity;
- inactive component that remains callable;
- description/schema mismatch that changes approval or policy semantics;
- provider or transform that hides a component from coverage.

Mounted and transformed components must preserve a stable source identity and namespace. Display names do not authorize target or backend selection.

## Errors and content

FastMCP middleware stops a request by raising the package error type appropriate to the operation. Returning an error-shaped ordinary value is still a successful tool result unless the package maps it to a protocol-native error.

Test separately:

- malformed protocol request;
- validation failure;
- authorization denial during listing and direct call;
- controlled domain execution error;
- timeout/cancellation;
- unknown outcome after a possible side effect;
- sanitized internal failure.

Content transforms and serializers are transport adapters. The final serialized payload, including metadata and encoding, remains within the manifest byte bound.

## Transport policy

Use stdio or Streamable HTTP for new and migrated primary hosts. Legacy two-endpoint HTTP+SSE is not a normal FastMCP deployment profile and receives no new capabilities.

Stdio requirements:

- protocol-only stdout;
- logs on stderr;
- explicit process principal and scope provisioning;
- allowlisted environment for client subprocesses;
- official-client initialization, listing, representative call, failure, cancellation, and shutdown tests.

Streamable HTTP requirements:

- reviewed auth provider;
- explicit bind, state/session, Origin, host, body, header, response, queue, and connection limits;
- request-scoped caller context;
- direct-call authorization in addition to discovery filtering;
- official-client test against the built artifact and exact container.

A custom ASGI/REST bridge does not count as MCP transport conformance unless an official MCP client completes the full contract.

## Lifecycle and composition

Do not construct clients, providers, browser sessions, or configuration at import time. The application composition root creates them after settings validation and owns deterministic cleanup.

Mounted servers, proxy providers, OpenAPI providers, and remote components expand the trust boundary. For each one record:

- source identity and immutable configuration;
- principal propagation;
- target/backend confinement;
- schema and manifest provenance;
- timeout and retry ownership;
- lifecycle and cleanup owner;
- SSRF, redirect, credential, and confused-deputy controls;
- behavior when the provider changes or becomes unavailable.

Provider metadata may only conservatively restrict application policy. It cannot make an unknown operation safe, idempotent, retryable, reversible, or low risk.

## Tasks, artifacts, browser profiles, and blocking work

Package-level task or progress features do not replace an application-owned supervised executor. Durable work is principal-, target-, capability-, and approval-bound and has bounded admission, retention, cancellation, reconciliation, and shutdown.

Artifacts use opaque IDs and confined writable roots. Browser profiles are isolated credential stores. Blocking adapters use bounded executors or isolated processes; response timeout does not release their permit while work continues.

## Version and security review

Pin the exact FastMCP package lane in locks and the adoption record. Before changing versions:

- review release notes and security advisories;
- inventory providers, proxy/auth flows, installer subprocesses, and OpenAPI surfaces;
- verify public APIs used by the project;
- run middleware ordering and mounted-state tests;
- run two-principal auth isolation tests;
- run SSRF, redirect, command/path injection, malformed bearer, and oversized-input regressions where applicable;
- run exact-wheel/container stdio and HTTP official-client tests;
- keep candidate evidence separate from the publishing lane.

Security findings are evaluated against the actual framework and call path. A generic linter suggestion is not applied until the issue is reproduced and protected by a regression test.

## Migration to the official SDK

Migrate around the application-owned kernel:

1. inventory FastMCP-specific registration, providers, middleware, auth, state, transports, and content transforms;
2. freeze manifests and public wire behavior;
3. add parity tests through a real client;
4. implement an official-SDK adapter beside the FastMCP adapter;
5. run both against the same kernel and exact artifacts;
6. switch one transport/profile at a time;
7. remove the old adapter only after behavior, security, lifecycle, and rollback evidence is complete.

Do not claim parity solely because both adapters list the same number of tools.
