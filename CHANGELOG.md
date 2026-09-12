# Changelog

## 2.1.0 - 2026-09-12

### Added

- Added `mcp-steward-architect`, a durable MCP control-plane architecture skill that composes inbound server and outbound consumer standards with receipts, reconciliation, lineage fencing, evidence authority, completion gates, recovery, and adversarial conformance tests.

### Changed

- Strengthened shared capability, evidence, exact-artifact, and verification-integrity contracts across the bundled architecture skills.

## 2.0.0 - 2026-09-11

### Added

- Added shared application contracts for layered action outcomes, runtime identity, deployment leases, audit events, and tool-result provenance so repository and MCP implementation guidance composes around one machine-readable source of truth.
- Added Capability Manifest v2 as the canonical `capability-manifest.schema.json` contract with schema version 2: explicit contract revision, async model, outcome contract, declared idempotency and reconciliation, publication semantics, bounded results, and runtime-identity advertisement, with the Python and .NET MCP generators migrated to emit the v2 manifest.
- Added cross-event audit-log semantics that enforce append-only history and reject duplicate or conflicting event identifiers, idempotency-key rebinding, conflicting terminal outcomes, and a second equivalent canonical success for the same idempotency identity.
- Added CI verification-integrity tooling for declared-dependency bootstrap, test-corpus discovery/execution accounting, runtime-exception detection, local/hosted gate parity, state-isolation preflight, and canonical verification receipts.
- Added the canonical exact-candidate MCP probe: acceptance evidence is derived from a real session through the pinned official `mcp==2.0.0` client launched against the digest-bound artifact, with client provenance receipts required by exact-candidate acceptance, transport dogfood, contract capture, the release verifier, the local candidate lane, and provider-schema compatibility; fixture- or caller-asserted session facts fail closed.
- Added seven provider-neutral runtime/API invariants to `mcp-server-architect` with positive and negative fixtures: runtime identity, diagnostic parity, actionable preconditions, managed-resource ownership, durable async progress, bounded results, and scoped health.
- Added deterministic consumer pre-mutation admission (`MATCH`, `SUSPECTED_DRIFT`, `CONFIRMED_DRIFT`, `OWNER_UNKNOWN`, `RUNTIME_STALE_OR_UNKNOWN`, `CAPABILITY_DEGRADED`) where an unknown owner blocks mutation, and authoritative delivery reconciliation in which a missing acknowledgement yields reconciliation-required instead of a speculative resend.
- Added scoped consumer health/readiness per process, transport, auth, read, and write dimension, plus typed public-identifier provenance with create→status→read referential integrity.
- Added canonical control-plane projection invariants (durable outbox, ambiguous reconciliation, managed-resource guards, identity-preserving retarget) and the agent-backed semantic façade profile with a bounded public tool surface and schema-byte budget.
- Added semantic content extraction with `EXTRACTED`/`PARTIAL`/`UNEXTRACTED`/`UNSUPPORTED_FORMAT` states and extraction provenance, so chrome-first HTML or binary payloads cannot pass as summaries.
- Added provider schema compatibility profiles validating public tool schemas against model-provider restrictions (nullable arrays/objects, unions, defaults, additionalProperties); unknown compatibility refuses optimistic capability activation.
- Added real-transport dogfooding acceptance and the reusable `mcp-gateway-release-verifier` skill with a local candidate acceptance lane, composing preflight, bootstrap, exact-artifact launch, schema, lifecycle, degraded-health, identity, execution-integrity, and cleanup phases into one bounded fail-closed receipt.
- Added the `qa-change-verifier` skill deriving risk-based LOW/MEDIUM/HIGH verification plans with exact-evidence binding, stale-simulator invalidation, and harness-versus-product failure attribution.
- Added the adversarial state-transition review playbook with executable fixture classes for stale generations, replay, timeout-after-effect, concurrent writers, tombstones, lease reuse, partial effects, and recovery on a new generation.
- Added machine-readable gate-source inventory for `agents-md-architect` so true CI/task entrypoints consume the audit budget while helper/library files remain visible without creating false source-count failures.

### Changed

