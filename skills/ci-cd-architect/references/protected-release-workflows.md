---
afds_schema_version: 2
description: Safe construction and distribution of protected release workflows and trusted workflow auditors.
doc_id: reference.protected-release-workflows
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification:
  kind: command
  value: Render the bundled publish template, audit it with the protected-release profile, and perform a disposable-registry release using a closed image archive.
---

# Protected release workflows

## Build and publish separation

A build job operates with read-only repository permissions. It resolves an existing tag or full commit SHA, verifies trusted-branch ancestry, executes repository-controlled tests, builds once, smoke-tests that exact image, and exports the image plus a checksum and manifest. It has no package, contents, OIDC, or attestation write permission.

The publish job receives only the bounded archive and manifest from the build job. It does not check out source, run package scripts, invoke a Dockerfile, or execute the image. Before registry login it verifies the archive checksum, expected source SHA, image reference, and OCI labels. It then pushes an explicit allowlist of tags.

## Preview sources

An arbitrary branch, fork, or user-selected ref is untrusted executable input. Preview publication therefore uses an unprivileged build followed by a publisher that treats the exported OCI archive as data. The publisher may copy or tag the verified archive but must not run it.

A stable release accepts only an existing SemVer tag or full SHA that is reachable from the configured trusted default branch. A moving branch name is never sufficient release identity.

## Package releases

NuGet, Python package, and analogous releases use the same boundary. The validation job builds and tests the exact package set, validates package identities and versions, writes a package allowlist plus checksums, and uploads one closed artifact. The publish job downloads that artifact, verifies its manifest and checksums, and publishes only the named package files. It does not restore, build, test, pack, or execute candidate source.

A GitHub Release references the validated source SHA and tag from the producer outputs. The publishing job does not reconstruct identity from its own `github.sha` or from a mutable branch.

## Permission profile

The workflow declares `# ai-skills-policy-profile: protected-release`. Top-level permissions remain read-only. A job-level write scope is allowed only when the job has a protected environment and depends on prior validation. Do not grant a scope merely because a template mentions it; remove unused `contents`, `packages`, `id-token`, `attestations`, or `security-events` writes.

## Trusted auditor distribution

Acceptance uses a verifier outside the assessed revision. The preferred channel is the rendered `templates/trusted-workflow-audit.yml.template` in a separately governed repository, referenced by full commit SHA. A signed wheel or OCI image pinned by digest is an acceptable equivalent when it carries the same versioned policy and verification behavior.

Never use `curl` from a mutable branch, execute an auditor copied from the assessed pull request as approval authority, or let the candidate rewrite the claim catalog that evaluates it.

## Verification

Render the template with concrete values and run:

```bash
python skills/ci-cd-architect/tools/check_github_actions_policy.py \
  --profile protected-release \
  --workflow path/to/rendered-publish.yml \
  path/to/repository
```

Then use a disposable registry namespace to prove archive checksum validation, explicit tag pushes, digest capture, source-label equality, and rejection of an altered archive.


## Protected publisher execution boundary

An authority-bearing protected publisher promotes an already-tested immutable artifact. It MUST NOT check out or clone candidate source, rebuild/package candidate code, load/import candidate images, or execute candidate code/images under publication authority. Those operations belong in the unprivileged validation/build stage.

The trusted workflow-policy auditor rejects high-signal command classes such as repository checkout/clone, container build/load/import/run, and common language package-build commands in protected write jobs. Shell line continuations are normalized before matching so splitting a prohibited command across physical lines does not bypass the boundary. Known build actions are rejected when they run under publication authority, while the same actions remain valid in unprivileged validation.

A protected write job that delegates to a job-level reusable workflow is rejected unless a future compatibility profile provides independent semantic inspection of that workflow. Pinning a reusable workflow by SHA proves source immutability, not that it avoids candidate materialization or execution. Registry-native exact-digest copy/promote/inspect operations remain valid. Dynamic shell indirection and unknown third-party action semantics still require review of the protected publication trust boundary.
