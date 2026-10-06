# Changelog

## 3.21.0 - 2026-10-06

### Added

- Added an explicit CI dependency-lock contract that separates exact committed-lock candidate verification from deliberate mutable-upstream dependency refresh.
- Extended the canonical verification-bootstrap validator with typed candidate-verification and dependency-refresh operations, resolver/runtime/source provenance, refresh cache isolation, reviewable lock-diff semantics, and exact-versus-observational reproducibility claims.
- Added Python exact-hash guidance and regressions derived from the completed `mikrus-mcp#30` lock/refresh split.

### Security and correctness

- A newer package appearing in a mutable public index no longer constitutes candidate failure when the unchanged committed lock remains the admitted dependency identity and passes its integrity checks.
- Candidate acceptance cannot silently regenerate or rewrite dependency locks, while mutable-upstream refresh cannot claim exact reproducibility without an immutable dependency-source identity.
- Resolver cache state is excluded from refresh authority unless the refresh profile explicitly uses an isolated or disabled cache; security/vulnerability freshness remains a separate enforceable gate.

## 3.20.0 - 2026-10-06

### Added

- Added DeploymentLease schema version 2 target-generation fencing for concurrent autonomous deployment, binding an exact mutation domain, authority-issued expected-current target identity, and provider-CAS or durable broker/generation fence.
- Added a provider-neutral reference admission/reservation helper and regressions for same-domain races, independent-domain concurrency, provider revision drift, crash/restart ownership, rollback conflict, one-shot consumption, authoritative reconciliation, and bounded resulting-target audit evidence.

### Security and correctness

- Conflicting deploy, rollback, restart, promotion, or migration operations cannot race from independent stale snapshots in one mutation domain; only exact current authority plus target/fence preconditions may reach dispatch.
- Reservation consumes the one-shot lease before dispatch and survives restart; delivery-unknown state remains pressure-bearing until authoritative reconciliation, while successful mutation advances the fence so stale holders fail closed.
- Runtime identity or acceptance evidence may inform later deployment preconditions but cannot mint, widen, or refresh deployment authority.

## 3.19.0 - 2026-10-06

### Added

- Added a generation-bound mutable MCP catalog/discovery lifecycle for gateways, binding derived indexes, search caches, and discovery results to exact catalog plus search-configuration identity.
- Added a deterministic reference model and regressions for single-flight rebuilds, waiter/owner cancellation, failed or partial publication, stale caches, old-generation overwrite prevention, lazy/eager builder parity, and current invocation re-resolution.

### Security and correctness

- Discovery ranking, confidence, and stale search output remain advisory and cannot authorize invocation; selected components are re-resolved against the current catalog/source/manifest/policy identity before execution.
- Federated discovery is explicitly allowlisted and remains behind authentication/capability authorization before network-backed source resolution; health distinguishes catalog currentness, index readiness, and invocation readiness.

## 3.18.0 - 2026-10-06

### Added

- Added a provider-neutral ArtifactPublicationLease contract that binds one-shot publication authority to an exact already-proven artifact, provider/namespace/package/version/channel scope, policy/evidence identity, execution generation, and expiry.
- Added a deterministic publication authority helper and adversarial regressions for artifact substitution, scope widening, immutable conflicts, same-artifact convergence, mutable-channel movement, ambiguous provider outcomes, terminal artifact acceptance, and provider-neutral package/OCI/release-asset publication.

### Security and correctness

- Build/test, repository-write, deployment, or generic registry credentials no longer constitute autonomous publication authority; the trusted publisher requires current exact lease authority and destination state.
- The privileged publisher consumes the prepared artifact identity without checkout/rebuild/repack/load/execute authority, and timeout/conflict acknowledgements reconcile authoritative destination state before any later dispatch can receive fresh authority.
- Publication receipts preserve exact artifact/destination/lease/policy lineage while projected deployment references carry no permission to rebuild or republish the artifact.