- Published the bundled application/repository-authoring skills as version `2.0.0` and aligned the conformance template, README, and release metadata to one major release boundary.
- Changed agent-instruction auditing to preserve the established import/API facade while moving bounded implementation details into canonical helper modules.
- Changed verification policy to distinguish selected tests from observed execution, reject incomplete discovery/execution evidence, classify background runtime failures separately from ordinary warnings, and require merge-blocking hosted gates discovered from pull-request workflows to have a parity-policy entry with a faithful local entrypoint or explicit hosted-only rationale.
- Changed local/hosted parity validation to verify that local entrypoint, policy, and dependency references exist and that local Python entrypoints parse successfully or executable scripts are actually executable.
- Changed test-corpus and verification-receipt accounting so expired exclusions are fail-closed drift and cannot satisfy completeness; the current time is injectable for deterministic verification.
- Changed gate-source classification so an executable `scripts/*` file with a shebang is independently classified as a real task entrypoint even after rename/move and without a separate CI reference.
- Changed `agents-md-architect` to classify durable versus volatile runtime facts and to require a stable compatibility contract or a logical capability owner whenever host, version, IP, or port claims would otherwise become timeless instructions (`VOLATILE_RUNTIME_BINDING_REQUIRES_OWNER`).
- Changed repository-shared contracts to keep one canonical schema/helper owner per durable application semantic instead of parallel skill-private copies.
- Made generic adoption evidence runtime-neutral for explicitly opted-in consumer runtimes: Node/TypeScript repositories can submit provider-backed compatibility claims and exact JUnit-style testcase identities without representing those consumer runs as combinations tested by the `ai-skills` repository itself.
- Moved runtime-agent orchestration, mutable intent/session state, delegation lifecycle, diagnostic reasoning, secret-taint runtime handling, and skill distribution/runtime-consumption machinery to `opencode-stack-guides` under migration owner OSG #140; those components are not part of the `ai-skills` 2.0.0 release boundary.

### Security and correctness

- Bound deployment lease admission to the declared principal, session, target, artifact, action, argument digest, policy revision, validity window, and one-use state; a lease for one session or principal cannot authorize another.
- Strengthened verification receipts with observed-execution/completeness fields, producer-computed accounted-file counts, expiry-aware exclusions, and an executable semantic validator that recomputes corpus accounting before accepting `pass`.
- Restricted ambiguous action outcomes: an unknown side effect can no longer yield a terminal `failed` disposition; the outcome requires reconciliation or remains pending until the external effect is established.

### Dependencies

- Regenerated the committed native lockfiles for every supported platform/runtime target and moved `httpx2`/`httpcore2` from the advisory-affected 2.9.1 graph to 2.12.0, aligning the generated Python MCP package metadata with the canonical runtime lock.

## 1.4.0 - 2026-08-28

### Added

- Added `changelog-release-architect` as the canonical owner of human-facing changelog curation, repository SemVer classification, release-boundary discovery, evidence sourcing, legacy bootstrap, and idempotent release metadata updates.
- Added a history-aware release validator that derives the baseline from merge-base, detects repeated version transitions such as `1.3.0 -> 1.4.0 -> 1.5.0`, verifies aligned version mirrors, and rejects multiple release headings introduced by one release boundary.
- Added an MCP compatibility profile that maps MCP public-contract changes to repository MAJOR, MINOR, or PATCH while leaving capability/schema version semantics owned by `mcp-server-architect`.
- Added `readme-architect` as the canonical owner of evidence-backed repository README authoring, adaptive entrypoint structure, verified quick starts, public security projection, visual/accessibility guidance, and volatile-fact control.
- Added README evidence-source and change-impact playbooks, generic and server templates, a non-secret repository evidence collector, a deterministic README auditor, and focused regression tests for secret exclusion, broken links, placeholders, profile checks, and volatile metrics.

### Changed

- Made release-version selection merge-base-relative: agents calculate a target from the baseline version, reuse a target already claimed by the branch, and report scope conflicts instead of incrementing the branch version again.
- Routed repository release instructions through the new canonical skill instead of duplicating branch-iteration and single-heading policy in `AGENTS.md`.
- Extended the existing stable-version self-hosting gate to invoke the canonical history-aware validator while preserving the rule that changed stable skill contracts require a version increase.
- Published all bundled skills as version `1.4.0` and added the release and README skills to the cross-platform Python compatibility lane.
- Split AFDS README publication and structural governance from product-facing README authoring so frontmatter/confinement rules and onboarding/presentation rules have distinct canonical owners.
- Aligned generated Python and .NET MCP README templates with `readme-architect` while keeping MCP capability, transport, authorization, retry, lifecycle, and safety semantics canonical in `mcp-server-architect`.
- Registered README governance in the shared adoption rule catalog and standard-rule map and routed root repository instructions through the new skill.

