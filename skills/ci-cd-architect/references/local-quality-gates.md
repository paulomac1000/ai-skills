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
- full environment orchestration on every commit;
- automatic staging or committing on behalf of the developer;
- downloading an unpinned tool through `npx`, `pnpx`, or an equivalent command during hook execution.

## Package-manager selection

Select the JavaScript package manager from repository evidence rather than preference:

- `pnpm-lock.yaml` selects pnpm;
- `yarn.lock` selects Yarn;
- `package-lock.json` or `npm-shrinkwrap.json` selects npm;
- an authoritative `packageManager` field may further pin the tool and version.

When multiple conflicting lockfiles exist or no authoritative signal exists, fail with a clear inventory finding and require an explicit repository decision. Do not silently default to npm. Install hook dependencies through the selected package manager and its committed lockfile.

## Husky and lint-staged profile

Use Husky only as a thin dispatcher to repository-owned commands. Preserve an existing hook framework and formatter configuration unless the repository explicitly chooses a migration. Do not overwrite `.husky/pre-commit`, lint-staged configuration, Prettier configuration, or an existing package script without reviewing its behavior and ownership.

A governed Node pre-commit profile should normally:

1. run lint-staged through the selected package manager's local executable resolution;
2. route staged file types to the repository's existing formatter, linter, secret scanner, syntax validator, or focused documentation validator;
3. avoid unstaged-file loss by preserving partially staged files and verifying the resulting index and working tree;
4. use pinned development dependencies already present in the lockfile;
5. keep type-checking or tests only when their measured warm duration stays within the pre-commit budget;
6. move broader type-checking and tests to pre-push or hosted CI when they exceed that budget.

Prefer an explicit repository script such as `quality:staged` over embedding a long command in `.husky/pre-commit`. The hook may call the package-manager-native equivalent of lint-staged, but it must not trigger a network install. A local bypass such as `--no-verify` never changes the acceptance contract: hosted CI remains authoritative.

## Python profile

Use repository-owned Ruff, type-check, validator, and test configuration. Avoid downloading ad hoc versions on each hook invocation. Compile checks are useful but do not replace tests. The pre-push hook calls the same bounded runner used by CI.

## .NET profile

Use `dotnet format --verify-no-changes` and targeted tests on pre-push. Analyzer configuration belongs in `Directory.Build.props`, editorconfig, or project files. Avoid restoring every solution repeatedly when the hook framework can reuse the local SDK cache.

## Polyglot profile

Route changed files to language-specific cheap checks and reserve the full cross-language contract suite for pre-push or CI. One failing language gate blocks the push; results remain attributable to the responsible command.

## Measurement

Measure hook duration on a warm checkout and record the budget in the repository guide. When a pre-commit check repeatedly exceeds the budget, move it to pre-push or CI rather than training developers to bypass hooks.

## Verification

Test all of the following in a disposable checkout:

- hook installation and executable permissions;
- the package-manager lifecycle or `prepare` integration used to install hooks;
- a clean pass;
- a known formatter or lint failure;
- a known focused-test failure when tests are in scope;
- a partially staged file with additional unstaged edits;
- a filename containing spaces or non-ASCII characters;
- the timeout path;
- operation without network access;
- a local bypass followed by rejection from the authoritative hosted gate.

Confirm hooks use no secrets, leave the index and working tree understandable, and do not create commits automatically.
