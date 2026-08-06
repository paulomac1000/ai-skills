---
description: Machine-readable policy for MCP protocol revisions, SDK versions, package profiles, negotiation, and cross-language compatibility claims.
doc_id: reference.mcp-protocol-sdk-compatibility
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: ci-job
  value: Compare manifest SDK profiles with committed locks and package pins, then bind each repository-tested protocol revision to official-client evidence against the exact installed and container artifact.
---

# MCP protocol and SDK compatibility

## Separate compatibility axes

Protocol revision, SDK distribution, SDK package version, language runtime, transport, implementation profile, and generated artifact are independent axes. Passing one language or package lane does not prove another supports the same protocol revision. A package release alone is not evidence of negotiated protocol behavior in this repository.

The skill manifest records one `default_revision` for new design work and one exact SDK profile per supported package family. Each profile separates:

- package identity and import namespace;
- generated versus assessment-only support;
- verified baseline versions used by committed locks or package pins;
- newer upstream stable candidates awaiting repository evidence;
- revisions upstream says the package supports;
- revisions actually exercised by this repository;
- current-revision support claimed by the profile.

`upstream-supported`, `repository-tested`, and `project-claimed` are different states. They must not be copied into one another.

## Python official SDK profile

The official Python generator targets distribution `mcp` and official `mcp` imports. It uses the reviewed 2.x stable baseline from committed hashed locks. Its dependency range in generated `pyproject.toml` is not the acceptance identity; the selected platform lock, exact installed distribution, built wheel, and container define the tested package and artifact.

A protocol revision moves into `repository_tested_revisions` only after an official client exercises the exact installed and container artifacts. For revision 2026-07-28, the lane must include modern discovery/direct-request behavior and every new request metadata/header requirement applicable to the SDK. Compatibility with an earlier revision is a separate forced test, not an inference from fallback.

Read `python-official-mcp-sdk.md` for lifecycle, principal, transport, manifest, and exact-artifact requirements.

## Python FastMCP package profile

The independently distributed `fastmcp` package is a separate profile. Similar class names do not make it interchangeable with the official SDK. Its provider, middleware, authentication context, component APIs, mounted-state behavior, and transport lifecycle require package-specific evidence.

The canonical Python generator does not emit this package profile. Existing FastMCP projects are assessed through `python-fastmcp-package.md`. Mixed or unresolved package ownership is `unsupported-sdk-profile` until a reviewed profile and exact tests exist.

## .NET official SDK profile

The generated .NET baseline remains pinned to `ModelContextProtocol` and `ModelContextProtocol.AspNetCore` 1.4.1 because those versions are represented by committed exact NuGet locks in this repository.

The official upstream now has a newer stable 2.1.0 line. That makes 2.1.0 an upstream stable candidate, not a repository-verified baseline. The generator must not change its central package pins until the same change includes:

1. regenerated exact lock files for server and smoke projects;
2. namespace-aware verification that direct package metadata matches the requested IDs and versions;
3. restore, build, warnings-as-errors, and publish of the generated solution;
4. official-client stdio and Streamable HTTP execution of the published artifact;
5. revision-specific negotiation and feature evidence for 2026-07-28 and each earlier revision claimed;
6. exact container smoke where the profile publishes a container;
7. a reviewed compatibility report covering public API, auth filters, request principal, sessions/state, tasks, structured output, error signaling, trimming, and shutdown.

Do not hand-edit lock files to make the version appear current. Do not infer 2026-07-28 support from Python or from upstream release status.

## Transport policy sources

Transport decisions identify their authority explicitly:

- the protocol specification defines interoperable transport behavior and compatibility allowances;
- an SDK profile records what a concrete package version implements and what the repository tested;
- `ai-skills` policy forbids the deprecated two-endpoint HTTP plus SSE transport for every new server;
- a named legacy-client adapter is a controlled project exception with an owner, allowlist, parity tests, and removal deadline.

The project-policy prohibition is intentionally stricter than the protocol compatibility allowance. It does not redefine optional `text/event-stream` responses inside modern Streamable HTTP, and it must not be presented as a protocol-level removal claim.

## Negotiation and fallback

Servers negotiate explicitly and expose only features supported by both the selected SDK profile and the application implementation. Unknown revisions or features fail with a controlled compatibility response. A compatibility adapter does not silently rewrite semantics, widen authorization, or advertise a capability that lacks profile-specific tests.

The default protocol revision guides new implementation work. It does not retroactively convert an untested SDK profile into a supported one. Package support does not become repository evidence until the exact package and artifact lane records it.

## Assessment profile identity

Record stable profile strings in `extensions.mcp.profiles`, for example:

```text
sdk:python-official-mcp@2.0.0
sdk:python-fastmcp@3.4.6
sdk:dotnet-official-mcp@1.4.1
protocol:2026-07-28
transport:stdio
transport:streamable-http
```

Use exactly one owning SDK profile per implementation adapter. Mixed implementations name each adapter and include parity evidence; an unresolved implementation records `unsupported-sdk-profile` and cannot receive unwaived L2+ approval.

## Verification

For every language and SDK profile:

1. compare manifest package versions with committed locks or central package pins;
2. generate a fresh server and install or restore the exact dependency graph;
3. verify public imports and runtime package ownership;
4. record the protocol revision negotiated by an official client;
5. execute listing, representative read, failure, authorization, cancellation, and write-boundary scenarios;
6. smoke the exact wheel, binary, package, OCI platform digest, or image that would be published;
7. update repository-tested revisions only from exact-SHA, exact-artifact evidence;
8. keep upstream candidate results isolated from the publishing verified-baseline lane until review accepts the migration.
