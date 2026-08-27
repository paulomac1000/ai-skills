---
afds_schema_version: 2
description: Resolved profile for generated servers using the official .NET Model Context Protocol SDK.
doc_id: reference.dotnet-mcp-sdk
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification:
  kind: ci-job
  value: Generate the canonical .NET server and run locked restore, build, publish, and official-client stdio and Streamable HTTP smoke tests on the exact generated artifact.
---

# Official .NET MCP SDK profile

Use this profile only when package ownership resolves to the official `ModelContextProtocol` distribution and production imports resolve to the `ModelContextProtocol` namespace. A similarly named API or wrapper is not sufficient evidence.

## Baseline

The generated baseline pins `ModelContextProtocol` and `ModelContextProtocol.AspNetCore` to **1.4.1** and restores their committed NuGet lock files in locked mode. The repository manifest is the source of truth for profile status.

`2.1.0` is an upstream stable candidate, not a generated baseline. Do not move the generator to that line until exact locks are regenerated and restore, build, publish, official-client, transport, and protocol-revision evidence pass together.

## Protocol evidence

The profile currently records no repository-tested protocol revision and `current_revision_support: not-claimed`. Package availability or successful compilation does not establish protocol conformance. Add a revision only after the exact published artifact passes the required client negotiation and behavior tests for that revision.

## Generated output

Generated projects carry machine-readable `mcp-profile.json` metadata with the resolved profile identifier, exact SDK version, tested revision set, and evidence status. The metadata must remain consistent with the pinned package versions and locks; it is descriptive evidence context, not a substitute for the artifact smoke tests.

## Acceptance

A production claim requires, at minimum, locked restore, build, publish, public-client stdio and Streamable HTTP tests, authorization and failure-path checks, lifecycle/cancellation coverage, and smoke of the exact published DLL. Re-run the same evidence after any SDK or protocol change.
