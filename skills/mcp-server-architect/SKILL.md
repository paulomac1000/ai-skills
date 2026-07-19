---
name: mcp-server-architect
description: Design, generate, implement, review, and harden complete MCP servers across Python and .NET with explicit contracts, lifecycle ownership, trust boundaries, and production verification.
---

# MCP server architect

Use this skill for new MCP servers, transport migrations, SDK upgrades, security reviews, production-readiness audits, and recovery of architectural knowledge from existing servers.

## Workflow

1. Define consumer outcomes, cross-tool workflows, stable ID flow, tool boundaries, risk axes, authorization, and response contracts before choosing an SDK.
2. For a new Python server, generate the executable baseline with `python skills/mcp-server-architect/tools/generate_python_server.py <target> --package <package_name> --name "<Server Name>"` rather than copying an old server.
3. Install the generated project and run its own tests through the official in-memory MCP client before adding domain integrations.
4. Separate domain operations from MCP registration, hosting, transport, artifacts, tasks, and browser or privileged adapters.
5. Define a complete capability manifest and fail the build when a public component lacks governed metadata.
6. Choose stdio or Streamable HTTP deliberately; keep legacy SSE only for verified compatibility needs.
7. Assign ownership for process, tenant, target, session, request, client, cache, lock, executor, artifact, browser profile, and background-task lifecycles.
8. Define deadlines, cancellation, idempotency, retry, concurrency enforcement, expected disconnect, reconciliation, and partial-failure semantics.
9. Add authentication, resource-scoped authorization, confused-deputy controls, safe path and command validation, secret boundaries, and request/session quotas.
10. Design bounded discovery, server instructions, profiles, summaries, pagination, stable identifiers, versioning, provenance, and empty-success behavior.
11. Implement transport-parity policy, correlation, traces, metrics, audit events, and separate response and log sanitization.
12. Test domain, manifest, policy, registration, lifecycle, filesystem, artifacts, tasks, browser state, transport, race, and real-client behavior separately.
13. Build and smoke-test the exact deployment artifact.
14. Review both language profiles and the cross-language incident map before claiming Python/.NET parity.

Read `STANDARD.md`, then use `references/capability-manifests-and-versioning.md`, `references/transport-lifecycle-and-conformance.md`, `references/runtime-boundaries-and-artifacts.md`, and the relevant Python or .NET profile. Use `references/python-migration-simulation.md`, `references/testing-strategy.md`, `references/security-and-operations.md`, and `references/problem-solution-matrix.md` for production work.

## Generated Python baseline

The generator creates an atomic, non-overwriting project using the stable official Python SDK lane. It includes typed settings, manifests, one invocation kernel, stdio and loopback Streamable HTTP, tools, resources, a prompt, server instructions, packaging, Docker, pinned CI, fail-closed sample mutation, and a real-client test.

Treat the result as a verified architecture seed. Replace the sample domain adapter, review every manifest, add real authentication and per-resource authorization, and implement all applicable upstream, artifact, task, browser, and deployment tests before production use.

## Constraints

- Do not place business logic only inside decorated or attributed tool methods.
- Do not treat private SDK registries as a stable contract.
- Do not advertise a transport implemented by a partial custom JSON-RPC bridge.
- Do not default missing capability metadata to read-only.
- Do not declare concurrency safety without enforcing and testing it.
- Do not use stdout for logs on stdio transport.
- Do not build shell commands from agent-controlled text.
- Do not validate filesystem containment with string prefixes.
- Do not create daemon threads or untracked tasks as operation records.
- Do not expose browser profiles, container sockets, SSH, or raw device protocols as ordinary low-risk adapters.
- Do not swallow cancellation or convert expected disconnect into generic retryable failure.
- Do not claim a generated server works until a real MCP client lists and invokes it.
- Do not claim parity between SDKs without mapping the invariant to each platform's lifecycle, DI, and concurrency model.
