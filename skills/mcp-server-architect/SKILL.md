---
name: mcp-server-architect
description: Design, generate, implement, review, and harden complete MCP servers across Python and .NET with explicit contracts, lifecycle ownership, trust boundaries, and production verification.
---

# MCP server architect

Use this skill for new MCP servers, transport migrations, SDK upgrades, security reviews, production-readiness audits, and recovery of architectural knowledge from existing servers.

## Workflow

1. Define consumer outcomes, cross-tool workflows, stable IDs, capability boundaries, risk, authorization, and response contracts before choosing an SDK.
2. For an existing server, create `migration-assessment.yaml` from `templates/migration-assessment.yaml.template`, bind it to the exact source revision, and classify every applicable rule before changing code.
3. Resolve distribution name, exact SDK version, import namespace, registration/enumeration APIs, auth context, transport startup API, and protocol revisions from locks and production imports.
4. Route Python by package identity: official `mcp` uses `references/python-official-mcp-sdk.md`; independent `fastmcp` uses `references/python-fastmcp-package.md`; unresolved or mixed ownership is `unsupported-sdk-profile` and requires an owned waiver or reviewed profile for L2+.
5. Generate new baselines instead of copying old servers:
   - Python official SDK: `python skills/mcp-server-architect/tools/generate_python_server.py <target> --package <package_name> --name "<Server Name>"`;
   - .NET official SDK: `python skills/mcp-server-architect/tools/generate_dotnet_server.py <target> --namespace <Root.Namespace> --name "<Server Name>"`.
6. Restore/install the generated project and run its official-client smoke before adding domain integrations.
7. Keep domain operations separate from MCP registration, hosting, transports, artifacts, tasks, browsers, and privileged adapters.
8. Define a complete capability manifest; public components without governed metadata fail closed.
9. Choose stdio or Streamable HTTP deliberately. Never add the deprecated two-endpoint HTTP+SSE transport to a new server.
10. Legacy HTTP+SSE compatibility is exceptional, disabled by default, isolated, allowlisted, tested, owned, and time-bounded while migrating to Streamable HTTP.
11. Assign ownership for process, tenant, target, session, request, client, cache, lock, executor, artifact, browser profile, and background-task lifecycles.
12. Define deadlines, cancellation, idempotency, retry, concurrency, disconnect, reconciliation, and partial-failure semantics.
13. Add authentication, resource-scoped authorization, confused-deputy controls, safe path/command validation, secret boundaries, and quotas.
14. Design bounded discovery, server instructions, pagination, stable identifiers, provenance, and empty-success behavior.
15. Add transport parity, correlation, traces, metrics, audit events, and separate response/log sanitization.
16. Test domain, manifest, policy, registration, lifecycle, filesystem, artifacts, tasks, browser state, transports, races, and real-client behavior independently.
17. Build and smoke the exact deployment artifact; generation or source inspection alone is never acceptance evidence.
18. Complete applicability, compatibility, behavior, waiver, rollback, residual-risk, SDK-profile, protocol-revision, transport, and exact-artifact evidence before claiming adoption.
19. Review the selected SDK profile and cross-language incident map before claiming Python/.NET parity.

Read `STANDARD.md`, `references/migration-assessment.md`, `references/capability-manifests-and-versioning.md`, `references/protocol-and-sdk-compatibility.md`, `references/transport-lifecycle-and-conformance.md`, `references/runtime-boundaries-and-artifacts.md`, the selected SDK profile, both migration simulations, testing strategy, security/operations guidance, and the problem-solution matrix for production work.

## SDK and generated-baseline evidence

Record stable profile entries such as `sdk:python-official-mcp@2.0.0`, `sdk:python-fastmcp@<exact-version>`, `protocol:2026-07-28`, and the advertised transport. `upstream-supported`, `repository-tested`, and `project-claimed` are distinct states; only exact-package and exact-artifact official-client evidence advances a claim beyond upstream support.

Both generators are atomic and non-overwriting. The Python seed emits only the official `mcp` profile, uses hash-locked dependency graphs, builds one wheel, installs/smokes that exact wheel, and copies the same verified wheel into its container. The .NET seed restores exact NuGet locks, publishes the server, and smokes the published DLL. Both are architecture seeds, not production acceptance.

## Adoption and migration evidence

1. Read `contracts/rule-catalog.yaml`, the atomic child-control catalog, compatibility matrix, evidence profiles, and selected skill manifest.
2. Create one assessment per skill from `contracts/adoption-assessment.yaml.template`, bound to the exact SHA; use the assessment bundle/index for multi-skill migrations.
3. Record maturity, deployment profiles, capabilities, SDK profile, protocol revisions, and transports; let machine applicability determine required rules and child controls.
4. Bind every passed claim to executable result data and exact test-case identity. A badge, screenshot, commit message, located command, or handwritten `passed` is not evidence.
5. Local structural evidence is diagnostic only. L2 requires provider-backed exact-SHA evidence; L3/L4 and public, multi-tenant, or sensitive deployments require the independent-release profile.
6. Provider adapters are not the provider-neutral evidence model. The GitHub.com adapter is one reference implementation, not a portability requirement.
7. Run local diagnostics with `contracts/validate_adoption.py`, then use the authoritative external verifier with read-only provider credentials. Candidate code cannot approve itself.
8. Require independent review bound to the exact SHA whenever the evidence profile demands it; author, committer, evidence producer, and independent reviewer must remain appropriately separated.

## Finding triage

Treat bot/scanner findings as inputs: confirm the actual SDK/version/call path, reproduce the violated contract, classify the issue, reject framework-incompatible mechanical fixes, and add a regression that fails before the correction and passes after it.

## Constraints

- Never infer an SDK profile from a similarly named class, use private SDK registries as stable contracts, or advertise a transport implemented by a partial custom JSON-RPC bridge.
- Never default missing capability metadata to read-only, claim concurrency without enforcement/tests, log to stdout on stdio, or build shell commands from agent-controlled text.
- Never validate filesystem containment with string prefixes, expose browser/container/SSH/raw-device boundaries as ordinary low-risk adapters, or swallow cancellation/disconnect semantics.
- Never create untracked fire-and-forget work, treat annotations/DTOs as runtime authorization, or claim a generated server works before an official client lists and invokes the exact installed/published artifact.
- Never claim migration completion or SDK parity without authoritative exact-SHA evidence, applicable atomic controls, and platform-specific lifecycle/DI/concurrency mapping.

The assessed revision MUST NOT supply the authoritative verifier, claim catalog, or acceptance workflow used to approve itself; candidate-local validation remains diagnostic and final acceptance uses immutable external authority coordinates.