## 3.17.0 - 2026-10-06

### Added

- Added a provider-neutral IntegrationLease contract for autonomous repository integration, binding exact principal, repository/change, candidate head/tree, target/base, merge strategy, evidence-set/policy identity, execution generation, expiry, and provider controls.
- Added a deterministic integration authority helper and adversarial regressions for stale candidate/base/evidence, child-worker authority, one-shot reservation, ambiguous dispatch reconciliation, and squash candidate-to-integrated lineage.

### Security and correctness

- Generic repository write/push credentials no longer satisfy integration authority: only a current exact lease may admit the mutation.
- Durable operation reservation consumes the one-shot lease before provider dispatch; timeout/lost acknowledgement reconciles the same operation and cannot reactivate or blindly replay authority.
- Squash/rebase/merge evidence preserves candidate and integrated revision as distinct identities and carries bounded lease/operation/evidence/policy lineage without repository credentials.

## 3.16.0 - 2026-10-06

### Added

- Added a provider-neutral persistent-context provenance contract for checkpoints, handoffs, memories, instructions, episodes, summaries, and workspace notes reused across autonomous sessions.
- Added trust classes, explicit project/principal/work scope, dependency-bound currentness, bounded permitted-influence semantics, deterministic fresh-session assembly, and an executable poisoning/currentness reference helper.

### Security and correctness

- Persistence cannot grant authority/capabilities, change policy, waive verification, or promote advisory/untrusted prose into required evidence merely because it survived across sessions.
- Subject/runtime/environment/policy generation drift makes dependent context stale or unknown; cross-project/cross-principal reuse requires explicit scope compatibility and lower-trust content cannot override current higher-trust facts.
- Conformance requires bounded provenance/refs rather than private chain-of-thought or raw transcripts, and native product stores remain decentralized behind opaque storage/content references.

## 3.15.0 - 2026-10-05

### Added

- Added a provider-neutral projection field ownership contract for writable external projections, distinguishing canonical-owned, external-advisory, shared-managed-region, external-execution, and unknown field semantics.
- Added least-privilege external automation grants scoped by field/action (and external region for shared fields), explicit executor/environment identity for work-starting metadata, bounded provider-confidence/rationale audit evidence, drift taxonomy, and scheduler fencing against duplicate canonical work.

### Security and correctness

- Provider confidence, rationale, suggestion state, or coarse auto-approval thresholds are evidence only and cannot grant canonical authority or side-effect admission.
- Shared-field reprojection updates only declared canonical-managed regions while preserving admitted external enrichment; unknown fields and externally started work fail conservative until classified/reconciled.

## 3.14.0 - 2026-10-05

### Added

- Added a provider-neutral source-qualified MCP gateway identity and re-export contract for tools, prompts, resources, resource templates, and extension-owned references, with deterministic bounded gateway identities and exact upstream source/manifest provenance.
- Added collision-safe gateway identity helpers and adversarial fixtures for equal/normalized names, case and truncation collisions, overlapping resource URIs, source removal/re-registration, explicit prompt composition, arbitrary JSON-schema shapes, and minimized stdio child environments.

### Security and correctness

- Gateway resolution now fails closed on stale, ambiguous, colliding, or unhealthy exact-source mappings instead of using registration order, first-wins, silent dropping, or same-name fallback.
- Gateway-owned subprocess fixtures explicitly minimize inherited host environment so ambient tokens and unrelated source credentials are not propagated by default.

## 3.13.0 - 2026-10-05

### Added

- Added a provider-neutral executable-resource contract to `skill-architect` so bundled `library_helper`, `agent_cli`, `host_adapter`, and `service` resources can declare one canonical invocation boundary, structured/human/internal outcome semantics, process-exit mapping, side effects, replay behavior, network/credential needs, timeout/cancellation, and bounded diagnostics.
- Added an executable-resource JSON Schema, manifest auditing, self-hosted declarations for the three bundled `skill-architect` CLIs, and regressions for CLI-vs-library confusion, unbounded diagnostics, unconfined resources, and reconciliation-before-retry mutation.