### Dependencies

- Regenerated the five committed platform dev locks and the MCP generator runtime/dev locks for Python 3.12, 3.13, and 3.14 with the updated toolchain, and pinned `pip` 26.2 in the development sources to resolve PYSEC-2026-3721.
- Bumped development dependencies: `ruff` 0.16.0 → 0.16.3, `setuptools` 83.0.0 → 84.0.0, `types-PyYAML` 6.0.12.20260724 → 6.0.12.20260815, `wheel` 0.47.0 → 0.48.0, and `pip-tools` 7.6.0 → 7.6.1.

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
- Added a materialized reusable consumer-acceptance workflow, external authority binding for candidate trust locks and adoption assessments, provider-control preflight, trusted-source lock generation, and explicit no-runner evidence classification for real provider-backed adoption.
- Added an `agents-md-architect` migration-diff workflow that compares normative, validator, evidence, template, and reference surfaces before rewriting an existing canonical `AGENTS.md`.
- Added mutation outcome taxonomy for independently recording completion, returned identity, representation, and reconciliation requirements.
- Added conservative stage-local container provenance guidance and practical consumer regressions covering disposable live targets, README preservation, lifecycle separation, moving-head freshness, review freshness, reproducibility claims.

### Changed

- Reworked the container and NuGet publish templates so unprivileged validation builds and tests closed artifacts while protected publishers verify and publish them without checking out or executing candidate source.
- Replaced mutable runner labels across all workflow templates, short-SHA artifact identity, post-checkout authenticated fetches, and `docker push --all-tags` with concrete runners, full source SHAs, checksums, explicit tags, and registry digest capture.
- Made every rendered workflow template pass its declared policy profile and made the repository workflow profile explicit in `.github/workflow-policy.yaml`.
- Clarified that AFDS `verification` is conditional on operational or normative rigor: governed metadata is canonical, while a `## Verification` section is a fallback only for legacy implicit-v1 documents that have no governed metadata.
- Clarified the distinction between MCP protocol compatibility allowances, SDK implementation evidence, `ai-skills` transport policy, and controlled project exceptions.
- Hardened `mcp-server-consumer` trusted capability values with exact `CapabilityIdentity` bindings while preserving the 1.2 helper call shape: legacy unbound policy/contract inputs and `trusted_server=` remain accepted for migration compatibility, but they are fail-closed and cannot reduce risk or confer positive idempotency.
- Distinguished trusted executable provenance from trusted orchestration authority: candidate-owned immutable verifier execution is structural evidence only, while provider-backed approval requires externally pinned orchestration, candidate-lock equality, provider-control verification, exact-SHA evidence, and independent review.
- Changed `agents-md-architect` reference validation so concrete directories are valid routing targets, while concrete files remain regular-file references and placeholder/path-pattern references are not forced to exist literally.
- Strengthened live-backend mutation acceptance so operator intent is distinct from verified exclusive disposable-target identity, pre-clean is forbidden before target proof, and cleanup strategy is explicit for namespaced and non-namespaced resources.
- Separated repository implementation/merge/release state from formal provider-backed assurance/adoption state, and kept volatile PR/provider status out of durable product documentation.
- Defined a root README migration as product-entrypoint preservation rather than structural compliance alone.
- Clarified that `SOURCE_DATE_EPOCH` and related deterministic-build controls are reproducibility controls rather than evidence of byte-identical rebuilds.

### Security and correctness

- Bound external trust-lock coordinate checks, required authority paths, schema validation, and authority digest validation to one stable bounded candidate byte snapshot instead of reopening candidate-owned lock bytes between phases.
- Hardened real-consumer canary materialization so Git resolves from reviewed absolute system locations rather than inherited `PATH`.
- Added focused coverage floors for trust validators, provider controls, consumer canaries, and source-provenance inspection in addition to aggregate policy coverage.
- Made review evidence revision-scoped: zero unresolved bot threads is hygiene only, and security-sensitive final changes require a fresh exact-head adversarial/manual pass.

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
