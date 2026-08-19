---
name: mcp-server-architect
description: Design, generate, implement, review, and harden complete MCP servers across Python and .NET with explicit contracts, lifecycle ownership, trust boundaries, and production verification.
---
# MCP server architect

Use this skill for new MCP servers, transport migrations, SDK upgrades, security reviews, production-readiness audits, and recovery of architecture from existing servers. Read `STANDARD.md` first; load only the references required by the resolved SDK/profile.

## Workflow

1. Define consumer outcomes, stable identifiers, tool boundaries, risk axes, authorization, response contracts, lifecycle ownership, deadlines, cancellation, retries, concurrency, and failure semantics before choosing an SDK.
2. For an existing server, create `migration-assessment.yaml` from `templates/migration-assessment.yaml.template`, bind it to the exact revision, and classify the applicable shared rules and atomic child controls before changing code.
3. Resolve the implementation profile from distribution/package name and exact version, production import namespace and owning distribution, registration/component APIs, middleware/auth-context APIs, transport startup API, and protocol revisions actually tested.
4. Route Python by package identity: official `mcp` -> `references/python-official-mcp-sdk.md`; independent `fastmcp` -> `references/python-fastmcp-package.md`; mixed or unresolved ownership -> `unsupported-sdk-profile`. Do not route by class-name similarity.
5. For a new server, generate rather than copy an old implementation: `python skills/mcp-server-architect/tools/generate_python_server.py <target> --package <package_name> --name "<Server Name>"` for the official Python SDK, or `python skills/mcp-server-architect/tools/generate_dotnet_server.py <target> --namespace <Root.Namespace> --name "<Server Name>"` for .NET.
6. Install/restore the generated project and run its official-client smoke before adding domain integrations. Separate domain operations from MCP registration, hosting, transports, artifacts, tasks, browser state, and privileged adapters.
7. Give every public capability a complete application-owned manifest. Distinguish supported catalog from active catalog and fail closed on unknown or incomplete metadata.
8. Use stdio or Streamable HTTP deliberately. New servers do not implement deprecated two-endpoint HTTP+SSE; a legacy adapter is exceptional, isolated, allowlisted, tested, disabled by default, and owned with a removal condition.
9. Bind principals, targets, approvals, resources, arguments, expiry, and side effects server-side. Revalidate target identity before I/O and after redirects/retries. Never use model-controlled confirmation as human approval.
10. Define idempotency, retry eligibility, ambiguous-outcome reconciliation, filesystem/shell confinement, request/session quotas, pagination, response bounds, provenance, confidentiality, partial-result semantics, logs, metrics, traces, and audit events.
11. Test domain, manifest, policy, authorization, registration, lifecycle, races, filesystem/artifacts/tasks/browser state, transports, and real-client behavior separately. Build and smoke the exact deployment artifact.
12. Complete applicability, compatibility, behavior changes, waivers, rollback, residual risk, exact artifacts, SDK profiles, protocol revisions, and advertised transports before claiming migration completion.

## SDK and artifact evidence

Use stable profile entries such as `sdk:python-official-mcp@2.0.0`, `protocol:2026-07-28`, `transport:stdio`, and `transport:streamable-http`. A FastMCP-package project uses `sdk:python-fastmcp@<exact-version>`; unsupported or mixed implementations never borrow another profile's evidence.

`upstream-supported`, `repository-tested`, and `project-claimed` are distinct. Release notes can establish only upstream support. Repository/project claims require exact-package, exact-artifact, official-client evidence.

The Python generator emits only the official `mcp` profile. Its baseline uses platform-specific hashed runtime/dev locks, `--require-hashes`, `pip check`, an exact wheel installed into isolation, real stdio/Streamable HTTP client smoke, and a container that copies and verifies that wheel rather than rebuilding source. The .NET seed restores exact NuGet locks, publishes the server, and smokes the published DLL. Generated output is an architecture seed, not production acceptance.

## Adoption and migration evidence

The shared adoption gate is `contracts/adoption-assessment.yaml.template` validated by `contracts/validate_adoption.py`, with parent rules in `contracts/rule-catalog.yaml`, atomic claims in `contracts/atomic-claim-catalog.yaml`, and provider-neutral evidence profiles in `contracts/evidence-profiles.yaml`.

Create one assessment per skill and use the assessment index for repository-wide migrations. Bind every passed claim to exact test-case/result identity and an immutable revision. A green job, badge, screenshot, commit message, located command, or hand-written `passed` value is not evidence.

`local-structural` is diagnostic. L2 acceptance requires reviewed hosted-provider exact-SHA evidence. L3/L4 and public, multi-tenant, or sensitive deployments require the applicable `independent-release` evidence profile. The candidate revision cannot approve itself: use immutable external authority and read-only provider credentials, and require an independent review bound to the exact SHA when the profile requires it.

For GitHub provider evidence, use GitHub.com identities/run data as the adapter to the provider-neutral contract; do not treat a provider-specific schema as the evidence model itself. See `references/migration-assessment.md`, `references/protocol-and-sdk-compatibility.md`, `references/capability-manifests-and-versioning.md`, `references/runtime-boundaries-and-artifacts.md`, and the exact resolved SDK profile.

## Finding triage

A scanner or bot suggestion is an input, not an automatic patch. Confirm the actual framework/version/call path, reproduce the behavior or violated contract, classify the finding, reject framework-incompatible mechanical fixes, and add a regression test for accepted defects.

## Constraints

- Do not put business logic only in decorated/attributed tool methods or use private SDK registries as stable contracts.
- Do not choose SDK/profile by class name, advertise partial custom JSON-RPC as a supported transport, or call legacy HTTP+SSE equivalent to Streamable HTTP.
- Do not default missing capability metadata to read-only or declare concurrency/idempotency/retry safety without runtime enforcement and tests.
- Do not use stdout for logs on stdio, build shell commands from agent text, or validate filesystem containment with string prefixes.
- Do not create unsupervised background work, expose privileged adapters as low risk, swallow cancellation, or turn expected disconnect into generic retryable failure.
- Do not treat annotations/DTOs as runtime validation, authorization, approval, or protocol error signaling.
- Do not claim generated-server success without a real MCP client invoking the exact installed/published artifact.
- Do not claim migration completion until the assessment and applicable atomic child controls validate against independently reviewed evidence.
- Do not claim SDK parity without mapping lifecycle, DI, identity, concurrency, and artifact invariants per platform.

The assessed revision MUST NOT supply the authoritative verifier, claim catalog, or acceptance workflow used to approve itself; candidate-local validation is diagnostic and final acceptance requires immutable external authority coordinates.
