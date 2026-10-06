---
description: Exact authority, one-shot reservation, and reconciliation contract for publishing or promoting an already-proven artifact.
doc_id: reference.cicd-artifact-publication-lease
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Exercise exact artifact/destination admission, authority provenance, one-shot reservation, ambiguous publication reconciliation, immutable conflicts, mutable-channel lineage, receipt projection, and provider-neutral package/OCI/release-asset cases.
---

# Artifact publication lease

Use this profile when an autonomous publisher may place an already-built and already-validated artifact into a governed package, registry, release-asset, or distribution namespace. Build/test authority, repository write authority, deployment authority, and the mere presence of registry credentials are not publication authority. Candidate code, artifact producers, model output, and ordinary workers cannot mint, widen, refresh, or delegate an ArtifactPublicationLease.

## Exact authority envelope

An ArtifactPublicationLease is an authority-owned, bounded, one-shot grant. It binds at least:

- lease and authority-principal identity;
- exact prepared artifact reference and digest, with media/package type and source-location reference when relevant;
- exact provider/registry, namespace, package/repository, version, and explicit tags/channels;
- one bounded publication action;
- publication-policy revision and required evidence-set digest;
- execution generation, issue/expiry, lifecycle state, and the durable operation that consumes it.

`active`, `used`, `revoked`, and `expired` are authority states, not model labels. Destination credentials stay behind the trusted publisher/adapter; they are not carried by the lease or copied into the build worker. A lease for one artifact/version/tag set grants no authority over another digest, package, namespace, version, or channel.

## Exact-artifact admission

Immediately before reserving a publication operation, re-read trusted authority and destination state and compare them with the lease:

```text
acting principal + execution generation
publication policy + exact evidence-set identity/currentness
prepared artifact ref + digest
provider/registry + namespace/package + version + tags/channels
authoritative destination state + provider publication controls
```

Only an exact `AVAILABLE` result may dispatch a mutation. `ALREADY_PRESENT_SAME_ARTIFACT` may complete without another write only when current provider/policy explicitly admits same-artifact convergence, after authoritative read-back and one-shot reservation. `ALREADY_PRESENT_DIFFERENT_ARTIFACT` is a hard conflict. Unknown destination state, stale policy/evidence, lost authority, artifact mismatch, destination-scope widening, or unavailable provider controls fail closed.

Immediately before dispatch the publisher binds the artifact it actually opened/read to the reserved `PublicationArtifact`; a different ref or digest is rejected before provider mutation. The publisher consumes the prepared artifact identity. It does not check out, rebuild, repack, load/import, or execute candidate source under publication authority. Existing protected-release auditing remains the canonical mechanical owner of that publisher boundary; the lease adds exact autonomous authority rather than replacing those controls.

## Version and channel reservation

Immutable versions and release identities are resolved before mutation. A failed publication never invents a new version or widens the allowed namespace merely to continue.

Mutable tags/channels such as `latest`, `stable`, or release channels are explicit lease scope. Their authoritative before-state is captured in the durable operation and their after-state is recorded in the receipt. Missing or partial channel observation is `DESTINATION_UNKNOWN`, not permission to move the channel.

## One-shot reservation and ambiguous outcomes

Publication is a stateful external effect. Durable operation identity is reserved before the first provider byte is dispatched, and reservation consumes the lease. A timeout, transport loss, provider conflict, process restart, or ambiguous acknowledgement resumes/reconciles the same operation; it does not reactivate the lease or authorize blind replay.

After any ambiguous/rejected acknowledgement, read the exact destination:

```text
same exact artifact (+ requested channel state)
  -> reconciled success
different artifact at immutable identity
  -> conflict, never overwrite/reinterpret
artifact not present
  -> operation settles not-published; any later dispatch needs fresh policy-owned authority
unknown/partial destination state
  -> reconciliation-required
```

A provider conflict can be the observable consequence of an earlier successful publication whose acknowledgement was lost. Transport status therefore never substitutes for authoritative destination read-back.

## Publication receipt and terminal composition

A successful or same-artifact-reconciled operation emits a bounded `artifact_publication` receipt carrying:

- exact artifact ref/digest;
- exact destination identity and provider immutable identity when available;
- explicit tags/channels plus before/after digest state;
- durable operation and lease references;
- publication-policy revision and exact evidence-set digest;
- outcome, observation time, and bounded evidence references.

This is the publication-authority projection point for the broader execution-evidence owner; it does not redefine global receipt correlation or evidence freshness.

A delivery policy may use a proven exact publication receipt to satisfy `terminalBoundary=artifact_accepted` without requiring runtime deployment. That policy decision remains owned by the autonomous-delivery policy contract. A later DeploymentLease may consume a projected exact published-artifact reference, but that reference carries no publication lease, publication principal, or permission to rebuild/republish the artifact.

## Supply-chain evidence

When policy requires SBOM, provenance, signature, or attestation, the lease references the required evidence-set identity instead of redefining those formats. The trusted publisher must preserve the attested artifact identity; publication of rebuilt/substituted bytes fails exact-artifact admission or reconciliation.

## Provider neutrality

The contract describes provider/registry, namespace/package, version/channel, prepared artifact identity, and authoritative observations rather than one provider API. PyPI/NuGet/npm package publication, OCI digest promotion, GitHub Release assets, and equivalent immutable artifact channels may adapt native IDs without becoming the generic wire model.

## Security boundary

Do not place registry credentials, tokens, signing secrets, cookies, or raw provider payloads in the lease, operation, or receipt. Untrusted candidate/model content cannot supply authority principal, current policy/evidence verdicts, provider-control decisions, or authoritative destination observations. Large provider diagnostics remain behind governed evidence references.
