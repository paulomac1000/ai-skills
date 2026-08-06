---
name: mcp-server-architect
description: Design, generate, implement, review, and harden complete MCP servers across Python and .NET with explicit contracts, lifecycle ownership, trust boundaries, and production verification.
---

# MCP server architect

Use this skill for new MCP servers, transport migrations, SDK upgrades, security reviews, production-readiness audits, and recovery of architectural knowledge from existing servers.

## Workflow

1. Define consumer outcomes, cross-tool workflows, stable ID flow, tool boundaries, risk axes, authorization, and response contracts before choosing an SDK.
2. For an existing server, create `migration-assessment.yaml` from `templates/migration-assessment.yaml.template`, pin the immutable source revision, and classify every rule from `contracts/rule-catalog.yaml` before changing code. The file is the repository-wide adoption contract plus the required `extensions.mcp` evidence.
3. Resolve the implementation profile before reading SDK-specific guidance or changing code. Record all of the following from locks, installed metadata, and production imports:
   - distribution/package name and exact version;
   - production import namespace and owning distribution;
   - registration and component-enumeration APIs;
   - middleware and authentication-context APIs;
   - transport startup or embedding API;
   - protocol revisions claimed and actually tested.
4. Route Python projects by package identity, not by a similarly named class:
   - official distribution `mcp` and official `mcp` imports: `references/python-official-mcp-sdk.md`;
   - independently distributed `fastmcp` package and `fastmcp` imports: `references/python-fastmcp-package.md`;
   - mixed ownership, unresolved imports, or any other SDK: record `unsupported-sdk-profile` in `extensions.mcp.profiles`. L2+ requires an owned waiver or a reviewed profile with exact tests. Do not route such a project through the official generator by analogy.
5. For a new server, generate a baseline instead of copying an old server:
   - Python official SDK only: `python skills/mcp-server-architect/tools/generate_python_server.py <target> --package <package_name> --name "<Server Name>"`;
   - .NET official SDK: `python skills/mcp-server-architect/tools/generate_dotnet_server.py <target> --namespace <Root.Namespace> --name "<Server Name>"`.
6. Install or restore the generated project and run its own official-client smoke before adding domain integrations.
7. Separate domain operations from MCP registration, hosting, transport, artifacts, tasks, and browser or privileged adapters.
8. Define a complete capability manifest and fail the build when a public component lacks governed metadata.
9. Choose stdio or Streamable HTTP deliberately. Never implement the deprecated two-endpoint HTTP+SSE transport in a new server.
10. Migrate existing legacy HTTP+SSE servers to Streamable HTTP. A temporary compatibility adapter is exceptional, disabled by default, isolated from the primary host, allowlisted to known legacy clients, covered by conformance tests, and owned with a removal deadline.
11. Assign ownership for process, tenant, target, session, request, client, cache, lock, executor, artifact, browser profile, and background-task lifecycles.
12. Define deadlines, cancellation, idempotency, retry, concurrency enforcement, expected disconnect, reconciliation, and partial-failure semantics.
13. Add authentication, resource-scoped authorization, confused-deputy controls, safe path and command validation, secret boundaries, and request/session quotas.
14. Design bounded discovery, server instructions, profiles, summaries, pagination, stable identifiers, versioning, provenance, and empty-success behavior.
15. Implement transport-parity policy, correlation, traces, metrics, audit events, and separate response and log sanitization.
16. Test domain, manifest, policy, registration, lifecycle, filesystem, artifacts, tasks, browser state, transport, race, and real-client behavior separately.
17. Build and smoke-test the exact deployment artifact.
18. Complete the applicability, compatibility, behavior, waiver, rollback, residual-risk, exact-artifact, SDK-profile, protocol-revision, and MCP transport sections of `migration-assessment.yaml`. Use maturity-scaled evidence: local structural evidence cannot approve L2+, hosted exact-SHA evidence cannot approve L3/L4 or sensitive/public deployments without the required independent-release profile.
19. Review every selected language/SDK profile and the cross-language incident map before claiming parity.

Read `STANDARD.md`, then use `references/migration-assessment.md`, `references/capability-manifests-and-versioning.md`, `references/protocol-and-sdk-compatibility.md`, `references/transport-lifecycle-and-conformance.md`, `references/runtime-boundaries-and-artifacts.md`, and the exact resolved SDK profile. Use both migration simulations, `references/testing-strategy.md`, `references/security-and-operations.md`, and `references/problem-solution-matrix.md` for production work.

## SDK profile evidence

