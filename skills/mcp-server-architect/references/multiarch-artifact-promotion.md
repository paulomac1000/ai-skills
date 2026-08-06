---
description: Defines build-once, test, composition, provenance, and unchanged promotion for multi-platform OCI images.
doc_id: reference.mcp.multiarch-artifact-promotion
type: reference
status: active
rigor: normative
owners:
  - MCP maintainers
  - Release engineering
verification:
  method: manual-review
  command: python skills/afds-doc-writer/validate.py --repository-root . skills/mcp-server-architect/references/multiarch-artifact-promotion.md
---
# Multi-architecture artifact promotion

## Identity model

For a multi-platform OCI release, “the same artifact” means the complete immutable graph:

```text
source revision
  -> platform build record
  -> platform manifest digest for linux/amd64
  -> platform manifest digest for linux/arm64
  -> OCI index or manifest-list digest
  -> release tag pointing to that exact index digest
```

The release identity is the OCI index digest. Each declared platform digest is an independently testable child identity. Provenance MUST bind the full source revision, build inputs, child digests, and final index digest.

## Build and test sequence

1. Build each declared platform exactly once into a closed OCI layout or registry staging namespace.
2. Record the platform, full source revision, configuration digest, image manifest digest, and layer digests.
3. Run the declared artifact smoke tests against each platform digest. Native execution is preferred. Emulation is acceptable only when the claim records the emulator and does not imply native-host coverage.
4. Reject any platform that was not tested or whose test result cannot be bound to its exact digest.
5. Compose the OCI index from the already tested platform digests without rebuilding a platform image.
6. Inspect the resulting index and verify that its platform descriptors exactly match the approved set.
7. Promote or retag the exact index digest. Do not rebuild, mutate labels, add layers, or replace a child digest in the publisher.

## Accepted build mechanisms

The standard defines the result, not one package manager or Dockerfile layout. Both approaches are valid when identity is preserved:

- a previously built wheel, package, binary, or OCI layout copied into a later image stage;
- a hermetic multi-stage build whose resulting image digest is tested and then promoted unchanged.

A build performed again in the release job is a different artifact even when source and Dockerfile are unchanged.

## Required promotion record

The record MUST contain:

- full source SHA;
- builder identity and immutable builder revision;
- build arguments and dependency-lock digests;
- one entry per platform with platform, child manifest digest, test command, result, and evidence digest;
- final index digest;
- descriptor comparison result;
- promotion source and destination references;
- proof that destination resolves to the same index digest.

A short SHA tag MAY be a convenience alias but MUST NOT be the artifact identity.

## Failure handling

Do not compose or promote a partial index unless the release contract explicitly declares a reduced platform set and obtains a new approval for that changed claim. A failed platform cannot be silently omitted. Rebuilding one platform invalidates the previous index and requires retesting that child plus recomposition and reapproval of the new index digest.
