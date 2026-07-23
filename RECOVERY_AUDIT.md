---
description: Audit mapping knowledge removed by the skills cleanup to its current canonical location.
doc_id: decision.skills-recovery-audit
type: decision
status: active
rigor: operational
owners: [repository-maintainers]
verification: Compare commit 6a5f1850 with the current branch, generate and execute fresh Python and .NET MCP servers, run `python scripts/ci.py`, and inspect every mapping in this document.
---

# Skills recovery audit

## Decision

The cleanup commit removed valuable production knowledge together with obsolete and duplicated material. The repository now uses a compact core plus focused references, templates, examples, executable generators, compatibility entry points, and regression tests. Old monoliths are not restored byte-for-byte because they mixed stable invariants, volatile versions, project-specific details, and unsafe defaults.

## Recovery map

| Removed knowledge | Current canonical location | Recovery decision |
| --- | --- | --- |
| AFDS document lifecycle, upstream traversal, ownership, conflicts, downstream impact, freshness, and type-specific structures | `skills/afds-doc-writer/references/lifecycle-and-impact.md`, `type-playbooks.md`, and `templates/governed-document.md.template` | Restored around explicit ownership and evidence |
| AFDS executable validation, fenced Markdown handling, links, metadata types, and explicit verification | `skills/afds-doc-writer/validate.py` and `tests/test_afds_validator.py` | Reimplemented with stronger CommonMark regressions |
| Stable links used by downstream repositories | Deprecated `docs_standards.md` and `mcp-server-standards.md` entry points | Restored as redirects instead of duplicate standards |
| Python quality, coverage, services, Docker smoke, MCP registration checks, and artifacts | CI templates for Python, MCP, containers, and references | Restored as composable profiles |
| .NET format, analyzers, TRX, coverage, artifacts, package and release behavior | .NET CI, MCP contract, and package templates plus template-selection guidance | Restored with exact-revision release identity and direct NuGet `package/metadata` verification |
| Incremental documentation validation and pull-request feedback | Documentation workflow template and failure-pattern guidance | Restored without unsafe write permissions on untrusted pull requests |
| Semgrep pull-request and scheduled scans | Semgrep workflow templates | Restored with bounded permissions and SARIF handling |
| Multi-ecosystem dependency updates and action pin maintenance | Dependabot template and action-SHA maintenance guidance | Restored; non-workflow action pins are checked by tests |
| Local pre-commit and pre-push gates | CI/CD local-quality-gate reference and templates | Merged into CI/CD instead of remaining an empty top-level skill |
| MCP maturity, transport independence, lifecycle, auth, errors, cancellation, observability, degradation, discovery, aggregation, server instructions, embedded hosting, and operations | MCP `STANDARD.md` plus focused references | Restored as a language-neutral core |
| Executable Python MCP project baseline | `tools/generate_python_server.py` and `tests/test_mcp_generator.py` | Rebuilt as an atomic generator whose output runs through an official real MCP client |
| Executable .NET MCP project baseline | `tools/generate_dotnet_server.py` and `tests/test_mcp_dotnet_generator.py` | Rebuilt as an atomic .NET 10 generator whose output is restored, built, published, and invoked through the official C# MCP client |
| MCP manifest schema, risk-consistency matrix, versioning, deprecation, and complete coverage gate | `capability-manifests-and-versioning.md` | Restored with fail-closed registration and runtime enforcement |
| MCP transport parity, session safety, Origin policy, readiness, lifecycle ownership, and protocol conformance | `transport-lifecycle-and-conformance.md` | Restored for stdio and Streamable HTTP; the deprecated two-endpoint legacy HTTP+SSE transport is forbidden in new servers |
| Safe filesystem roots, generated exports, artifact ownership, long-running task registries, session quotas, browser profiles, interactive authentication, UI drift, multi-backend namespaces, and embedded-host ownership | `runtime-boundaries-and-artifacts.md` | Recovered from production server behavior and converted into normative runtime and test contracts |
| FastMCP registration, context, lifespan, content blocks, async I/O, SDK compatibility, event-loop affinity, bounded executors, task and browser boundaries | `python-fastmcp.md`, Python example, and generator | Restored for the stable official SDK lane with separate candidate-major policy |
| .NET hosting, DI, `ClaimsPrincipal`, authorization filters, cancellation, structured content, protocol errors, task execution, official transports, AOT registration, and test host patterns | `dotnet-mcp.md`, .NET examples, generator, and contract workflow | Restored as a first-class executable profile, not a Python syntax translation |
| Cross-language mapping of production incidents to enforceable controls | `cross-language-invariant-map.md` | Expanded with lifecycle, manifest, transport, sanitization, task, identity, and packaging lessons |
| MCP layered tests including generator, manifest, lifecycle, filesystem, task, browser, race, parity, conformance, real client, and artifacts | `testing-strategy.md`, migration tests, and both generator suites | Restored with independently falsifiable layers |
| Migration experience from read-only aggregators, heterogeneous devices, SSH appliances, multi-backend administration, financial APIs, and browser automation | Python and .NET migration simulations | Generalized into portable archetypes without retaining private repository names or unsafe implementation details |
| MCP consumer discovery, risk, retry, conflict refresh, errors, pagination, partial execution, and negotiation | MCP consumer standard, references, engine, and tests | Restored with typed consumer-owned trust channels and monotonic fail-closed aggregation |
| Large consumer decision and efficiency regression suite | Decision-engine tests and focused policy references | Rebuilt around current safe behavior rather than legacy assumptions |

