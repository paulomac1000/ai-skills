---
description: Machine-readable policy for MCP protocol revisions, SDK versions, negotiation, and cross-language compatibility claims.
doc_id: reference.mcp-protocol-sdk-compatibility
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Compare `manifest.yaml` protocol profiles with committed Python locks, .NET package pins, official-client evidence, and the protocol revision negotiated in generated-server tests.
---

# MCP protocol and SDK compatibility

## Separate compatibility axes

Protocol revision, SDK package version, language runtime, transport, and implementation profile are independent axes. Passing the Python lane does not prove the .NET lane supports the same protocol revision, and a package version alone is not evidence of negotiated protocol behavior.

The skill manifest records one `default_revision` for new design work and a separate SDK profile for every generated language. Each profile names exact tested package versions, protocol revisions actually exercised by official clients, and whether current-revision support is claimed.

## Python profile

The Python generator uses the reviewed `mcp` 2.x stable lane from the committed hashed locks. Its declared protocol revisions are accepted only when the generated server completes initialization, capability listing, representative reads, denied writes, protocol-native failures, and exact-artifact smoke tests under an official client.

Dependency ranges in generated `pyproject.toml` are not the acceptance identity. The committed lock and the exact installed wheel define the tested SDK version.

## .NET profile

The .NET generator remains on the stable `ModelContextProtocol` and `ModelContextProtocol.AspNetCore` package lane. Until the repository runs revision-specific negotiation and official-client evidence for that stable SDK, the manifest records current protocol support as `not-claimed` rather than inferring it from API shape or another language's results.

A move to a prerelease or new major SDK is a reviewed compatibility change. Package restore, compilation, unit tests, and HTTP startup are necessary but do not by themselves establish support for a protocol revision.

## Transport policy sources

Transport decisions identify their authority explicitly:

- the protocol specification defines interoperable transport behavior and compatibility allowances;
- an SDK profile records what a concrete package version implements and what the repository tested;
- `ai-skills` policy forbids the deprecated two-endpoint HTTP plus SSE transport for every new server;
- a named legacy-client adapter is a controlled project exception with an owner, allowlist, parity tests, and removal deadline.

The project-policy prohibition is intentionally stricter than the protocol compatibility allowance. It does not redefine optional `text/event-stream` responses inside modern Streamable HTTP, and it must not be presented as a protocol-level removal claim.

## Negotiation and fallback

Servers negotiate explicitly and expose only features supported by both the selected SDK profile and application implementation. Unknown revisions or features fail with a controlled compatibility response. A compatibility adapter does not silently rewrite semantics, widen authorization, or advertise a capability that lacks profile-specific tests.

The default protocol revision guides new implementation work. It does not retroactively convert an untested SDK profile into a supported one.

## Verification

For every language profile:

1. compare manifest package versions with committed locks or central package pins;
2. generate a fresh server and install or restore the exact dependency graph;
3. record the protocol revision negotiated by an official client;
4. execute listing, representative read, failure, and write-boundary scenarios;
5. smoke the exact wheel, binary, package, or image that would be published;
6. update `tested_revisions` only from that evidence.
