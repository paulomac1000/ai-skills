---
description: Selection matrix for composing CI/CD workflow profiles by repository archetype, runner budget, and release artifact.
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
| .NET MCP server | `dotnet-ci.yml.template`, `dotnet-mcp.yml.template` | package/container release, candidate SDK lane |
| NuGet package | `dotnet-ci.yml.template`, `dotnet-package.yml.template` | GitHub Release |
| Governed documentation | `docs-validation.yml.template` | PR summary comment only from trusted workflow architecture |
| Security-sensitive repository | `semgrep-pr.yml.template`, `semgrep-scheduled.yml.template` | CodeQL or ecosystem-native scanners |
| Multi-ecosystem dependencies | `dependabot-multi-ecosystem.yaml.template` | Renovate regex manager for template files |
| Private or high-churn agentic repository with finite hosted-runner budget | `on-demand-ci.yaml.template` for expensive development gates | separate manual Semgrep/container/cross-platform workflows; scheduled assurance and protected release remain separate |

## Execution-policy choice

Use normal continuously triggered CI when automatic pull-request feedback is affordable and required by the repository. Use `on-demand-ci.yaml.template` when repeated agent pushes would spend material hosted-runner quota without adding proportional evidence.

The on-demand template is not a weaker quality profile. It changes execution frequency:

- branch iteration uses local checks plus manual fast/full dispatch;
- expensive development jobs do not start on pull-request synchronization;
- the governed integration branch runs the full path automatically;
- the final accepted SHA still needs every gate required by repository policy.

Do not switch to on-demand CI merely to make a red gate disappear. First distinguish code failure from provider/runner failure. A job that never receives a runner and executes zero steps is not code evidence.

## Composition rules

- Reuse the same install, test, and validator commands locally and in CI.
- Do not duplicate the same test suite across jobs unless the environment is intentionally different.
- Prefer a small number of coherent jobs over many one-step jobs with repeated setup.
- Separate package and container release from development validation.
- Add service containers only to jobs that need them.
- Use matrices only when each axis represents supported behavior and total cost is bounded.
- Use path filters as an optimization, never as the sole protection for a critical release.
- Keep prerelease MCP SDKs in a separately visible candidate lane; candidate success never replaces the stable production lane.
- Keep trust policy and execution policy independent: changing triggers never authorizes broader permissions or secrets.
- Keep cheap metadata automation, intentionally scheduled assurance, and release workflows separate from expensive development CI instead of disabling all automation mechanically.

## Python variants

A library usually needs quality, tests, coverage, and package build. A web service adds integration and health checks. An MCP server adds protocol registration, official-client invocation, schema, cancellation, error-shape, and exact-artifact checks. An MQTT or database integration adds a service container and readiness wait.

## .NET variants

A library needs restore, format, analyzer build, tests, coverage, pack validation, and artifact inspection. A service adds integration hosting and health checks. A .NET MCP server additionally needs real stdio and Streamable HTTP initialization, public tool-schema enumeration, authorization-filtered discovery, protocol-native errors, structured content, cancellation, explicit session mode, task policy, and smoke of the exact published artifact through the official C# MCP client.

A package release validates the tag-derived package version, reads identity only from direct `package/metadata/id` and `package/metadata/version`, rejects extra or spoofed identities, and publishes only files in the verified manifest from the validated revision.
