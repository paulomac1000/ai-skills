# Changelog

## 1.3.0 - 2026-08-12

### Added

- Added consumer-driven adoption discovery, immutable external consumer canaries, observed upstream-contract validation, and live-backend mutation-safety contracts derived from real MCP migrations.
- Added transport-by-capability authorization parity, profile-specific FastMCP consumer evidence, and a stable-version drift gate so changed stable skill contents cannot continue to identify as the previous release.
- Added explicit `pull-request`, `trusted-ci`, and `protected-release` workflow-policy profiles with profile-specific permissions, closed literal runner matrices, and reusable-workflow validation.
- Added repository-governed AFDS document profiles, bounded confined link and anchor checks, and regression coverage for basename exemptions, symlinks, traversal, and informative-document verification.
- Added machine-readable MCP rule applicability, granular runtime, artifact, task, browser, backend, hosting, readiness, discovery, configuration, component, and SDK-isolation rules.
- Added a lightweight local conformance report and validator that derive applicable rules without requiring GitHub run, job, artifact, or acceptance-authority identifiers.
- Added a per-language MCP protocol and SDK compatibility matrix that records verified revisions independently for Python and .NET and leaves unsupported claims explicitly unasserted.
- Added a reusable trusted-workflow audit template that checks out the candidate and immutable verifier separately, installs the verifier's hashed dependency graph, and executes only the external auditor.

### Changed

- Reworked the container and NuGet publish templates so unprivileged validation builds and tests closed artifacts while protected publishers verify and publish them without checking out or executing candidate source.
- Replaced mutable runner labels across all workflow templates, short-SHA artifact identity, post-checkout authenticated fetches, and `docker push --all-tags` with concrete runners, full source SHAs, checksums, explicit tags, and registry digest capture.
- Made every rendered workflow template pass its declared policy profile and made the repository workflow profile explicit in `.github/workflow-policy.yaml`.
- Clarified that AFDS `verification` is conditional on operational or normative rigor and may be supplied through metadata or a verification section.
- Clarified the distinction between MCP protocol compatibility allowances, SDK implementation evidence, `ai-skills` transport policy, and controlled project exceptions.

## 1.2.0 - 2026-07-28

This release adds a governed standard for designing and maintaining repository instruction systems for coding agents.

### Added

- Added `agents-md-architect` with a concise operating workflow, normative standard, repository-discovery playbook, profile and routing guidance, drift and anti-pattern guidance, and lifecycle evidence requirements.
- Added root and nested `AGENTS.md` templates that preserve canonical ownership, operating modes, architecture and safety boundaries, exact commands, and evidence-based completion.
- Added an executable validator for profile requirements, instruction length, relative links, repository-boundary escapes, blind references, placeholders, versioned current names, volatile counts, host-specific paths, generic advice, keyword-based approval, and false CI guarantees.
- Added regression tests and stable adoption rules covering scope, discovery, profiles, ownership, safety, verification, routing, nested locality, drift, and completion evidence.
- Added compositional layout and domain-profile validation, bounded English and Polish lexical contracts, and stable contract markers for other document languages.
- Added a bounded `ci-cd-architect` GitHub Actions policy auditor for evaluating untrusted workflow trees from a trusted immutable revision.
- Added a governed Husky and lint-staged profile with evidence-based package-manager selection, staged-file preservation, offline execution, and explicit CI authority.

### Changed

