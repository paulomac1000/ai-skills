---
description: Design rules and practical profiles for pre-commit and pre-push checks that preserve CI authority.
doc_id: reference.local-quality-gates
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Install the generated hooks in a disposable checkout and verify both success and bounded failure paths.
---

# Local quality gates

## Budget

Pre-commit should normally finish in seconds. It may format changed files, lint changed or cheap project scopes, validate syntax, check secrets with local rules, and validate directly affected documentation. Pre-push may run a bounded parity command such as `python scripts/ci.py` or a focused solution test.

## Prohibited local-hook behavior

- network calls;
- production credentials or secret-dependent tests;
- deployment or publication;
- unbounded subprocesses;
- hidden configuration different from CI;
- mutation of unrelated files;
- full environment orchestration on every commit.

## Python profile

Use repository-owned Ruff, type-check, validator, and test configuration. Avoid downloading ad hoc versions on each hook invocation. Compile checks are useful but do not replace tests. The pre-push hook calls the same bounded runner used by CI.

## .NET profile

Use `dotnet format --verify-no-changes` and targeted tests on pre-push. Analyzer configuration belongs in `Directory.Build.props`, editorconfig, or project files. Avoid restoring every solution repeatedly when the hook framework can reuse the local SDK cache.

## Polyglot profile

Route changed files to language-specific cheap checks and reserve the full cross-language contract suite for pre-push or CI. One failing language gate blocks the push; results remain attributable to the responsible command.

## Measurement

Measure hook duration on a warm checkout and record the budget in the repository guide. When a pre-commit check repeatedly exceeds the budget, move it to pre-push or CI rather than training developers to bypass hooks.

## Verification

Test hook installation, a clean pass, a known formatting failure, a known test failure, and the timeout path. Confirm hooks use no secrets and leave the working tree understandable.