Use stable, machine-readable profile entries in `extensions.mcp.profiles`, for example:

```text
sdk:python-official-mcp@2.0.0
protocol:2026-07-28
transport:stdio
transport:streamable-http
```

A FastMCP-package project uses an entry such as `sdk:python-fastmcp@<exact-version>`. A mixed or unsupported implementation records `unsupported-sdk-profile`; it never borrows the support or evidence of another profile.

`upstream-supported`, `repository-tested`, and `project-claimed` are different states. Package release notes may establish the first state only. Moving a revision into a tested or claimed state requires exact-package and exact-artifact official-client evidence.

## Generated baselines

Both generators are atomic and non-overwriting. They create typed settings, application-owned manifests, one invocation kernel, official SDK registration, stdio and loopback Streamable HTTP, structured results and protocol-native errors, conservative writes, packaging, pinned CI, and a real-client smoke.

The Python generator emits the official `mcp` SDK profile only. It carries platform-specific runtime and development lock graphs with artifact hashes, installs them with `--require-hashes`, runs `pip check`, builds a wheel, installs that exact wheel into an isolated environment, and runs the official-client suite without editable installs or `PYTHONPATH`. Its container copies that same prebuilt wheel, verifies the wheel SHA-256, and never rebuilds the package from source. It is not a FastMCP-package generator.

The .NET seed restores exact NuGet lock files, publishes the server, and smokes the published DLL. It additionally demonstrates generic tool registration, explicit stateless HTTP, `ClaimsPrincipal`, authorization-filter activation, principal-partitioned rate limiting, separate liveness/readiness, mandatory optimistic concurrency, and principal-bound server-side approvals.

A generated result is an architecture seed whose acceptance commands must still pass on the exact generated revision. Generation alone, source inspection, or an upstream SDK claim is not evidence that the project works. Replace the sample domain adapter, review every manifest, add production identity and per-resource authorization, and implement all applicable upstream, artifact, task, browser, and deployment tests before production use.

## Adoption and migration evidence

Before claiming that this skill has been adopted or a migration is complete:

1. Read the repository-root rule catalog, atomic child-control catalog, compatibility matrix, evidence profiles, and selected skill manifest.
2. Create one assessment per skill, bound to the exact SHA. Use the assessment bundle/index for a repository-wide migration involving several skills; do not invent a list-valued replacement for the one-skill schema.
3. Record target maturity, deployment profiles, capabilities, exact SDK profile, protocol revisions, and advertised transports. Let machine applicability determine required parent rules and child controls.
4. Bind each passed claim to an executable result file and exact test-case identity. A green job, badge, screenshot, commit message, located command, or hand-written `passed` value is not evidence.
5. Use `local-structural` only for baseline diagnostics. Use a reviewed hosted-provider adapter for L2 exact-SHA evidence. Use `independent-release` for L3/L4 and public, multi-tenant, or sensitive deployment approval.
6. Treat the legacy GitHub Actions adoption schema as the reference provider adapter, not as the provider-neutral evidence model. Provider-neutral records use the shared evidence-provider contract.
7. Run the applicable local validators and the authoritative external acceptance verifier with read-only provider credentials. The candidate revision cannot approve itself.
8. Require an independent review bound to the exact SHA when the selected evidence profile requires it. The reviewer must not be the PR author, commit author/committer, or evidence-producing actor.

Generated templates and examples are architecture seeds, not production acceptance. Apply the relevant CI/CD profile, verify the exact deployment artifact, record rollback and residual risk, and retain provider evidence long enough for the stated decision lifetime.

## Finding triage

A scanner, reviewer bot, or generic linter suggestion is an input, not an automatically valid patch. Before changing code:

1. confirm the actual framework, package version, and call path;
2. reproduce the reported behavior or prove the violated contract;
3. classify it as a standard violation, implementation defect, compatibility issue, or tool false positive;
4. reject framework-incompatible mechanical fixes;
5. add a regression test that fails before the fix and passes after it.

## Constraints

- Do not place business logic only inside decorated or attributed tool methods.
- Do not choose an SDK profile from a class name without proving distribution and import ownership.
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
- Do not claim a migration is complete unless the completed assessment and applicable atomic child controls pass authoritative validation against independently reviewed evidence.
- Do not claim parity between SDKs without mapping the invariant to each platform's lifecycle, DI, and concurrency model.

The assessed revision MUST NOT supply the authoritative verifier, claim catalog, or acceptance workflow used to approve itself; candidate-local validation is diagnostic and final acceptance requires immutable external authority coordinates.
