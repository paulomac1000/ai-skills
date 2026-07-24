---
name: mcp-server-architect
description: Design, generate, implement, review, and harden complete MCP servers across Python and .NET with explicit contracts, lifecycle ownership, trust boundaries, and production verification.
---

# MCP server architect

Use this skill for new MCP servers, transport migrations, SDK upgrades, security reviews, production-readiness audits, and recovery of architectural knowledge from existing servers.

## Workflow

1. Define consumer outcomes, cross-tool workflows, stable ID flow, tool boundaries, risk axes, authorization, and response contracts before choosing an SDK.
2. For an existing server, create `migration-assessment.yaml` from `templates/migration-assessment.yaml.template`, pin the immutable source revision, and classify every rule from `contracts/rule-catalog.yaml` before changing code. The file is the repository-wide adoption contract plus the required `extensions.mcp` evidence.
3. For a new server, generate a baseline instead of copying an old server:
   - Python: `python skills/mcp-server-architect/tools/generate_python_server.py <target> --package <package_name> --name "<Server Name>"`;
   - .NET: `python skills/mcp-server-architect/tools/generate_dotnet_server.py <target> --namespace <Root.Namespace> --name "<Server Name>"`.
4. Install or restore the generated project and run its own official-client smoke before adding domain integrations.
5. Separate domain operations from MCP registration, hosting, transport, artifacts, tasks, and browser or privileged adapters.
6. Define a complete capability manifest and fail the build when a public component lacks governed metadata.
7. Choose stdio or Streamable HTTP deliberately. Never implement the deprecated two-endpoint HTTP+SSE transport in a new server.
8. Migrate existing legacy HTTP+SSE servers to Streamable HTTP. A temporary compatibility adapter is exceptional, disabled by default, isolated from the primary host, allowlisted to known legacy clients, covered by conformance tests, and owned with a removal deadline.
9. Assign ownership for process, tenant, target, session, request, client, cache, lock, executor, artifact, browser profile, and background-task lifecycles.
10. Define deadlines, cancellation, idempotency, retry, concurrency enforcement, expected disconnect, reconciliation, and partial-failure semantics.
11. Add authentication, resource-scoped authorization, confused-deputy controls, safe path and command validation, secret boundaries, and request/session quotas.
12. Design bounded discovery, server instructions, profiles, summaries, pagination, stable identifiers, versioning, provenance, and empty-success behavior.
13. Implement transport-parity policy, correlation, traces, metrics, audit events, and separate response and log sanitization.
14. Test domain, manifest, policy, registration, lifecycle, filesystem, artifacts, tasks, browser state, transport, race, and real-client behavior separately.
15. Build and smoke-test the exact deployment artifact.
16. Complete the applicability, compatibility, behavior, waiver, rollback, residual-risk, exact-artifact, and MCP transport sections of `migration-assessment.yaml`; run `python contracts/validate_adoption.py migration-assessment.yaml --require-approval`; an independent reviewer owns the final decision.
17. Review both language profiles and the cross-language incident map before claiming Python/.NET parity.

Read `STANDARD.md`, then use `references/migration-assessment.md`, `references/capability-manifests-and-versioning.md`, `references/transport-lifecycle-and-conformance.md`, `references/runtime-boundaries-and-artifacts.md`, and the relevant Python or .NET profile. Use both migration simulations, `references/testing-strategy.md`, `references/security-and-operations.md`, and `references/problem-solution-matrix.md` for production work.

## Generated baselines

Both generators are atomic and non-overwriting. They create typed settings, application-owned manifests, one invocation kernel, official SDK registration, stdio and loopback Streamable HTTP, structured results and protocol-native errors, conservative writes, packaging, pinned CI, and a real-client smoke.

The Python seed carries complete platform-specific runtime and development lock graphs with artifact hashes, installs them with `--require-hashes`, runs `pip check`, builds a wheel, installs that exact wheel into an isolated environment, and runs the official-client suite without editable installs or `PYTHONPATH`. The .NET seed restores exact NuGet lock files, publishes the server, and smokes the published DLL.

The .NET seed additionally demonstrates generic tool registration, explicit stateless HTTP, `ClaimsPrincipal`, authorization-filter activation, principal-partitioned rate limiting, separate liveness/readiness, mandatory optimistic concurrency, and principal-bound server-side approvals.

Treat each result as a verified architecture seed. Replace the sample domain adapter, review every manifest, add production identity and per-resource authorization, and implement all applicable upstream, artifact, task, browser, and deployment tests before production use.

## Constraints

- Do not place business logic only inside decorated or attributed tool methods.
- Do not treat private SDK registries as a stable contract.
- Do not advertise a transport implemented by a partial custom JSON-RPC bridge.
- Do not implement legacy HTTP+SSE in new servers or call it equivalent to Streamable HTTP.
- Do not confuse optional SSE framing inside Streamable HTTP with the deprecated two-endpoint HTTP+SSE transport.
- Do not default missing capability metadata to read-only.
- Do not declare concurrency safety without enforcing and testing it.
- Do not use stdout for logs on stdio transport.
- Do not build shell commands from agent-controlled text.
- Do not validate filesystem containment with string prefixes.
- Do not create daemon threads, untracked `Task.Run`, or fire-and-forget work as operation records.
- Do not expose browser profiles, container sockets, SSH, or raw device protocols as ordinary low-risk adapters.
- Do not swallow cancellation or convert expected disconnect into generic retryable failure.
- Do not treat data annotations, tool annotations, or a typed DTO as runtime validation, authorization, or protocol error signaling.
- Do not claim a generated server works until a real MCP client lists and invokes the exact installed or published artifact.
- Do not claim a migration is complete unless the completed assessment passes `contracts/validate_adoption.py --require-approval` against the full stable rule catalog and independently reviewed evidence.
- Do not claim parity between SDKs without mapping the invariant to each platform's lifecycle, DI, and concurrency model.
