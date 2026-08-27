---
description: Official Python MCP SDK v2 profile for package identity, protocol revisions, lifecycle, request context, transport, manifests, exact-artifact testing, and upgrade evidence.
doc_id: reference.python-official-mcp-sdk
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification:
  kind: ci-job
  value: Generate the canonical Python server, install the exact wheel outside the checkout, and run official-client stdio and Streamable HTTP tests for every claimed protocol revision.
---

# Python official MCP SDK profile

## Profile identity

This profile applies only when all of the following are true:

- the installed distribution is `mcp`;
- application imports resolve through the official `mcp` namespace;
- registration, client, transport, and context APIs match the reviewed official SDK lane;
- the dependency lock and assessment identify the exact package version;
- no separately distributed `fastmcp` package supplies the server implementation.

The similarly named `FastMCP` convenience class available from the official SDK does not turn the project into a FastMCP-package project. Package identity, import ownership, and runtime API determine the profile.

A project that imports both `mcp` and `fastmcp`, wraps one implementation with the other, or cannot prove which distribution owns a public API is a mixed-SDK project. Treat it as `unsupported-sdk-profile` until a reviewed compatibility profile defines ownership and tests.

## Generated baseline

For a new project run:

```text
python skills/mcp-server-architect/tools/generate_python_server.py \
  <target> --package <package_name> --name "<Server Name>"
```

The generator renders one canonical template tree. It must not patch a weaker baseline through string replacement. Generated output includes:

- immutable settings;
- application-owned capability manifests validated by the repository schema;
- one transport-independent invocation kernel;
- official SDK registration;
- stdio and Streamable HTTP;
- request-scoped principal propagation;
- protocol-native failures and bounded final responses;
- exact-wheel and exact-container official-client smoke tests;
- pinned, auditor-clean CI.

Generated code is an architecture seed, not proof that a domain integration is production-ready.

## Protocol revision contract

Record three distinct facts:

1. revisions supported by the upstream package;
2. revisions exercised by this repository against the exact package and artifact;
3. revisions claimed by the adopting project.

Never copy upstream support into `tested_revisions`. A tested revision requires an official client against the exact installed or published artifact.

For the 2026-07-28 protocol era, acceptance covers:

- modern `server/discover` behavior;
- stateless request processing;
- request-scoped client info, capabilities, and protocol metadata;
- required method/name headers where applicable;
- cache-hint behavior for list operations;
- structured multi-round-trip or input-required behavior when used;
- extension negotiation rather than accidental activation;
- compatibility with every earlier revision explicitly claimed by the project.

The legacy compatibility test must force the earlier revision. Automatic client fallback alone is not evidence that both eras were intentionally tested.

## Application architecture

Keep settings, manifests, policy, target resolution, domain adapters, tasks, artifacts, and responses independent from SDK registration. Build one application-owned invocation kernel that performs, in order:

1. capability and manifest resolution;
2. local input normalization;
3. caller authentication;
4. namespace authorization;
5. confined target resolution;
6. exact resource authorization;
7. approval, retry, deadline, quota, and concurrency policy;
8. target identity revalidation;
9. domain I/O;
10. error and unknown-outcome mapping;
11. response minimization, final byte-bound enforcement, and audit emission.

MCP, REST, CLI, tests, and compatibility adapters delegate to the same kernel. They do not call raw registered functions or reconstruct policy from SDK metadata.

## Lifecycle and request context

Load and validate configuration before creating clients or registering components. Importing a module must not read secrets, perform network I/O, or allocate process resources.

Process resources have one explicit lifespan owner. Connection or request callbacks do not recreate shared upstream clients unless the manifest deliberately declares that ownership model.

For HTTP, normalize the authenticated transport identity into an immutable `CallerContext` for each request. Use request-scoped context only as an adapter into the kernel. Never cache one network principal in process-global state.

For local stdio, derive the principal from the trusted process or operating-system boundary described in `principal-and-shell-boundaries.md`. Tool arguments never supply identity or scopes.

## Transport policy

New servers use stdio or Streamable HTTP. The deprecated two-endpoint HTTP+SSE transport is not generated and receives no new capabilities.

