---
description: Selection matrix for composing CI/CD workflow profiles by repository archetype and release artifact.
doc_id: reference.ci-cd-template-selection
type: reference
status: active
rigor: informative
owners: [repository-maintainers]
---

# CI/CD template selection

## Profiles

| Repository need | Required profile | Add when applicable |
| --- | --- | --- |
| Python library or service | `ci.yml.template` | container, docs, Semgrep, package release |
| Python MCP server | `ci.yml.template`, `python-mcp.yml.template` | container publish, services, scheduled security |
| Python container service | `ci.yml.template`, `python-container.yml.template` | protected publish |
| .NET library or service | `dotnet-ci.yml.template` | package release, container profile |
| NuGet package | `dotnet-ci.yml.template`, `dotnet-package.yml.template` | GitHub Release |
| Governed documentation | `docs-validation.yml.template` | PR summary comment only from trusted workflow architecture |
| Security-sensitive repository | `semgrep-pr.yml.template`, `semgrep-scheduled.yml.template` | CodeQL or ecosystem-native scanners |
| Multi-ecosystem dependencies | `dependabot-multi-ecosystem.yaml.template` | Renovate regex manager for template files |

## Composition rules

- Reuse the same install, test, and validator commands locally and in CI.
- Do not duplicate the same test suite across jobs unless the environment is intentionally different.
- Prefer a small number of coherent jobs over many one-step jobs with repeated setup.
- Separate package and container release from pull-request validation.
- Add service containers only to jobs that need them.
- Use matrices only when each axis represents supported behavior and total cost is bounded.
- Use path filters as an optimization, never as the sole protection for a critical release.

## Python variants

A library usually needs quality, tests, coverage, and package build. A web service adds integration and health checks. An MCP server adds protocol registration, client invocation, schema, cancellation, and error-shape checks. An MQTT or database integration adds a service container and readiness wait.

## .NET variants

A library needs restore, format, analyzer build, tests, coverage, pack validation, and artifact inspection. A service adds integration hosting and health checks. A package release validates the tag-derived package version and publishes only the package built from the validated revision.