## Unsafe legacy behavior intentionally rejected

- A missing manifest, a `[READ]` name prefix, or server-provided description never downgrades unknown risk to read-only.
- A boolean trust switch never upgrades values from an untrusted metadata map; trusted risk and idempotency arrive in typed consumer-owned objects.
- Risk evidence is combined regardless of order; weaker metadata cannot hide a stronger dangerous prefix or annotation.
- Tool annotations are advisory unless the server trust boundary is explicit.
- A concurrency flag without runtime enforcement and race evidence is not accepted.
- A custom REST or partial JSON-RPC bridge is not advertised as a conformant MCP transport.
- The deprecated two-endpoint legacy HTTP+SSE transport is not used by new servers. Modern Streamable HTTP may still use `text/event-stream` framing without becoming the legacy transport.
- A string-prefix path check is not accepted as filesystem containment.
- Daemon threads and untracked async tasks are not accepted as long-running operation state. A protocol task store is not treated as a supervised executor.
- Short, transferable session, task, approval, or artifact identifiers are not accepted.
- Browser profiles are not treated as ordinary cache directories; they are credential stores with principal, process-lock, and cleanup policy.
- Custom success DTOs do not replace protocol-native `IsError`; structured C# output requires explicit structured-content configuration and tests.
- Data annotations and generated JSON Schema do not replace runtime validation before I/O.
- Mutable GitHub Action tags are not accepted in bundled workflows.
- A container or package is not published merely because source tests passed; the same image or exact artifact is smoke-tested before publication.
- Manual release inputs do not inherit tag, SHA, or package version identity from the dispatch branch.
- NuGet identity is read only from direct `package/metadata/id` and `package/metadata/version`, never from dependency descendants.
- Volatile action versions, timestamps, dependency matrices, semantic hashes, fitness scores, or invented protocol-removal dates are not handwritten as durable truth.
- A repository file-count limit is not used as an architectural quality metric.
- Exact per-skill file allowlists do not prevent legitimate references, examples, templates, tools, or compatibility stubs.

## Verification

Generate fresh Python and .NET servers and execute their complete real-client suites. Run the full repository quality gate. Compare the cleanup commit and the current branch by topic, not only filename or line count. A topic is recovered only when its invariant, language-specific implementation, runtime enforcement, and regression evidence are present.
