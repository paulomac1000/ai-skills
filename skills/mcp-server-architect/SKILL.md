---
name: mcp-server-architect
description: Design, generate, implement, review, and harden complete MCP servers across Python and .NET with explicit contracts, lifecycle ownership, trust boundaries, and production verification.
---

# MCP server architect

Use this skill for new MCP servers, transport migrations, SDK upgrades, security reviews, production-readiness audits, and recovery of architectural knowledge from existing servers.

## Workflow

1. Define consumer outcomes, cross-tool workflows, stable IDs, capability boundaries, risk, authorization, and response contracts before choosing an SDK.
2. For an existing server, run the read-only inspector and executable planner first: `inspect_existing_project.py` discovers facts/unknowns; `plan_existing_project.py` projects only applicable rules, child controls, evidence classes, and unresolved human decisions. Do not fabricate a complete migration assessment from source assumptions.
3. If the repository integrates an external, legacy, or poorly documented backend, observe and validate `upstream-contract.yaml` before refactoring its adapter. Then resolve distribution name, exact SDK version, import namespace, registration/enumeration APIs, auth context, transport startup API, and protocol revisions from locks and production imports.
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
18. For an existing public contract, capture baseline and candidate snapshots through an official-client probe and run `compare_mcp_contracts.py --check`; removed capabilities, new required inputs, changed schemas, target selection, pagination, retry, or auth semantics require a major bump.
19. Progress through discovered, planned, implemented, locally verified, provider verified, and accepted states. Build the full provider-backed assessment only when implementation and local exact-artifact verification are stable enough for formal adoption.
20. Complete applicability, compatibility, behavior, waiver, rollback, residual-risk, SDK-profile, protocol-revision, transport, and exact-artifact evidence before claiming adoption.

Read `STANDARD.md`, `references/testing-strategy.md`, and the SDK profile selected by package identity first. Add `references/upstream-contract-discovery.md` when an external upstream is present, and load other references only when the inspector or an applicable rule routes to them. Python consumers do not need the .NET migration simulation, and .NET consumers do not need the Python simulation; both simulations remain mandatory for ai-skills self-validation.

## SDK and generated-baseline evidence

Record stable profile entries such as `sdk:python-official-mcp@2.0.0`, `sdk:python-fastmcp@<exact-version>`, `protocol:2026-07-28`, and the advertised transport. `upstream-supported`, `repository-tested`, and `project-claimed` are distinct states; only exact-package and exact-artifact official-client evidence advances a claim beyond upstream support. A declared SDK range wider than an exact tested pin requires compatibility lanes covering that range; the adoption planner reports the unresolved claim instead of treating it as proven.

Both generators are atomic and non-overwriting. The Python seed emits only the official `mcp` profile, uses hash-locked dependency graphs, builds one wheel, installs/smokes that exact wheel, and copies the same verified wheel into its container. The .NET seed restores exact NuGet locks, publishes the server, and smokes the published DLL. Both are architecture seeds, not production acceptance.

## Adoption and migration evidence

1. Start with read-only discovery and the executable adoption plan; `unknown` and `needs human decision` are valid migration states and are not waivers.
2. Read `contracts/rule-catalog.yaml`, atomic child controls, compatibility matrix, evidence profiles, and the selected skill manifest only after discovery identifies the relevant profile.
3. Create the full assessment from `contracts/adoption-assessment.yaml.template` when the implementation is ready for formal local/provider verification, bind it to the exact SHA, and let machine applicability determine required rules and child controls.
4. Bind every passed claim to executable result data and exact test-case identity. A badge, screenshot, commit message, located command, or handwritten `passed` is not evidence.
5. Local structural evidence is diagnostic only. L2 requires provider-backed exact-SHA evidence; L3/L4 and public, multi-tenant, or sensitive deployments require the independent-release profile.
6. Provider adapters are not the provider-neutral evidence model. The GitHub.com adapter is one reference implementation, not a portability requirement.
7. Run local diagnostics with `contracts/validate_adoption.py`, then use the authoritative external verifier with read-only provider credentials. Candidate code cannot approve itself.
8. Record real-environment checks as deployment observations bound to exact source/artifact identity. Unavailable live prerequisites are `not-executed`, never synthetic passes.
9. Require independent review bound to the exact SHA whenever the evidence profile demands it; author, committer, evidence producer, and independent reviewer must remain appropriately separated.

## Finding triage

Treat bot/scanner findings as inputs: confirm the actual SDK/version/call path, reproduce the violated contract, classify the issue, reject framework-incompatible mechanical fixes, and add a regression that fails before the correction and passes after it.

## Constraints

- Never infer an SDK profile from a similarly named class, use private SDK registries as stable contracts, or advertise a transport implemented by a partial custom JSON-RPC bridge.
- Never default missing capability metadata to read-only, claim concurrency without enforcement/tests, log to stdout on stdio, or build shell commands from agent-controlled text.
- Never validate filesystem containment with string prefixes, expose browser/container/SSH/raw-device boundaries as ordinary low-risk adapters, or swallow cancellation/disconnect semantics.
- Never create untracked fire-and-forget work, treat annotations/DTOs as runtime authorization, or claim a generated server works before an official client lists and invokes the exact installed/published artifact.
- Never claim migration completion or SDK parity without authoritative exact-SHA evidence, applicable atomic controls, and platform-specific lifecycle/DI/concurrency mapping.

The assessed revision MUST NOT supply the authoritative verifier, claim catalog, or acceptance workflow used to approve itself; candidate-local validation remains diagnostic and final acceptance uses immutable external authority coordinates.