- Published all bundled skills as version `1.2.0` with `maturity: stable` and added the new skill to the cross-platform Python compatibility lane.
- Extended repository quality, documentation, release, and adoption contracts to treat `agents-md-architect` as a first-class governed skill.
- Hardened instruction discovery and validation for repository `bin/` entry points, ecosystem-specific build output, shared Markdown parsing, regular-file references, invalid UTF-8, bounded input trees, complete placeholder detection, and non-executing command evidence.
- Made audit and validation share one bounded instruction-tree read, enforced root topology for single and monorepo layouts, required safety contracts for router and application profiles, normalized filesystem failures, and bounded fail-closed repository and gate-source discovery.
- Hardened full ancestor directive, command, and canonical-owner inheritance; rejected invalid YAML as command evidence while charging every read to the aggregate budget; recognized subprocess and operating-system calls only after real imports at any AST depth; and declared the PyYAML runtime dependency used by the audit tool.
- Hardened fenced examples inside Markdown list containers, descriptor-bounded file reads, executable-only command evidence extraction, incremental repository enumeration, and platform-capability-preserving tests for the component-safe reader path.
- Required workflow-policy approval to execute the auditor from an immutable authority outside the assessed pull-request tree; repository-local copies are diagnostic mirrors only.
- Replaced flattened command strings with lossless `argv` comparison for completion evidence, preserved quoted task and package-script names, rejected option-like task names, and removed ambiguous package-manager shorthand evidence.
- Bound public command evidence to its source working directory, constructed discovered script entry points directly from `argv`, unified completion-fence parsing with list-aware CommonMark containers, and distinguished concrete repository paths from generic per-skill filenames.
- Added a self-hosting release contract that runs the published strict validator and repository auditor against the repository's own root `AGENTS.md`.
- Unified Codex context reads on shared component-confined I/O, removed the legacy duplicate reader, hardened exact Markdown span and recursive YAML parsing, and made policy-auditor publication and typing explicit.

## 1.1.0 - 2026-07-27

This release consolidates the complete implementation history of the branch into one production version.

### Added

- Added governed `SKILL.md`, `STANDARD.md`, and `manifest.yaml` contracts for AFDS documentation, CI/CD architecture, MCP server architecture, and MCP server consumption.
- Added Python/FastMCP and .NET MCP implementation profiles, executable server generators, migration assessments, compatibility matrices, and cross-language failure guidance.
- Added secure Python, .NET, MCP, documentation, packaging, dependency, container, Semgrep, Dependabot, and local quality-gate templates.
- Added repository-wide adoption, rule-catalog, evidence-report, and independent-approval contracts with provider-backed verification.
- Added `AGENTS.md` as the canonical repository workflow for implementation and migration agents.

### Changed

- Published all bundled skills as version `1.1.0` with `maturity: stable` after the complete cross-platform production gate passed.
- Recovered valuable knowledge from the historical repository into one canonical set of standards, profiles, references, templates, tools, and tests.
- Merged local pre-commit and pre-push guidance into `ci-cd-architect` instead of maintaining a separate incomplete skill.
- Replaced brittle fixed-layout and file-count assumptions with per-skill manifests and extensible reviewed resource categories.
- Made generated Python acceptance build and install an exact wheel in an isolated environment and made container acceptance exercise the exact image that is published.
- Added deterministic complete dependency locks, immutable action pins, exact-head CI, compatibility lanes for supported Python and .NET platforms, and retained diagnostic evidence.
- Clarified normative precedence so lower-level examples, templates, generators, and simulations cannot weaken the standard.

### Security and correctness

- Hardened AFDS metadata, CommonMark fences and code spans, inline and reference links, and explicit verification requirements.
- Made MCP consumer risk, retry, reconciliation, pagination, response parsing, and remote metadata handling fail closed.
- Required authentication and selector authorization before network-backed resolution, post-connect peer verification, trusted approval provenance, optimistic concurrency, and bounded lifecycle ownership.
- Bound evidence claims to exact argv, working directories, result bytes, JUnit identities, provider jobs, artifacts, source revisions, and independent reviewer identities.
- Rejected duplicate or contradictory JUnit identities, ambiguous result paths, incomplete commit provenance, unsafe symlinks, path traversal, and repository-external content claims.

### Removed

- Removed obsolete duplicate standards, numbered implementation aliases, temporary repair workflows, payload fragments, generated coverage databases, and migration leftovers.
- Removed unsafe legacy defaults, including new use of deprecated two-endpoint HTTP plus SSE transport and self-asserted production approval.

## Historical notes before 1.1.0

- 2026-06-06: Expanded MCP server guidance for transport, middleware, discovery, security, reliability, and production operation.
- 2026-06-05: Standardized skill metadata and strengthened documentation and CI template validation.
- 2026-06-01: Added the MCP consumer domain and deterministic decision-policy helpers.
- 2026-05-23: Strengthened CI/CD release integrity, workflow security, reliability, and dependency automation.
- 2026-05-21: Corrected CI rule identifiers and static-analysis edge cases.
- 2026-05-13: Added stricter documentation structure checks.