### Changed

- New skill manifests scaffold an empty optional `executable_resources` declaration while pre-contract skills migrate incrementally only when a supported executable boundary is created or materially changed; a file under `tools/` is not implicitly a public CLI.
- Kept runtime installation/invokability and validation-environment proof outside the portable skill declaration so host readiness and evidence provenance remain owned by their existing contracts.

### Security and correctness

- Stateful external mutation resources must declare replay/reconciliation semantics and bounded safe diagnostics; transport failure does not become implicit replay authority.

## 3.12.0 - 2026-10-05

### Added

- Added provider-scoped external binding identity for MCP control planes so canonical identity, complete provider namespace, external resource identity, and recovery locators remain distinct and collision-safe.
- Added durable provider/source-scoped event-ingress receipts and reference invariants for duplicate, out-of-order, concurrent, moved-binding, marker-collision, and restart-after-receipt reconciliation.

### Security and correctness

- External event arrival, timestamps, local resource numbers, and recovery markers cannot grant canonical transition authority or global uniqueness; trusted adapters/policy must supply scope, current-state evidence, and per-resource fencing before mutation.

## 3.11.0 - 2026-10-05

### Added

- Added AFDS executable behavior/acceptance contracts as a specialization of the existing `contract` type, with stable obligation/criterion references, observable acceptance criteria, failure-path coverage, compatibility effects, and verification mapping that keeps mutable results in their owning evidence systems.

### Changed

- Distinguished accepted decision authority from implementation completion and made material implementation, migration, rollout, rollback, cleanup, verification, and downstream-review consequences explicit before a decision may be represented as fully implemented.

## 3.10.0 - 2026-10-05

### Added

- Added five provider-neutral MCP runtime adoption rules for stable expected-failure contracts, exactly-one async terminality, replay-blocking unresolved idempotency, semantic operation/idempotency/correlation/causation/trace identity separation, and trusted unexpected-exception diagnostics.
- Added executable runtime invariant helpers and adversarial regressions for EOF/disconnect/wait cancellation without terminal state, conflicting or replayed terminal outcomes, stale post-terminal progress, unresolved idempotency cleanup, conservative recovery disposition, malformed progress events, and public-versus-trusted exception diagnostics.

### Changed

- Extended `mcp-server-architect` from seven to twelve production runtime/API invariants and made failure classification distinct from policy-selected recovery disposition.
- Clarified that internal Result/exception/envelope representations do not define the MCP wire contract, and that durable operation handles obey the same terminality rules as long-lived progress streams.

### Security and correctness

- Generic TTL/maintenance cleanup can no longer convert `in_flight`, `indeterminate`, `unknown_outcome`, or `reconcile_required` side effects into replay permission; unknown failures do not default to retry and ambiguous stateful effects require reconciliation or a more conservative governed disposition.
- Unexpected exception cause and stack remain available only at the trusted operator-diagnostic boundary, correlated to the public operation, while public/durable failure records stay sanitized and exception-object free.

## 3.9.0 - 2026-10-05

### Added

- Added a provider-neutral migration-acceptance evaluator that binds the exact candidate, current schema, supported and unsupported input states, immutable fixture identity, production migration entrypoint/revision, data invariants, interrupted-recovery evidence, and bounded exercised-input ref/kind/schema identities.
- Added adversarial regressions for accidental current-bootstrap setup, wrong migrator identity/revision, missing supported predecessors, silent unsupported-state normalization, unsupported recovery substitution, and conditional current-schema rerun.

### Changed

- Extended `qa-change-verifier` with a normative persistent-schema migration matrix that keeps fresh installation, legacy upgrade, optional current-schema idempotence, unsupported input, and interrupted recovery as distinct proof cases.
- Extended the MCP local candidate lane to derive migration scope from exact-candidate-bound trusted admission evidence backed by a validated immutable change-acceptance contract, then evaluate raw migration evidence through `qa-change-verifier` and accept only the canonical in-process receipt when a required migration obligation is admitted; missing/invalid scope and contradictory payloads fail closed.

