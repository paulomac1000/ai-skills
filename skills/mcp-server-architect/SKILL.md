---
name: mcp-server-architect
description: Design, implement, review, and harden MCP servers across Python and .NET with explicit contracts, lifecycle ownership, trust boundaries, and production verification.
---

# MCP server architect

Use this skill for new MCP servers, transport migrations, SDK upgrades, security reviews, or production-readiness audits.

## Workflow

1. Define consumer outcomes, tool boundaries, risk, authorization, and response contracts before choosing an SDK.
2. Separate domain operations from MCP registration, hosting, and transport.
3. Define a complete capability manifest and fail the build when a public component lacks governed metadata.
4. Choose stdio or Streamable HTTP deliberately; keep legacy SSE only for verified compatibility needs.
5. Assign ownership for process, session, request, client, cache, lock, and background-task lifecycles.
6. Define deadlines, cancellation, idempotency, retry, concurrency enforcement, and partial-failure semantics.
7. Add authentication, resource-scoped authorization, confused-deputy controls, input validation, and secret boundaries.
8. Design bounded discovery, summaries, pagination, stable identifiers, versioning, and empty-success behavior.
9. Implement transport-parity middleware, correlation, traces, metrics, audit events, and boundary sanitization.
10. Test domain, manifest, policy, registration, lifecycle, transport, race, and real-client behavior separately.
11. Build and smoke-test the deployment artifact.
12. Review both language profiles and the cross-language incident map before claiming Python/.NET parity.

Read `STANDARD.md`, then use `references/capability-manifests-and-versioning.md`, `references/transport-lifecycle-and-conformance.md`, and the relevant Python or .NET profile. Use `testing-strategy.md`, `security-and-operations.md`, and `problem-solution-matrix.md` for production work.

## Constraints

- Do not place business logic only inside decorated or attributed tool methods.
- Do not treat private SDK registries as a stable contract.
- Do not advertise a transport implemented by a partial custom JSON-RPC bridge.
- Do not default missing capability metadata to read-only.
- Do not declare concurrency safety without enforcing and testing it.
- Do not use stdout for logs on stdio transport.
- Do not build shell commands from agent-controlled text.
- Do not swallow cancellation or convert it into generic failure.
- Do not claim parity between SDKs without mapping the invariant to each platform's lifecycle, DI, and concurrency model.
