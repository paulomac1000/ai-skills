---
name: ci-cd-architect
description: Audit, design, repair, or template CI/CD pipelines using repository evidence, least privilege, reproducible dependencies, tested artifacts, and local parity.
---

# CI/CD architect

Read `STANDARD.md` before changing workflows. Use bundled templates as starting points, not as substitutes for repository inspection.

## Workflow

1. Inspect languages, manifests, lock files, tests, artifacts, release targets, secrets, protected environments, and current workflows.
2. Reconstruct the real path from a source change to validation, artifact creation, publication, deployment, and rollback.
3. Identify trust boundaries for pull requests, forks, automation tokens, environments, registries, and external services.
4. Run fast deterministic checks before expensive, networked, or credentialed checks.
5. Build and test the same revision or immutable artifact that will be released.
6. Minimize permissions per job and prevent untrusted code from reaching secrets.
7. Pin third-party actions to immutable commits and let dependency automation propose updates.
8. Add concurrency control, timeouts, provenance, environment protection, and recovery where relevant.
9. Reproduce deterministic checks locally and report anything that requires unavailable infrastructure.
10. Validate the final workflow syntax and exercise representative success and failure paths.

## Constraints

- Do not copy a workflow before inspecting the target repository.
- Do not publish an artifact different from the one tested.
- Do not expose credentials to forked or otherwise untrusted code.
- Do not use mutable third-party action tags in protected workflows.
- Do not encode current dependency versions in prose or a hand-maintained matrix.
- Do not claim a pipeline works when only static YAML inspection was possible.