### Security and correctness

- Legacy-upgrade evidence now fails closed when the pre-state is already current, required legacy/current-absence characteristics are unproven, the wrong production migrator is exercised, representative data invariants are absent, or a known/unknown unsupported state is normalized into apparent success.
- Recovery evidence from an unsupported input or current-schema no-op path can no longer satisfy the recovery obligation for a mutating supported migration, and interrupted legacy cases must still prove their exact legacy pre-state.
- Migration policy switches are now separated from raw evidence: the MCP lane requires identity-bound policy/admission provenance for candidate scope, always requires interrupted-recovery proof for migrations, sources current-rerun applicability from that trusted scope, and preserves the exact production migrator entrypoint/revision in its bounded receipt.

## 3.8.0 - 2026-10-04

### Added

- Added automatic post-integration release finalization for repositories that explicitly declare it: a successful integration gate can now drive a protected tag/provider-release/package flow without a second conversational confirmation.
- Added an ai-skills GitHub Release workflow that consumes successful `CI` runs on `main`, prepares an exact source archive and checksum without publication authority, then creates or converges the exact `v<version>` tag, GitHub Release, `ai-skills-<version>.tar.gz`, and `SHA256SUMS` from a separate protected publisher.

### Changed

- Changed `changelog-release-architect` so `automatic-after-integration` publication is part of release completion rather than an opt-in follow-up; merged-but-unpublished release boundaries remain incomplete or explicitly blocked.
- Changed CI concurrency identity so pull-request runs may still supersede stale runs while each `main` push has a distinct concurrency key, preventing a later integration from cancelling the CI evidence needed to release an earlier version.

### Security and correctness

- Automatic publication binds to the exact integrated SHA and a successful provider CI run, validates the release transition again, keeps repository checkout/package construction out of the write-authorized publisher, and fails closed on tag or asset digest conflicts.
- Release retries are idempotent only after proving an existing tag resolves to the same integrated commit; package assets are revalidated against the prepared SHA-256 before completion.

## 3.7.0 - 2026-10-04

### Added

- Added a provider-neutral structured diagnostic-egress contract and reference constructor that emit only trusted typed reason/category/severity data plus policy-allowlisted bounded fields, with a fixed fail-closed fallback for unknown or unsafe classifications.
- Added adversarial regressions for internal apostrophes and nested/escaped quotes, provider wording drift, embedded source/template fragments, multiline and Unicode/control input, nested and long errors, secret-looking and ordinary values, single-token payloads, and protected stderr/receipt/summary sinks.

### Changed

- Extended MCP server and QA semantic-review guidance to consume one repository-level diagnostic-safety owner, require source/provider payload exclusion from broader-trust sinks, and keep optional raw forensic detail behind an opaque narrower-authority reference.

### Security and correctness

- Diagnostic field values are now admitted by policy-owned value classes rather than syntax alone, preventing source/provider payload that happens to look like a valid identifier token from crossing the diagnostic boundary.
- Unknown wording, classifier failure, invalid provenance, unapproved values, forged fallback metadata, and free-form diagnostic members fail closed without copying raw source/provider text.

## 3.6.0 - 2026-10-04

### Added

- Added a provider-neutral exact artifact evidence contract and reference constructor with collision-safe length-prefixed file-tree framing, explicit construction-profile identity, and bounded `exact|partial|unknown` coverage.
- Added regression coverage for delimiter-framing collisions, large supported artifacts, file/byte/depth/time limits, requested-versus-observed fallback identity, and construction-profile freshness.

### Changed

- Extended CI/CD verification receipts and guidance so exact artifact identity is distinct from requested package/source/runtime compatibility, non-exact coverage cannot publish an exact digest, and candidate-defined exclusions cannot shrink the v1 evidence subject.

