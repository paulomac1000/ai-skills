---
description: Binds every credential-bearing auditor, collector, verifier, and vendored validator to one immutable executable-source lock.
doc_id: reference.cicd.trusted-executable-sources
type: reference
status: active
rigor: normative
owners: [CI/CD maintainers, Security maintainers]
verification: Validate trusted-executable-sources.lock.yaml against both the consumer tree and the immutable authority checkout before granting provider credentials.
---
# Trusted executable sources

## One trust inventory

A consumer MUST NOT maintain independent hardcoded SHAs for auditors, evidence collectors, provider correlators, or vendored validators outside the canonical trusted executable source lock. Every executable that receives provider credentials or contributes provider-backed acceptance evidence is a trusted source, regardless of whether its name contains `auditor`, `collector`, `validator`, or `reporter`.

The lock records the external repository, full revision, role, credential access, authority path, optional vendored path, and SHA-256 of every executable file. A local vendored copy must match the same digest as the authority file. Renaming a trusted component does not change this requirement.

## Candidate and trusted jobs

Candidate jobs receive no provider credential used to approve their own result. They execute tests and emit local artifacts. A trusted job checks out the source revision recorded by the lock, validates its file digests, then receives only the read-only provider credential required to correlate run, job, artifact, review, and exact-SHA metadata.

Run `python contracts/validate_trusted_executable_sources.py trusted-executable-sources.lock.yaml --repository-root . --authority-root SOURCE_ID=/immutable/checkout --require-authority` before granting provider credentials. The authority checkout itself must be at the revision recorded in the lock; branch names and mutable tags are invalid inputs to that bootstrap.

## Local validation entrypoints

A vendored documentation validator and its authority copy must not evolve independently. Consumers should expose one canonical local command such as `make docs-check`; pre-commit and CI call that command instead of maintaining separate file lists or validator options. `check_consumer_trust_hygiene.py` detects duplicated AFDS entrypoints, unmanaged trusted revision pins, and security scanners that silently turn into local no-ops.

Security hooks fail closed. If Semgrep or another declared scanner is unavailable, the local hook either installs it through a managed pinned environment or fails; printing that CI remains authoritative is not a substitute for the requested local gate.
