---
afds_schema_version: 2
description: Binds credential-bearing auditors, collectors, verifier entrypoints, and vendored validators to one immutable executable-source declaration while preserving an external orchestration root of trust.
doc_id: reference.cicd.trusted-executable-sources
type: reference
status: active
rigor: normative
owners: [CI/CD maintainers, Security maintainers]
verification:
  kind: command
  value: Validate trusted-executable-sources.lock.yaml against the immutable authority checkout and externally supplied authority coordinates before granting provider-backed acceptance status.
---
# Trusted executable sources

## One trust inventory

A consumer MUST NOT maintain independent hardcoded SHAs for auditors, evidence collectors, provider correlators, or vendored validators outside the canonical trusted executable source lock. Every executable entrypoint that receives provider credentials or contributes provider-backed acceptance evidence is a trusted source, regardless of whether its name contains `auditor`, `collector`, `validator`, or `reporter`.

The lock records the external repository, full revision, role, credential access, authority path, optional vendored path, and SHA-256 of each inventoried executable file. A local vendored copy must match the same digest as the authority file. Renaming a trusted component does not change this requirement.

The lock is a candidate declaration, not a bootstrap trust anchor. A candidate can edit its own `repository`, `revision`, and file list, so provider-backed orchestration MUST supply the expected authority repository and full SHA independently and compare the lock to those coordinates. Use `contracts/validate_external_trust_lock.py` for that equality check. A candidate-owned workflow that merely reads its own lock and checks out that revision remains structural evidence.

Do not inventory every imported helper mechanically. The externally pinned authority SHA binds the full checkout; the lock inventories the executable entrypoints that cross the provider-credential or acceptance-evidence boundary. See `provider-trust-bootstrap.md` for the decision matrix.

## Candidate and trusted jobs

Candidate jobs receive no provider credential used to approve their own result. They execute tests and emit local artifacts. A provider-backed trusted job is itself selected by immutable external orchestration, checks out the authority revision selected outside the candidate, proves the candidate lock declares the same authority, validates the inventoried file digests, and only then receives the read-only provider credential required to correlate run, job, artifact, review, and exact-SHA metadata.

For structural diagnostics, run `python contracts/validate_trusted_executable_sources.py trusted-executable-sources.lock.yaml --repository-root . --authority-root SOURCE_ID=/immutable/checkout --require-authority`. For provider-backed acceptance, run `contracts/validate_external_trust_lock.py` with `--expected-repository` and `--expected-revision` values supplied by the trusted orchestration layer, not by candidate files.

Generate or refresh digest entries from the exact authority checkout with `python skills/ci-cd-architect/tools/generate_trusted_executable_sources.py --authority-root ... --repository OWNER/REPO --revision <full-sha> --authority-path ...`. The generator verifies origin, exact HEAD, tracked files, clean listed paths, and digests before emitting YAML. Do not hash bytes from a mutable branch view.

## Local validation entrypoints

A vendored documentation validator and its authority copy must not evolve independently. Consumers should expose one canonical local command such as `make docs-check`; pre-commit and CI call that command instead of maintaining separate file lists or validator options. `check_consumer_trust_hygiene.py` detects duplicated AFDS entrypoints, unmanaged trusted revision pins, and security scanners that silently turn into local no-ops.

When trust hygiene reports an unmanaged immutable pin, choose the remediation by trust plane: a candidate-owned workflow may move the pin into the canonical lock only for structural/diagnostic provenance, while provider-backed approval must pin the reusable acceptance workflow outside the candidate and verify candidate-lock equality against that external authority. Moving a SHA into a candidate-owned lock never upgrades evidence to provider-backed by itself.

## Verification

Validate the lock structurally, validate it against the immutable authority checkout, and for provider-backed acceptance validate equality with authority coordinates supplied outside the candidate. Verify that every inventoried authority path is tracked at the authority revision and that every vendored copy matches the authority digest. Treat missing authority, dirty authority bytes, an untracked authority path, or candidate-selected provider authority as a hard failure.
