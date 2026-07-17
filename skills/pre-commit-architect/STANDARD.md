---
description: Normative rules for reliable local Git checks with fast feedback and CI parity.
doc_id: reference.precommit-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Install the hook configuration, measure clean-run latency, and exercise representative failing files at pre-commit and pre-push stages.
---

# Pre-commit standard

## Objectives

Local checks provide fast, deterministic feedback before code reaches the authoritative CI gate. They reduce avoidable failures without pretending to replace integration, platform, security, publication, or deployment verification.

## Rules

- Define and measure a latency budget.
- Run without production credentials.
- Avoid network access in pre-commit.
- Reuse the same tool configuration as CI.
- Give every required local check matching CI enforcement or a documented exception.
- Pass changed files only to tools that are safe to run incrementally.
- Print a clear repair command on failure.
- Keep dependency versions in hook or language configuration, not prose.
- Detect conflict markers, secrets, and private keys when relevant to the repository.
- Regenerate or verify generated files instead of hand-editing them.
- Preserve the framework's standard emergency bypass, but never allow it to bypass CI.
- Pin remote hook revisions or use controlled local hooks.
- Avoid duplicate formatters, linters, or validators that enforce conflicting rules.

## Staging

### Pre-commit

Use for checks that are fast and deterministic on changed files:

- formatting;
- syntax and lightweight lint;
- conflict markers;
- secret patterns;
- focused schema checks;
- targeted generated-file validation.

### Pre-push or local CI

Use for repository-wide work:

- compilation;
- type checking;
- broader lint;
- unit tests;
- documentation validation;
- package builds.

### CI only

Keep these in the authoritative pipeline unless a reliable local sandbox exists:

- service-container and integration tests;
- live APIs;
- platform matrices;
- credentialed security services;
- publication and deployment;
- provenance and signing.

## Performance

Measure both warm and cold execution. A hook that routinely exceeds its budget is narrowed, moved to pre-push, or exposed as an explicit local CI command. Do not solve slowness by silently skipping required checks.

## Failure behavior

A failed hook identifies the file or command, explains the violated property, and provides a repair command. Tools that modify files state what changed and require the user to review and stage the result.

## Portability

- Prefer repository-relative commands.
- Avoid shell-specific behavior when the contributor platforms are mixed.
- Verify required runtimes before execution.
- Keep environment assumptions explicit.
- Do not depend on globally installed tools unless the repository intentionally chooses that contract.

## Acceptance

Measured latency meets the repository budget, commands share configuration with CI, representative failures block correctly, local artifacts such as `.venv` are ignored where appropriate, and bypass does not weaken the authoritative gate.

## Verification

Install the configured hooks in a clean checkout, measure a no-change run, trigger representative formatting, validation, and test failures, confirm repair guidance, exercise pre-push checks, and verify that CI still enforces every required property independently.
