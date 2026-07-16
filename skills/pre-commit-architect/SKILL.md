---
name: pre-commit-architect
description: Audit, design, or repair local Git pre-commit and pre-push checks for Python, .NET, shell, and polyglot repositories. Use for fast feedback, hook staging, CI parity, secret scanning, and developer setup.
---

# Pre-commit architect

Use `precommit-standard.md`. Select the framework already accepted by the repository; native Git hooks, `pre-commit`, lefthook, or language tooling may all be valid.

## Procedure

1. Inspect CI, language manifests, existing developer commands, repository size, and measured check duration.
2. Classify checks by purpose: syntax, format, lint, types, secrets, unit tests, generated-file freshness, integration, build, deployment.
3. Put deterministic, local, low-latency checks in pre-commit.
4. Put slower repository-wide checks in pre-push or an explicit local verification command.
5. Keep credentialed, network-dependent, platform-specific, and deployment checks in CI unless a reliable local sandbox exists.
6. Reuse the same underlying commands and configuration as CI; exact orchestration may differ.
7. Pin hook dependencies through manifests and let dependency automation update them.
8. Measure the hook suite and document bypass and recovery behavior.
9. Test a clean pass and representative failures.

## Do not

- Do not require every CI test to run before every commit.
- Do not require `fail_fast: false` on every hook; choose behavior from feedback needs.
- Do not force Python's `pre-commit` framework on .NET or infrastructure repositories.
- Do not modify `AGENTS.md` with boilerplate unless the project uses it as canonical developer guidance.
- Do not duplicate tool configuration inside hook entries.
