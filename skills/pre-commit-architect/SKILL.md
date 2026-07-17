---
name: pre-commit-architect
description: Design, audit, or repair fast local Git checks that reuse CI configuration, provide actionable feedback, and avoid credentials or unreliable network dependencies.
---

# Pre-commit architect

Read `STANDARD.md` before generating or changing hooks.

## Workflow

1. Inspect CI, manifests, existing commands, repository size, and measured durations.
2. Classify checks by cost, determinism, credentials, network dependency, and scope.
3. Put cheap deterministic checks in pre-commit.
4. Put slower repository-wide checks in pre-push or an explicit local CI command.
5. Keep credentialed, environment-specific, and deployment checks in CI unless a reliable sandbox exists.
6. Reuse the same formatter, linter, compiler, schema, and test configuration as CI.
7. Keep dependency versions in executable configuration and update them through automation.
8. Test a clean pass and representative failures.

## Constraints

- Do not make every commit run the entire CI pipeline.
- Do not require production credentials or network access in pre-commit.
- Do not maintain separate local and CI rule sets that can drift.
- Do not remove the framework's emergency bypass, but never let bypass weaken CI.