Stdio requirements:

- stdout contains protocol traffic only;
- logs and diagnostics use stderr;
- the child environment is explicitly allowlisted in client and conformance examples;
- termination, cancellation, and stderr capture are bounded.

Streamable HTTP requirements:

- explicit bind and state mode;
- authentication before target, backend, artifact, task, browser, or network resolution;
- canonical Origin and host policy;
- bounded headers, body, JSON depth, response bytes, queues, and connections;
- authenticated principal propagation into the kernel;
- minimal unauthenticated liveness/readiness only when the deployment profile explicitly permits it.

## Capability manifests

Every registered public component has exactly one manifest validated by `contracts/capability-manifest.schema.json` and semantic validation.

Factories may provide syntax but must default write and destructive claims conservatively:

- `retryable: false`;
- `idempotent: false`;
- `reversible: false`;
- `requires_confirmation: false` unless a server-enforced approval policy is configured.

Positive write claims require typed evidence and a regression test. `requires_confirmation: true` requires a server-verifiable approval record bound to principal, capability, target, normalized arguments digest, expiry, and one-time consumption policy.

Registration and startup fail on missing, duplicated, orphaned, inactive-but-invokable, or schema-inconsistent manifests.

## Concurrency, deadlines, and blocking work

A response timeout does not terminate work. Work that still runs retains its permit, keyed lock, and capacity accounting until a real terminal state. Late output is discarded but remains visible to metrics and shutdown.

Declare concurrency scope and limits separately. Keyed serialization can permit global parallelism while preserving one-at-a-time execution per target, credential, resource, or principal.

Blocking libraries run through a bounded executor or isolated process with downstream deadlines shorter than the request deadline. `asyncio.to_thread` without queue and shutdown ownership is not a production policy.

## Filesystem, artifacts, tasks, and browser state

Filesystem policies distinguish metadata listing, text reads, binary reads, traversal, extraction, and artifact writes. Every public handle is opaque and server-owned. High-assurance profiles use no-follow or handle-relative operations appropriate to the operating system, not only lexical path checks.

Artifacts record owner, target, operation, media type, size, integrity, creation, expiry, and deletion. Containers declare writable roots and test the real read-only-root deployment.

Long-running work uses a bounded, principal-bound registry or durable executor. Non-interruptible work records deadline exceeded, abandoning, abandoned, unknown outcome, terminated, and completed-late states as applicable.

Writable browser profiles are credential stores with per-account confinement, process locking, cleanup, and cross-request isolation.

## Authentication and malformed input

Use one reviewed bearer parser for the selected HTTP profile. Tests cover:

- empty credentials;
- wrong scheme;
- repeated separators;
- non-ASCII input;
- oversized headers;
- constant-time comparison type mismatches;
- two overlapping principals with distinct authorization and state.

Authentication failures are controlled protocol or HTTP errors, never uncaught exceptions.

## Exact-artifact acceptance

The Python lane proves all of the following:

1. build one wheel;
2. record its digest;
3. install that exact wheel into an isolated environment outside the source checkout;
4. prove imports resolve from installed package locations;
5. run official-client stdio modern and legacy-revision tests;
6. build the container by copying the same wheel, not rebuilding from source;
7. run the same official-client contract against the exact container over stdio and Streamable HTTP;
8. verify failure paths and write boundaries;
9. retain JUnit and execution counts showing the mandatory suites actually ran.

Multi-architecture publication follows `multiarch-artifact-promotion.md`; it never rebuilds after platform smoke tests.

## Upgrade procedure

Before changing the SDK pin:

- inventory public and private API usage;
- render a fresh project from the canonical template;
- regenerate every platform lock;
- test registration, discovery, schemas, middleware, auth context, cancellation, transports, and shutdown;
- run exact-wheel and exact-container tests for every claimed revision;
- keep candidate results separate from the publishing stable lane;
- update the manifest only after evidence is bound to the exact revision.

Private SDK fields belong only in a version-bounded compatibility adapter. The adapter contains no domain, target, authorization, retry, or manifest decisions.
