---
name: ci-cd-architect
description: Audit, design, repair, or migrate GitHub Actions CI/CD for Python, .NET, Docker, and polyglot repositories. Use for tests, builds, releases, security, provenance, Dependabot, caching, permissions, and workflow debugging.
---

# CI/CD architect

Use `ci-cd-standard.md` for invariant properties. Read generated dependency facts instead of copying action or package versions from prose.

## Route the task

| Need | Load |
|---|---|
| Dependency and action updates | `references/dependency-policy.md` |
| Release and provenance | `references/release-security.md` |
| Project-specific templates | Inspect `templates/` after classifying the repository |

## Procedure

1. Inspect repository languages, manifests, lock files, test layout, deployable artifacts, release targets, protected branches, secrets, and existing workflows.
2. Reconstruct the real delivery graph: change → validation → artifact → publication → deployment.
3. Audit properties, not filenames or a universal job count.
4. Keep fast deterministic checks early; move expensive or credentialed checks to later gates.
5. Minimize workflow permissions per job and isolate untrusted pull-request code from secrets.
6. Pin third-party actions by immutable commit when the repository policy requires it; let Dependabot maintain the pin.
7. Reuse language-native caches and build outputs without crossing trust boundaries.
8. Make releases consume tested artifacts or the exact tested commit.
9. Add concurrency, cancellation, timeouts, environment protection, and rollback appropriate to the deployment.
10. Validate YAML, run local generators, inspect workflow results, and report any check that could not be executed.

## Do not

- Do not require every repository to have the same workflow names, job count, Python version, or release strategy.
- Do not hardcode “latest” action versions in the skill or standard.
- Do not install tools ad hoc in multiple jobs when a manifest or reusable action can own them.
- Do not use `pull_request_target` to execute untrusted checkout with secrets.
- Do not publish an artifact from a different source tree than the one validated.
- Do not silence failures with broad `continue-on-error` or `|| true`; narrow exceptions need an owner and reason.
