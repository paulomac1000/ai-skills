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

The cleanup commit removed valuable production knowledge together with obsolete and duplicated material. The repository now uses a compact core plus focused references, templates, examples, tools, and regression tests. Old monoliths are not restored byte-for-byte because they mixed stable invariants, volatile versions, project-specific details, and unsafe defaults.

## Recovery map

| Removed knowledge | Current canonical location | Recovery decision |
| --- | --- | --- |
| AFDS document lifecycle, upstream traversal, ownership, conflicts, downstream impact, freshness, and type-specific structures | `skills/afds-doc-writer/references/lifecycle-and-impact.md`, `type-playbooks.md`, and `templates/governed-document.md.template` | Restored and simplified around explicit ownership and evidence |
| AFDS executable validation, fenced Markdown handling, links, metadata types, and explicit verification | `skills/afds-doc-writer/validate.py` and `tests/test_afds_validator.py` | Reimplemented with stronger CommonMark regressions |
| Python quality, coverage, services, Docker smoke, MCP registration checks, and artifacts | `skills/ci-cd-architect/templates/ci.yml.template`, `python-mcp.yml.template`, and `python-container.yml.template` | Restored as composable profiles |
| .NET format, analyzers, TRX, coverage, artifacts, package and release behavior | `dotnet-ci.yml.template`, `dotnet-package.yml.template`, and `references/template-selection.md` | Restored using current .NET hosting and test conventions |
| Incremental documentation validation and pull-request feedback | `docs-validation.yml.template` and `references/failure-patterns.md` | Restored without unsafe write permissions on untrusted pull requests |
| Semgrep pull-request and scheduled scans | `semgrep-pr.yml.template` and `semgrep-scheduled.yml.template` | Restored with bounded permissions and SARIF handling |
| Multi-ecosystem dependency updates and action pin maintenance | `dependabot-multi-ecosystem.yaml.template` and `references/action-sha-maintenance.md` | Restored; action pins in non-workflow templates are checked by repository tests |
| Local pre-commit and pre-push gates | `skills/ci-cd-architect/references/local-quality-gates.md` and local-gate templates | Merged into CI/CD instead of remaining an empty top-level skill |
| MCP maturity levels, transport independence, lifecycle, auth, security, errors, deadlines, cancellation, observability, graceful degradation, discovery, aggregation, and operations | `skills/mcp-server-architect/STANDARD.md` plus focused references | Restored as a language-neutral core with operational appendices |
| FastMCP registration, call-tool, context, lifespan, decorator mocking, content-block, async I/O, cleanup, and test-hierarchy pitfalls | `skills/mcp-server-architect/references/python-fastmcp.md` | Restored as SDK-specific guidance and regression checklist |
| .NET MCP hosting, DI, `CancellationToken`, request scope, `Activity`, exception mapping, and test host patterns | `skills/mcp-server-architect/references/dotnet-mcp.md` and `examples/dotnet/` | Added as a first-class profile rather than a syntax translation of Python |
| Cross-language mapping of Python incidents to .NET controls | `cross-language-invariant-map.md` | Restored and expanded |
| MCP consumer discovery, risk, retry, errors, pagination, partial execution, cross-server flow, and capability negotiation | `skills/mcp-server-consumer/STANDARD.md`, references, engine, and tests | Restored with fail-closed trust semantics |
| Large consumer decision and efficiency regression suite | `tests/test_decision_engine.py` and focused policy references | Rebuilt around current safe behavior rather than legacy assumptions |

## Unsafe legacy behavior intentionally rejected

- A missing manifest, a `[READ]` name prefix, or server-provided description never downgrades unknown risk to read-only.
- Server annotations are advisory unless the server trust boundary is explicit.
- Mutable GitHub Action tags are not accepted in bundled workflows.
- A container is not published merely because source tests passed; the exact locally built image is smoke-tested and the same image is pushed.
- Manual release inputs do not inherit tag or SHA identity from the branch that triggered the workflow.
- Volatile action versions, timestamps, dependency matrices, semantic hashes, and fitness scores are not handwritten as durable truth.
- A repository file-count limit is not used as an architectural quality metric.
- Exact per-skill file allowlists do not prevent legitimate references, examples, templates, or tools.

## Verification

Run the full repository quality gate. During review, compare the cleanup commit and the current branch by topic, not only by filename or line count. A topic is recovered only when its invariant, implementation guidance, and regression evidence are all present.