## 3.5.0 - 2026-10-04

### Added

- Added a repository-level immutable change-acceptance contract for stable obligations, falsifiable criteria, deterministic proof-class mapping, exact-candidate evidence, and explicitly authorized policy waivers.
- Added a semantic review plan contract for exact candidate/base-scoped flows, focus areas, analogous paths, invariant matrices, negative-space review, and diagnostic-egress risk families.
- Added qa-change-verifier regressions for missing, stale, vacuous, deferred, provider-unfaithful, and non-exercised evidence, plus known-gap authority and semantic-review-plan freshness.

### Changed

- Extended qa-change-verifier's risk planner without breaking risk-only callers so required criteria can add specific proof layers and semantic-review requirements without weakening obligation-kind proof minimums, while preserving harness-versus-product failure attribution.
- Hardened acceptance evidence binding so blank candidate identities fail closed, exact-artifact proofs require current artifact bindings, semantic-review evidence is tied to the exact validated review-plan digest, hard FAIL evidence is authoritative only after required proof identity, proof-of-exercise, and provider-fixture fidelity validation, and acceptance consumes complete candidate/contract-bound known-gap registry snapshots whose full records cannot be replaced by caller-supplied gap semantics; malformed validator roots, path sets, snapshot/evidence/policy/runtime boundary shapes, and load-bearing/unknown gaps without criterion scope now fail closed.
- Aligned QA helper validation with the published contract schemas for schema-version typing and string bounds, made supplied base identity bidirectional/fail-closed, and validated primary/analogue review paths against concrete known repository paths through final acceptance.

## 3.4.0 - 2026-10-04

### Added

- Added machine-readable production-producer and gate reachability declarations for MCP Steward state machines, including explicit work-admission, mutation-admission, evidence-promotion, and completion-publication producer paths.
- Added the canonical `steward-checkpoint` contract for generation-fenced artifact identity, exact semantic dependency bindings, upstream checkpoint artifact bindings, and recovery-critical subject, authority, ownership, progress, budget, deadline, blocker, and external-operation state.
- Added deterministic checkpoint planning that derives reusable and stale artifacts, reason codes, the earliest safe resume stage, and the minimum recomputation set without replaying model transcript state.
- Generated Python and .NET Steward runtimes now durably persist canonical checkpoint bindings and artifact payloads, expose deterministic `resumePlan` projections, restart from persisted state without transcript replay, and recompute only checkpoint closure affected by changed semantic dependencies.

### Changed

- Extended MCP Steward state-machine v2 with explicit non-terminal liveness/convergence semantics and fail-closed producer coverage while retaining validation support for existing state-machine v1 documents.
- Extended Steward acceptance revision 2 so closure claims require real producer success/rejection paths, liveness closure, canonical checkpoint reuse, minimum recomputation, and transcript-independent restart behavior.
- Strengthened Steward evidence/recovery guidance so late-stage outages do not invalidate unrelated current earlier evidence, while changed load-bearing dependencies and older workflow generations invalidate only the affected checkpoint closure.

### Security and correctness

- A test-only state construction can no longer stand in for a real production producer path, and non-terminal states without an owner, wake-up, recoverable external operation, reconciliation path, or authorized blocker fail conformance.
- Checkpoint reuse fails closed on generation, machine, dependency-set, exact upstream artifact, or canonical binding drift, preventing stale work from being adopted by a newer workflow generation.
- Completion-candidate reuse now revalidates referenced evidence against the current clock, so evidence that expires between checkpoint sealing and restart forces only completion-stage recomputation and cannot produce a stale terminal handoff.

## 3.3.0 - 2026-10-03

### Added

