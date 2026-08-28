---
afds_schema_version: 2
description: Maps material README claims to canonical repository evidence, corroboration, verification, and drift-safe projection choices.
doc_id: reference.readme-evidence-source-map
type: reference
status: active
rigor: informative
owners: [repository-maintainers]
---

# README evidence source map

Use this file while building the temporary claim ledger.

The existing README is deliberately low in the authority order. It is useful
for discovering intended concepts and vocabulary, but every mutable claim must
be reconciled against its actual owner.

## Claim ledger

For each material claim, record:

| Field | Meaning |
|---|---|
| Claim | The exact fact the README may state |
| Canonical source | File/runtime contract that owns the fact |
| Corroboration | Independent supporting evidence when useful |
| Verification | Command/test/introspection used to check it |
| Volatility | low / medium / high |
| README form | inline / summary / live badge / link / omit |
| Conflict | none or the unresolved disagreement |

Do not commit this ledger unless the repository explicitly wants it as evidence.

## Source map

| README fact | Preferred evidence | Verification | README policy |
|---|---|---|---|
| Project name | package/project metadata + public repository identity | compare package name, executable, repo | use public product name consistently |
| One-line purpose | public entrypoint/capability surface + repository description | inspect representative behavior/tests | concise, no unsupported marketing |
| Supported runtime | `pyproject.toml`, `package.json`, `go.mod`, toolchain files + CI matrix/container | install/typecheck/test on claimed versions where feasible | state supported range, not one incidental dev version |
| Installation | published package/image/release workflow + package metadata | clean install or artifact smoke | prefer normal user artifact |
| Start command | console script, `__main__`, package scripts, Docker entrypoint/CMD | `--help`, startup smoke, health check | copy-pasteable |
| Required env/config | typed settings/config schema + `.env.example` | startup/config tests | show only onboarding-critical subset; link full reference |
| Defaults | typed config/schema or executable constants | config/unit tests | do not make README canonical owner |
| Ports/endpoints | server registration/router + compose/container config | smoke/health tests | compact table if several properties |
| Transport | server transport wiring + client tests | official client smoke | show recommended default first |
| MCP tools | governed capability registry or runtime `tools/list` | compare runtime registration with registry/tests | summarize groups; avoid hand-maintained exact counts |
| Tool risk | policy/capability definition | authorization tests | match domain vocabulary exactly |
| API surface | OpenAPI/schema/router/IDL | generated schema or contract tests | summary + canonical reference |
| Read/write default | policy/config + enforcement tests | negative-path tests | state prominently for privileged services |
| Authentication | middleware/transport policy + tests | unauthorized/authorized smoke | state effective requirement, not intent |
| Network exposure | bind validation/config + deployment defaults | startup tests/container inspect | surface unsafe opt-ins |
| Secret handling | settings/secret store/redaction + tests | redaction/log tests | never include real secrets |
| Mutation retry semantics | invocation/retry layer + tests | ambiguity/retry tests | document when operationally important |
| Docker image | Dockerfile + publish workflow/registry package | build or pull/run smoke | prefer immutable release tag/digest guidance where relevant |
| CI status | workflow file + GitHub Actions | live workflow badge | never hard-code “passing” |
| Coverage | coverage config/service | live badge/report | no copied percentage |
| Test commands | CI/project config | run commands | commands only; omit test count |
| Version | package/release/tag | release/package endpoint | avoid hard-coding moving-main version unless contract requires it |
| License | `LICENSE` + package metadata | check SPDX/name agreement | link license |
| Architecture | actual entrypoints/modules/dependency boundaries | source inspection/tests | brief mental model; deep rationale elsewhere |
| Supported platforms | packaging metadata + CI + documented platform-specific implementation | build/smoke lanes | distinguish tested from merely expected |
| Compatibility/migration | public contract + changelog/migration docs + tests | upgrade/compat tests | top callout only when currently material |
| Standards adoption | pinned authority + validated adoption evidence | repository-owned validator/external evidence | never infer compliance from a badge or lock alone |
| Help/support | issue/discussion/community configuration | inspect enabled channels | link, do not invent contact |
| Contributing | `CONTRIBUTING.md` + dev commands | run contributor checks | summarize entry point |
| Security reporting | `SECURITY.md` | inspect policy | link canonical policy |
| Changelog | `CHANGELOG.md` / releases | release tooling | link; do not mirror release history |
| UI/output visuals | current application output | current screenshot/demo | use only if current and helpful |

## Runtime-version reconciliation

Never read one version string and assume it is the supported range.

For runtime support, compare:
1. package metadata constraint;
2. CI test matrix;
3. lock/artifact build lanes;
4. Docker base/runtime;
5. syntax/runtime features in source when relevant.

If these differ, distinguish:
- **required by metadata**;
- **tested in CI**;
- **used by the container artifact**.

Do not silently collapse them into a false statement.

## Security-claim rule

A prose security document is supporting evidence, not sufficient proof of an
effective control.

Claims such as “read-only by default”, “loopback-only”, “auth required”,
“writes require approval”, “host verification is enabled”, “no raw shell”, or
“secrets are redacted” require executable enforcement or tests.

If implementation and prose disagree, the README must not repeat the prose.

## MCP-specific discovery

Inspect, as applicable:
- `McpServer` / `FastMCP` construction;
- `registerTool`, decorators, or capability registries;
- runtime `tools/list`;
- transport initialization;
- client compatibility tests;
- policy/authorization layer;
- response/provenance envelope;
- HTTP bind/auth configuration;
- Docker/stdio execution path;
- registry metadata comments already present in README.

Prefer one governed catalog and derive all secondary views from it.
