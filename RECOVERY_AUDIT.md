---
description: Audit mapping knowledge removed by the skills cleanup to its current canonical location.
doc_id: decision.skills-recovery-audit
type: decision
status: active
rigor: operational
owners: [repository-maintainers]
verification: Compare commit 6a5f1850 with the current branch, run `python scripts/ci.py`, and inspect every mapping in this document.
---

# Skills recovery audit

## Decision

The cleanup commit removed valuable production knowledge together with obsolete and duplicated material. The repository now uses a compact core plus focused references, templates, examples, tools, compatibility entry points, and regression tests. Old monoliths are not restored byte-for-byte because they mixed stable invariants, volatile versions, project-specific details, and unsafe defaults.

## Recovery map

| Removed knowledge | Current canonical location | Recovery decision |
| --- | --- | --- |
| AFDS document lifecycle, upstream traversal, ownership, conflicts, downstream impact, freshness, and type-specific structures | `skills/afds-doc-writer/references/lifecycle-and-impact.md`, `type-playbooks.md`, and `templates/governed-document.md.template` | Restored around explicit ownership and evidence |
| AFDS executable validation, fenced Markdown handling, links, metadata types, and explicit verification | `skills/afds-doc-writer/validate.py` and `tests/test_afds_validator.py` | Reimplemented with stronger CommonMark regressions |
| Stable links used by downstream repositories | Deprecated `docs_standards.md` and `mcp-server-standards.md` entry points | Restored as redirects instead of duplicate standards |
| Python quality, coverage, services, Docker smoke, MCP registration checks, and artifacts | CI templates for Python, MCP, containers, and references | Restored as composable profiles |
| .NET format, analyzers, TRX, coverage, artifacts, package and release behavior | .NET CI and package templates plus template-selection guidance | Restored using current hosting and test conventions |
| Incremental documentation validation and pull-request feedback | Documentation workflow template and failure-pattern guidance | Restored without unsafe write permissions on untrusted pull requests |
| Semgrep pull-request and scheduled scans | Semgrep workflow templates | Restored with bounded permissions and SARIF handling |
| Multi-ecosystem dependency updates and action pin maintenance | Dependabot template and action-SHA maintenance guidance | Restored; non-workflow action pins are checked by tests |
| Local pre-commit and pre-push gates | CI/CD local-quality-gate reference and templates | Merged into CI/CD instead of remaining an empty top-level skill |
| MCP maturity, transport independence, lifecycle, auth, errors, cancellation, observability, degradation, discovery, aggregation, and operations | MCP `STANDARD.md` plus focused references | Restored as a language-neutral core |
| MCP manifest schema, risk-consistency matrix, versioning, deprecation, and complete coverage gate | `capability-manifests-and-versioning.md` | Restored with fail-closed registration and runtime enforcement |
| MCP transport parity, session safety, Origin policy, readiness, lifecycle ownership, and protocol conformance | `transport-lifecycle-and-conformance.md` | Restored and corrected for stdio and Streamable HTTP |
| FastMCP registration, context, lifespan, content blocks, async I/O, SDK compatibility, and event-loop affinity | `python-fastmcp.md` and Python example | Restored for supported FastMCP generations |
| .NET hosting, DI, cancellation, request scope, Activity, official transports, filters, concurrency, and test host patterns | `dotnet-mcp.md` and .NET examples | Restored as a first-class profile, not a Python syntax translation |
| Cross-language mapping of production incidents to enforceable controls | `cross-language-invariant-map.md` | Expanded with lifecycle, manifest, transport, sanitization, and race lessons |
| MCP layered tests including manifest, lifecycle, race, parity, conformance, and artifacts | `testing-strategy.md` | Restored with independently falsifiable layers |
| MCP consumer discovery, risk, retry, conflict refresh, errors, pagination, partial execution, and negotiation | MCP consumer standard, references, engine, and tests | Restored with fail-closed trust semantics |
| Large consumer decision and efficiency regression suite | Decision-engine tests and focused policy references | Rebuilt around current safe behavior rather than legacy assumptions |

## Unsafe legacy behavior intentionally rejected

- A missing manifest, a `[READ]` name prefix, or server-provided description never downgrades unknown risk to read-only.
- Tool annotations are advisory unless the server trust boundary is explicit.
- A concurrency flag without runtime enforcement and race evidence is not accepted.
- A custom REST or partial JSON-RPC bridge is not advertised as a conformant MCP transport.
- Mutable GitHub Action tags are not accepted in bundled workflows.
- A container is not published merely because source tests passed; the exact locally built image is smoke-tested and the same image is pushed.
- Manual release inputs do not inherit tag or SHA identity from the dispatch branch.
- Volatile action versions, timestamps, dependency matrices, semantic hashes, and fitness scores are not handwritten as durable truth.
- A repository file-count limit is not used as an architectural quality metric.
- Exact per-skill file allowlists do not prevent legitimate references, examples, templates, tools, or compatibility stubs.

## Verification

Run the full repository quality gate. Compare the cleanup commit and the current branch by topic, not only filename or line count. A topic is recovered only when its invariant, language-specific implementation, runtime enforcement, and regression evidence are present.