- Added `skill-architect` as the canonical owner of reusable Agent Skill admission, routing, progressive disclosure, resource selection, portability, behavioral evaluation, migration, and deprecation.
- Added deterministic skill-package auditing and minimal scaffolding, plus a portable routing/behavior eval schema and representative repository-level `skill-architect` corpora.
- Added trigger-safe progressive-routing audit markers and representative `agents-md-architect` routing/behavior eval corpora for orphan, duplicate, extraction, transition-time, negative-routing, and discover-before-invoke regressions.

### Changed

- Extended `agents-md-architect` with owner-first knowledge placement, pre-load stubs, transition-time routing, platform-aware trigger ownership, and canonical invocation discovery before trial execution.
- Generalized CI verification-corpus completeness beyond test-file discovery: policies can declare exact required governed subjects that remain expected when deleted or missed by discovery heuristics, with an explicit governed accounting profile and expected/discovered/exercised/missing evidence kept complete.
- Strengthened protected-release workflow auditing so authority-bearing publisher jobs reject candidate checkout/materialization, rebuild/package, image load/import, candidate execution, shell-continuation bypasses, known build actions, and opaque reusable-workflow delegation while preserving registry-native exact-digest promotion.
- Made skill descriptions an explicit pre-load routing contract, kept development evidence such as eval corpora, benchmark reports, and changelogs outside published runtime skill packages, and separated deterministic corpus validation from provenance-bound model observations.
- Allowed skills without executable helpers to declare an empty `dependencies.tools` list while keeping tool-bearing skills inside the existing quality, typing, security, and coverage gates.
- Synchronized all bundled stable skill version mirrors to `3.3.0` for this combined unreleased boundary.

### Security and correctness

- Protected publication validation mechanically rejects supported candidate materialization/execution surfaces before publication authority can be used.
- Required validation subjects cannot disappear from a green governed-corpus receipt when the filesystem or discovery heuristic stops returning them.

### Dependencies

- Pinned the existing transitive security-sensitive dependencies to PyJWT 2.15.1 and urllib3 2.8.0, replacing advisory-affected PyJWT 2.13.0 and urllib3 2.7.0 in the regenerated development locks.
- Bumped development tooling and regenerated the five committed native development locks: `build` 1.5.0 → 1.6.1, `mcp` 2.0.0 → 2.2.0 (with `mcp-types` 2.0.0 → 2.2.0), `mypy` 2.3.0 → 2.3.1, `pip` 26.2 → 26.2.1, and `ruff` 0.16.3 → 0.16.9.

## 3.0.0 - 2026-09-13

### Added

- Added `mcp-steward-architect`, the canonical durable MCP control-plane architecture skill composing inbound MCP server and outbound consumer standards with receipts, reconciliation, lineage fencing, evidence authority, completion gates, recovery, and adversarial conformance tests.
- Added the Steward v3 Design Pack with machine-readable state-machine, mutation-policy, proof-recipe, capability, acceptance, candidate-identity, claim-binding, cancellation, recovery-equivalence, and layered acceptance contracts.
- Added explicit Work Admission, Mutation Admission, Evidence Promotion, and Completion Publication gates with typed fail-closed outcomes and atomic regression coverage for ambiguous delivery, stale publication, and credential failover.

### Changed

- Upgraded the generated Python and .NET Steward baselines from sidecar examples to durable recovery-oriented workflow seeds with semantic MCP controls, exact-candidate evidence/completion/handoff binding, bounded progress/deadline state, and stateful cancellation reconciliation.
- Strengthened shared capability, evidence, exact-artifact, and verification-integrity contracts across the bundled architecture skills.
- Synchronized all bundled stable skill version mirrors to `3.0.0` because the release changes shared repository contracts and the definition of Steward conformance.

### Security and correctness


- Stateful submit and cancellation effects now require durable pre-dispatch identity and reconcile-before-replay after ambiguous delivery; stale generations and stale candidates cannot publish actionable handoffs.
- Evidence promotion now requires approved producer, claim/criterion binding, exact subject/candidate identity, freshness, coverage, and authority before completion, while unknown or missing observations remain non-claims.

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
