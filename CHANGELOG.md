# Changelog

## 3.33.0 - 2026-10-27

### Added

- The repository-level `contracts/` directory gained the provider-neutral `ReviewReceipt` v1 contract (`review-receipt.schema.json`) and its evaluator (`review_receipt.py`), resolving issue #93. One bounded receipt is the semantic-review evidence for exactly one candidate: it binds subject identity (repository, full candidate SHA, base revision, input manifest digest), reviewer provenance with a separately attested independence declaration, the review policy/rubric/review-plan identity, predeclared per-criterion outcomes with `pass`/`fail`/`unknown`/`not_applicable` verdicts, review-input coverage (access mode, reviewed-through SHA, changed-file manifest, required-context completeness), the provider operation lifecycle, and durable finding state with stable finding identities and generations.
- Hard review-safety invariants are enforced fail-closed and regression-tested. Provider operation completion is lifecycle terminality only and never becomes semantic approval: a provider refusal, outage, or quota block is terminal for the operation but non-green for a required review gate, `ack_unknown` stays explicit, and `completed` without review content cannot approve. Required missing or `unknown` criteria, incomplete or summary-only input coverage, implementer-selected evidence, non-terminal provider operations, and self-declared or unattested independence can never yield a policy-green verdict; an issued `approve` that contradicts the receipt's own required criteria or open blocking findings is a typed rejection rather than a silent downgrade. Confidence scores are diagnostic metadata and can never satisfy a required criterion.
- Exact-candidate freshness is mechanical: `review(C1)` does not approve `C2`, and currentness invalidates independently across candidate SHA, repository, policy revision, rubric digest, review-plan digest, input manifest digest, and base revision — tree equality never transfers an approval across commit SHAs. Historical receipts remain queryable after a candidate change while reporting `NOT_CURRENT` for the new candidate, and `UNKNOWN` current values produce `NOT_PROVEN` instead of optimistic reuse.
- Reviewer independence is a declaration plus a separately attested authority class (`none`, `self_declared`, `orchestrator_attested`, `independent_authority`) with an explicit compatibility relation: the reviewer's own declaration never satisfies an orchestrator or independent-authority floor, provider or model diversity alone does not prove independence, and trusted review policies can raise the required attestation floor for implementer-controlled orchestration contexts. Findings carry stable identities, severity, generation watermarks, and explicit states (`open`, `resolved_by_candidate`, `waived_by_authority`, `superseded`, `non_blocking`); resolution must bind the reviewed candidate revision, waivers require a durable reference and non-implementer authority, and a resolved provider thread never resolves a finding by itself.
- Composition refuses internally contradictory approvals, receipts carry a re-derivable payload digest plus a canonical finding-ledger digest, and `verify_receipt` re-derives the gate verdict under a trusted review policy so a structurally valid, digest-consistent forged approval is a typed finding. The reviewer's issued verdict can only lower the derived gate, never raise it. Malformed, over-long, wrong-typed, or duplicate-keyed receipts fail closed as findings instead of exceptions, and receipts remain bounded — raw review transcripts stay referenced, never embedded. `qa-change-verifier` projects the receipt as the downstream evidence artifact of its semantic review plan.

### Fixed

- The locked development dependency set for the audited Linux/Python 3.12 target now pins `msgpack==1.2.3` (via `requirements-dev.in`), resolving CVE-2026-114613 reported by the dependency audit against the previously locked `msgpack==1.2.1`. The pin is a freshness fix independent of the ReviewReceipt scope; other platform locks are unchanged.

### Compatibility

- New standalone contract with no upgrade path concerns: existing repositories adopt it by referencing `contracts/review-receipt.schema.json` and `contracts/review_receipt.py`. Consumers that pinned the `qa-change-verifier` manifest now also declare the two new shared resources.

## 3.32.1 - 2026-10-26

### Fixed

- `runtime_acceptance` closes three acceptance-integrity defects found in post-release review of the 3.32.0 receipt contract. Cross-runtime proof reuse: a required proven proof was bound only to the instance-generation label, so evidence collected on runtime A could accept runtime B whenever the two runtimes shared a generation label; proven required proofs now bind to the observed `runtime_id` as well (schema `proofs[].runtime_id`), and unbound or mismatched runtime bindings are typed rejections. Complete profile currentness: the dependency snapshot carried only the profile revision, so two different profiles sharing a revision adjudicated as current; the snapshot now binds the full canonical profile identity (`acceptance_profile_id` and `acceptance_profile_digest`, schema-required) and any difference is STALE. Deployment-target currentness: `adjudicate_current` ignored the deployment identity, so an acceptance for deployment A stayed green against a fresh observation of deployment B sharing artifact, runtime id, and generation; the snapshot now binds the observed `deployment_identity`, observation binding rejects a disagreeing deployment, and currentness treats a deployment change as STALE.
- Observation composition converts merged timestamps to UTC before the `Z` suffix, `derive_currentness` never lets an unavailable comparison mask a demonstrable dependency change, generation binding applies only to proven required proofs, trusted verification compares the declared profile id/revision and policy revision with the trusted profile, receipts serialize observation provenance references, composition self-checks against the published schema, and typed reason overflow raises instead of truncating.

### Compatibility

- Receipts composed by 3.32.0 evaluators fail closed under 3.32.1: the receipt schema now requires the runtime and deployment bindings and the complete snapshot identity, and proofs without a runtime binding are typed rejections for binding-required profiles. No silent upgrade path exists by design; recompose receipts with a 3.32.1 evaluator.

## 3.32.0 - 2026-10-26

### Added

- The repository-level `contracts/` directory gained the provider-neutral `RuntimeAcceptanceReceipt` v1 contract (`runtime-acceptance-receipt.schema.json`) and its evaluator (`runtime_acceptance.py`), resolving issue #97. One bounded receipt composes caller-supplied expected deployment identity with independently observed runtime identity, per-proof obligations, and mechanically derivable staleness. Hard invariants are enforced by the evaluator and tested: an expected artifact digest never manufactures an observed one; artifact version is never silently promoted to a runtime instance generation; a healthy process running the wrong artifact, a failed required readiness or action-class proof, or a required `unknown`/`unsupported` proof can never yield acceptance, while an unsupported optional proof stays an explicit gap that does not block an unrelated profile.
- Proof evidence keeps typed authority classes (`caller_claim`, `worker_report`, `provider_ack`, `qa_deterministic`, `model_review`, `independent_observer`) with an explicit compatibility relation: a model review can never satisfy a deterministic-QA floor, and only an independent observer satisfies an independent-observer floor. An acceptance profile may declare a minimum authority per required proof kind; a proven claim below that floor, or a proven claim without an evidence reference, is a typed rejection rather than an automatic upgrade. Conflicting independent observations of the same target fail closed during composition, and composition preserves the source observation provenance references.
- Receipts bind their exact evidence input set through an order-insensitive `evidence_set_digest` and a structural `payload_digest`, both re-derivable by `verify_receipt`; every proof evidence reference must belong to the declared evidence input set. Required proofs are bound to the observed runtime instance generation, and the receipt target must agree with the evaluated expected/observed deployment identity. The receipt records the complete acceptance profile through a canonical profile digest, the issued typed `reason_codes`, and per-proof `runtime_generation` bindings, so downstream consumers can see which policy produced the verdict and why non-green outcomes occurred.
- `verify_receipt` distinguishes structural integrity checks from authoritative acceptance verification: supplying a trusted acceptance profile makes it re-derive the issued verdict, reason codes, and dependency snapshot from the receipt's own identities under that profile, verify the receipt target against the evaluated expected and observed deployment identities, compare the declared acceptance-profile and policy identities with the trusted profile, compare every serialized proof `required` flag with the trusted profile's obligations, and tolerate an absent deployment identity when a profile explicitly disables target binding — a structurally valid forged acceptance is a typed finding, because the payload digest binds content without authenticating the decision. The dependency snapshot binds the observed `runtime_id` alongside generation, configuration, artifact, and source identity, and a demonstrable dependency change is STALE even when another current value is unavailable. Adjudication combines an issued verdict with currentness and expiry into `ACCEPTED`, `REJECTED`, `INCONCLUSIVE`, or `STALE`, requires timezone-aware inputs, and separates the authoritative `adjudicate_current` path — which requires a real current observation, a positive freshness window, and clock-skew-bounded future tolerance, yielding STALE for over-aged evidence — from the explicitly non-authoritative dependency-only `adjudicate` helper, so post-rollback recovery always requires fresh generation-bound evidence. Optional clock provenance preserves source timestamps, offsets, and normalization; a naive source clock can never silently claim exact UTC evidence. Observation composition converts merged timestamps to UTC, preserves the identity reference of every contributing observation alongside their declared provenance references, and receipts serialize those provenance references. Generation binding applies to proven required proofs; unproven obligations keep their own typed reasons. Composition validates its output against the published schema and refuses to silently truncate decision reasons.
- Two reference acceptance profiles are regression-tested: `managed-skill-distribution`, where installed-artifact identity plus deterministic helper behavior satisfy the profile without model behavior proof, and `runtime-service`, where source/artifact/config identity, readiness, and action-class observations from an independent observer are load-bearing.

## 3.31.0 - 2026-10-24

### Added

- `mcp-gateway-release-verifier` now separates diagnostic composition from authoritative release acceptance. `compose_release_receipt` keeps composing caller-supplied phase results and marks its receipt `authority: "diagnostic"`: a `pass` verdict there means the aggregate is well formed and bounded, never that release authority was proven. The new `compose_release_acceptance` requires every phase accepted as `pass` — required and extension — to carry a typed `PhaseEvidenceBinding` whose provider-backed execution record an injected authority independently resolves against the exact candidate revision. Missing, unknown, unsupported, cross-candidate, stale, policy-mismatched, or unresolvable provenance yields a non-green receipt with typed failure reasons instead of a trusted PASS. The probe client receipt is now validated through the owning `mcp-server-architect` exact-candidate acceptance contract, removing the weaker second interpretation that accepted a checksum of caller-controlled fields as proof of a real client session.
- The local candidate lane now derives migration scope from a verified admission authority. A caller-constructed `TrustedCandidateScopeBinding` is only a claim: the lane requires an injected admission authority to independently resolve the admission record identified by the binding source and confirm the exact candidate revision, acceptance-contract digest, and policy revision. An absent authority, an unresolvable record, or a policy-revision mismatch between the lane and the binding is non-green, so a syntactically valid `:sha256:...` source string can no longer waive migration or current-rerun obligations. The canonical `qa-change-verifier` migration evaluator and its in-process receipt issuance are unchanged.
- `mcp-server-architect/SKILL.md` gained an explicit conditional handoff: release acceptance requested or required by policy loads `mcp-gateway-release-verifier` after the owning canonical probes run; routine implementation and exploratory inspection do not preload verifier references. The dependency direction stays acyclic — the verifier consumes architect outputs and never redefines them.
- The release-verifier manifest now declares both tools as `library_helper` executable resources, matching the real execution surface: they are reached through the owning workflow, and no command-line entry point is advertised.

### Changed

- `mcp-gateway-release-verifier/STANDARD.md` states the trust-root invariants for release evidence: the trust root is independent of the candidate and its author, every accepted phase binds the same exact candidate and artifact identity, evidence carries typed producer/authority/execution/policy identity, missing or unresolvable provenance is non-green, a local agent cannot issue its own trusted validation receipt, and a PASS receipt grants no merge, publication, or deployment authority.

## 3.30.2 - 2026-10-24

### Fixed

- The commit-authorship audit and the complete local gate now execute on the publication path. The `exact-head` job ran only for `pull_request` events, so a push to `main` concluded CI with the audit skipped, and the automatic release accepted that concluded run as a successful validation of a revision whose commit identities were never checked. The job now runs for both events: a pull request is audited against its recorded base, and a push is audited against the branch state the provider recorded before the push. A base that is missing, malformed, or the zero SHA of a branch creation fails closed instead of silently auditing nothing, and a merge commit in a pushed range fails closed because the integration policy is squash-only linear history. The audited base is still fetched from the provider, so a base the provider cannot serve cannot be audited.
- Release admission now proves the mandatory audit executed. The release workflow accepted `workflow_run.conclusion == 'success'`, which a skipped audit job also produces, so a revision whose integration audit never ran could be published. The release prepare job now reads the provider's own record of the triggering run and requires that the run is the `CI` workflow, is a push, carries exactly the published revision, and that the `exact-head` job concluded `success`. A skipped or neutral audit blocks publication instead of being promoted to an executed check.

### Changed

- `check_commit_authorship.py` gained `--forbid-merge-commits` for the push path, where the audited range is the integration branch's own history. The pull-request path keeps excluding merge commits from the identity listing, because a squash merge never carries the pull request's internal topology onto the integration branch; commits hidden behind a merge remain audited on both paths.

## 3.30.1 - 2026-10-22

### Fixed

- The verification scheduler no longer reuses evidence whose contract identity or expiry it could not check. A receipt bound to an acceptance contract qualified as reusable when the caller supplied no current contract digest, and a receipt carrying an expiry qualified when no current time was supplied, so evidence produced under another or unknown contract and evidence whose freshness was unverifiable entered the reuse path. Missing identity now fails closed: both shapes are stale and the node is re-run, while properly qualified reusable receipts are preserved.
- The verification scheduler no longer charges the admitted execution window for nodes it cannot legally dispatch. The admission loop consumed budget while walking the candidate order before prerequisite parking was propagated, so a deferred dependent spent budget behind a parked prerequisite and an independent sibling could be parked after it. Admission now skips nodes whose prerequisites are parked, pending, or deferred, charges only executable admitted nodes, and re-propagates deferrals after parking.
- The verification scheduler no longer raises on malformed typed input. The validator dereferenced `discriminates_between`, `required_before`, `invalidates_on`, and `exclusive_resource_class` before recording their input-shape findings, and graph traversal iterated raw `depends_on`, so a non-sequence field produced an uncaught exception instead of bounded typed findings with zero dispatch. Shape validation now precedes every dereference and traversal consumes only validated strings.
- The dependency locks for the four non-native targets now select `opentelemetry-api` 1.45.1, matching the constraint the 3.30.0 requirement declared, so the published vulnerability fix is effective on every supported target instead of only the target whose lock was regenerated locally. The generated MCP server runtime lock input carries the same constraint, so every committed lock family selects a non-vulnerable OpenTelemetry version.

### Changed

- Correction: the 3.30.0 section described the scheduler regression matrix as covering twelve scenarios; the shipped suite covers the twelve required counterexamples plus input-shape and evidence-identity regressions added by this release.

## 3.30.0 - 2026-10-22

### Added

- `qa-change-verifier` now provides a deterministic, dependency-aware cost-ordered verification scheduler and minimum rerun planner in `tools/verification_schedule.py`. The planner composes with the existing risk planner and composes with `ci-cd-architect` gate integrity to derive execution order and the minimum rerun set from declared evidence dependencies rather than a fixed checklist.
- New normative section "Verification scheduling and minimum rerun" in `qa-change-verifier/STANDARD.md` with typed scheduling decisions (`RUN`, `REUSE_CURRENT`, `DEFER_UNTIL_DEPENDENCY`, `NON_DISPATCH`, `BLOCKED_UNKNOWN`), evidence reuse rules, invalidation propagation, provider-availability separation, operation admission with trusted duration profiles, and release-worktree preflight.
- `ci-cd-architect/STANDARD.md` and `references/verification-integrity.md` extended with local/hosted gate roles, worktree/committed evidence identity, preflight versus immutable final proof, and the composition with the qa-change-verifier scheduler.
- Comprehensive regression test matrix in `tests/test_verification_schedule.py` covering 12 required scenarios including cheap prerequisite failure blocking expensive gates, focused failure deferring full gates, exact-candidate final gate invalidation on candidate change, provider outage preserving current evidence, minimal invalidation closure, stale base detection, window admission with unknown duration, malformed input rejection, release-worktree preflight, environment/contract/expiry reuse guards, caller-supplied pass text rejection, stable ordering under permutation, and provider status changes without redundant validation.

### Changed

- `qa-change-verifier` skill description and routing updated to include cost-ordered scheduling and minimum rerun planning.
- `qa-change-verifier` manifest now requires `tools/verification_schedule.py`.
- `scripts/quality_targets.py` includes the new module in type-checking and policy coverage targets.

## 3.29.6 - 2026-10-21

### Fixed

- The refactor-preservation checker no longer reads a comment marker inside a quoted attribute value as a comment opener. A `<!--` inside a double-quoted or single-quoted attribute value of a tag inside an active raw HTML block opened a comment, so the rest of the block was masked and a requirement after the correctly closed block was reported as lost. One quote-aware scan now decides the comment bodies, the quoted attribute values and the block elements together, and it carries the open tag, the open attribute value and the open comment across lines, so a marker inside an attribute value is literal text while a real comment still masks the requirement it contains.
- The refactor-preservation checker no longer lets a tag inside a comment end a raw HTML block, and no longer counts a closing tag that sits inside an attribute value which spans lines. A candidate could move a reviewed requirement into a raw HTML example, close the block early with a commented-out or a quoted closing tag and have the requirement certified as operative. The comment bodies and the quoted attribute values are now skipped before the block elements are counted, so a tag inside either of them is literal text and cannot end the block. An equals sign that ends a line still opens the attribute value on the next line, so a value whose delimiter is split from its equals sign keeps protecting its content as well, and a nested element whose opening tag spans lines is counted when that tag closes, so its closing tag cannot end a block that was never opened.
- The refactor-preservation checker no longer reads a comparison operator as a tag. A tag name follows the opening angle bracket directly, so "< b" in an example is prose; it was carried as markup, and the closing tag of the block was then counted from the wrong place, so the block never ended and every requirement after it stayed masked.
- The refactor-preservation checker no longer accepts a tag name that merely starts with the tracked name. The old pattern ended the name at a word boundary, and a word boundary also falls before "-", ":" and ".", so "</div-other>", "</div:other>" and "</div.foo>" were read as the closing tag of the block element; the block then ended early and the requirement it was meant to mask was promoted to an operative instruction, so a candidate was certified as preserving an obligation the document no longer shows. Only an allowed tag-name delimiter may follow the tracked name now, and the tracked list of block elements decides which element opens a block, so an element whose name only starts with a tracked name is another element. The defect was present in the previous release as well.
- The refactor-preservation checker now recognises the opening tag of a raw HTML block that follows a real comment on the same line, and reads the quoted attributes of that tag as part of the tag. The comment is removed first, so a marker inside an attribute value of the opening tag is literal text instead of opening a comment that masks the requirement after the block.
- The refactor-preservation checker now carries a comment that is still open when a raw HTML block ends into the surrounding prose, so it keeps masking the text it covers instead of being dropped with the block.
- The dependency lock check now reports the compiler's own diagnostics when a lock cannot be regenerated, instead of swallowing them, so a failed compilation states why it failed. The verdict is also recorded before the regenerated lock is emitted, and an emission directory that would write over a committed lock is refused, so a check can no longer be run against the content it just replaced.
- The Windows generator locks recorded their own output path with the native separator of the machine that produced them, so they were not the locks the repository's generator produces and no gate had ever said so. They are regenerated by the repository's generator on the Windows runner and now record the same relative paths as every other declared target.
- The dependency locks are now verified against the repository's own generator. A merged dependency bump could ship a declared requirement with a stale lock, because nothing compared the committed lock with what the generator produces from the committed requirement, and the lock-regeneration job only uploaded the regenerated locks as an artifact. The check compiles the native lock from the committed requirement, compares the bytes of all three lock families with the committed content, and fails closed on a missing lock, a missing declared requirement, a failed compilation and a difference. The local gate proves the native target and the hosted matrix proves every declared target on its own runner.

### Changed

- The dependency lock contract states that a committed lock is what the canonical generator produces from its committed requirement, that the gate fails closed when it is not, and that the check makes no exact-reproducibility claim against a mutable upstream index. The committed lock is the generator's constraint, so the check keeps the pinned versions instead of re-resolving them; re-resolving every pinned version remains the separate, reviewable refresh operation.

## 3.29.5 - 2026-10-21

### Fixed

- The refactor-preservation checker now rejects a reversal of a preserved prohibition that is stated in copular form. A pinned obligation that states "X is not Y" could be reversed by a separate instruction that deleted the negation token, because the checker recognized only the imperative "do not" and "never" forms; such a candidate was certified as structurally preserved. The copular form is now compared as a whole and per item of a negated subject list, and a claim that is only quoted, hypothetical, rejected or otherwise mentioned is not treated as a reversal.
- The mention detection of that comparison was narrowed, because an earlier version of it could silence a plain assertion. The bare copulas, the negation words and the plain complementizer "that" are no longer mention frames, a reporting verb governs only the claim it introduces directly on the same line, a line break ends the reach of a frame, and only a matched pair of quote or code delimiters delimits a quoted span. An unbalanced delimiter in an earlier paragraph therefore no longer suppresses a later claim, and a claim that a reporting verb introduces through a complement is reported instead of silently accepted.
- Correction: the 3.29.0 section stated that no deterministic structure check can separate a separate instruction asserting the opposite of a prohibition from legitimate conditional normative content, and placed both residual classes in the independent semantic review lane. The checker now rejects the mechanical polarity flip of a prohibition stated in the imperative form ("do not X", "never X") or in the copular form ("X is not Y"). The independent semantic review lane still covers a separate instruction that restricts the applicability of a pinned obligation, a separate instruction whose restatement does not reuse the pinned wording, including a different number, spelling or predicate, a separate instruction that reports the claim by introducing it directly, and a separate instruction that states the opposite claim and rejects it afterwards, which the checker reports in the fail-closed direction.

### Changed

- The skill-architect semantic-preserving refactoring contract and its migration playbook now state that narrowed residual. The reviewed baseline inventory, the pinned pilot anchors and the reviewed entrypoint routes are unchanged; only the candidate file bindings of the synthetic pilot ledger were repinned for the edited contract text.

## 3.29.4 - 2026-10-20

### Changed

- Development dependencies updated together: `mypy` 2.3.1 to 2.4.0, `ruff` 0.16.9 to 0.16.10, `httpx2` 2.12.0 to 2.13.1, `types-PyYAML` 6.0.12.20260815 to 6.0.12.20260906 and `mcp` 2.2.0 to 2.3.0.
- GitHub Actions updated: `actions/download-artifact` 4.3.0 to 8.0.2 in the release workflow and `actions/upload-artifact` 7.0.1 to 7.0.2 in the CI, lock-regeneration, release and Steward .NET workflows. The prepared payload is still uploaded and downloaded under the same artifact name within the same workflow run.

### Verification

- The locked dependency sets were regenerated with the repository's own lock generator and verified with the locked installer, and the complete development lock audit, the dependency audit and the generator contracts pass on the new versions.
- The integration range is now audited for commit authorship before merge. Only the repository owner's verified address and the trusted automation accounts may appear, and an unauthorized identity fails the pull request closed.
- The transitive `certifi` dependency is pinned to the release that fixes advisory GHSA-6q48-6c7w-9gw2, which the dependency audit reported against the previously locked version.
## 3.29.3 - 2026-10-20

### Fixed

- The refactor-preservation checker now keeps the last non-space character when it decides whether a quote opens an attribute value, so a legal attribute with whitespace between the equals sign and the quoted value is read as a value. A candidate could otherwise hide a reviewed requirement in such a value and have it certified as an operative instruction.

## 3.29.2 - 2026-10-20

### Fixed

- The refactor-preservation checker now walks the document with the same quote-aware scanner that ends a tag, so a tag inside a quoted attribute value is neither counted nor able to end the enclosing block, and a fence-looking line inside an active raw HTML block no longer hides that block's own nested elements from the depth accounting. In both cases a reviewed requirement moved into non-operative HTML was previously certified as preserved.

## 3.29.1 - 2026-10-20

### Fixed

- The refactor-preservation checker now removes every HTML comment opener on a line, so a second opener no longer leaves the rest of the document treated as operative text; it reads a raw HTML opening tag outside quoted attribute values, so a `/>` inside a quoted value no longer makes the element look closed and its content operative; and it recognises a fence opener before any comment removal, so a comment marker in a fence info string is literal content and no longer opens a comment that outlives the fence.
- The release validator now reads a correction declaration only from operative text, so a declaration hidden in an HTML comment or a fenced example cannot authorize a change to a published section; it accepts a declared version that ends the sentence with a period while still refusing a prerelease identifier; and it separates the trailing global Markdown link definitions from the release sections, so ordinary reference-link maintenance no longer looks like a change to a published release.

## 3.29.0 - 2026-10-20

### Added

- The release validator now rejects a repeated category heading inside one release section, and it rejects a change to an already published release section that the release under construction does not declare as a correction.

### Changed

- The refactor-preservation contract now enumerates both residual semantic classes, a separate instruction that restricts the applicability of a pinned obligation and a separate instruction that asserts the opposite of a prohibition the pinned obligation states, and names the enforceable independent semantic review lane that covers them: an independent acceptance authority reviewing provider-backed exact-revision evidence under the repository's independent release evidence profile, plus the candidate-specific semantic review scope owned by the verification owner.

### Fixed

- The refactor-preservation checker no longer treats a raw HTML block whose opening tag spans several lines as operative content, and it no longer removes HTML comments before it parses fenced blocks. A candidate that hid a reviewed requirement in either place was previously certified as structurally preserved, and a review comment marker inside a fenced example could delete the closing fence and expose a later block.
- Correction: the 3.27.0 section repeated a `Fixed` category and attributed the preservation-checker behavior introduced in 3.28.0 to 3.27.0. The duplicated category and the misattributed entries were removed, so the shipped 3.27.0 section matches the released 3.27.0 content.

## 3.28.0 - 2026-10-20

### Added

- A fail-conservative skill refactoring contract with bounded preservation-ledger checks, explicit before-action route validation, documented checker options and synthetic six-class regressions.

### Changed

- The skill-architect migration playbook now separates structural acceptance, model-backed behavior, context cost and independently activated profiles. The preservation contract states its verification boundary explicitly: the checker verifies structural preservation of pinned obligations and route mapping, and it never certifies semantic equivalence. The pilot retains broad existing-skill lifecycle routing (including rename, model upgrades, and deprecation) while shortening redundant guidance.

### Fixed

- Hardened the skill refactor route audit against delayed and optional loads, frontmatter metadata, list-contained code fences, wrapped Markdown and raw HTML example bypasses, noncritical negated safeguards, owner-path suffix spoofing, unrelated deadlines, unreviewed suffixes on a reviewed preload route, candidate-rewritten preload routes, narrowed owner instructions, additional owner-load instructions, and instructions that contradict a preload route; pinned the independently reviewed baseline inventory, exact source-anchor identities, and the complete maintenance-observation obligation; authenticated system-owned Git paths and explicitly labeled unverified candidate versions.

- Dependency-lock installation treats unexpected `pip check` stderr, canonicalized conflicts, and missing lock-pinned packages as blocking errors; verification checks every selected lock pin against the installed name/version inventory even when `pip check` succeeds. Installed versions are compared under PEP 440 canonicalization, and an unavailable `packaging` dependency is reported as an explicit validation error.

- Pin the version-only no-rewrite safeguard in the reviewed inventory; preload lifecycle guidance as workflow step 2 before editing any existing skill; distinguish missing Git main-ref infrastructure from untrusted history or structural preservation failures; reject higher-authority contradictions and reuse lock verification for the complete CI gate.

### Known limitations

- A structural PASS verifies only pinned normative ownership and entrypoint routes; it does not verify repository eval-corpus revisions (`NOT_VERIFIED`), model-backed behavioral equivalence (`BEHAVIOR_NOT_VERIFIED`) or semantic equivalence (`semantic_equivalence: NOT_VERIFIED`). Run those evidence lanes separately.
- The checker cannot decide whether a separate sentence narrows a reviewed obligation, because the same constructions appear in valid normative content of the same skill. That residual class is covered by the independent semantic review lane, never by a structural PASS.

## 3.27.0 - 2026-10-19

### Added

- Optional Steward external execution pressure admission with durable global/per-capability and detached-unresolved limits, reserved cancellation/reconciliation lanes and fail-closed unknown physical termination.
- Deterministic SQLite pressure fixture and cancellation-insensitive fake-provider regressions, including restart and superseded-generation safety.

### Changed

- Local cancellation and logical generation fencing no longer imply physical external capacity is available; service shutdown preserves remotely durable work.
- The optional amendment lineage and the optional external pressure profile now share one Steward profile contract: both feature flags are declared, each opt-in stays bound to its own profile, and enabling one never enables the other.

### Fixed

- A shutdown-fenced external operation that finished remotely and was reconciled by the host keeps its resolved status and remains publishable through a host-verified recovery transition; superseded, cancelled and unreconciled terminal operations stay rejected.
- The optional external pressure flag is not required in the adoption assessment, so an assessment written for 3.26.0 stays valid after the upgrade instead of failing on a newly required field.

### Known limitations

- Reference fixture and synthetic tests do not establish live remote-provider conformance.

## 3.26.0 - 2026-10-19

### Added

- Optional append-only correction, retraction, and supersession lineage for durable Steward evidence with trusted actor authority, linear CAS revisions, idempotent replay and history-preserving effective projections.
- A deterministic SQLite reference implementation, fault-path regressions, and opt-in Steward Design Pack contract fields.

### Changed

- Dependent evidence and artifacts must re-evaluate after effective lineage identity changes; the historical audit remains intact.

### Fixed

- An amendment that is superseded by a concurrent writer before its result is read now requires the same historical-read grant as a replay, so a superseded payload and its provenance are never disclosed to an unauthorized caller.
- Locked dependency installation distinguishes a locked-graph failure from an unmanaged runner host conflict, refuses a report that names a missing lock-pinned distribution, and verifies every selected lock pin against the installed name and version inventory; the complete local gate reuses that verification instead of running an unclassified check.

### Known limitations

- Model and production-provider acceptance remain outside deterministic reference-fixture evidence.

## 3.25.0 - 2026-10-13

### Added

- AFDS `system` documents can provide optional architecture-navigation maps routing stable work units to canonical implementation, contract, test, operational and decision owners.
- AGENTS.md guidance adds conditional navigation before wide scans; a synthetic large-repository regression exercises bounded selection and missing-owner/route failures.

### Changed

- Architecture ownership changes now trigger map and route review. Volatile runtime observations and generated file inventories remain outside durable navigation maps.

## 3.24.0 - 2026-10-13

### Added

- Added an opt-in Ruff `test-quality` profile for deterministic changed-test source selection with bounded configuration/toolchain/lock provenance.

### Changed

- Documented required production-only Ruff/mypy source selection and a separately authorized test-lint promotion path. Optional `--ruff-check` runs only validated test targets and propagates selection/tool failures without unguarded shell expansion; required local and hosted CI gates remain unchanged.
## 3.23.2 - 2026-10-10

### Fixed

- The canonical external-gate deviation evaluator now enforces the published schema's `format: date-time` (RFC3339) on every receipt timestamp — `observation.observed_at`, `incident.first_observed_at`, `incident.last_observed_at`, `incident.fresh_until`, and `retry_policy.next_eligible_at`. Non-RFC3339 ISO-8601 forms that `datetime.fromisoformat` accepts (week dates such as `2026-W41-2T13:00:00+00:00`, space separators) are rejected at construction and integrity verification, so a receipt the canonical owner certifies also satisfies a format-aware JSON Schema consumer. Valid RFC3339 forms (`Z`, `±HH:MM` offsets, fractional seconds), timezone requirements, and chronological comparisons are unchanged.

### Security and correctness

- Closes the schema/evaluator parity gap for date-time fields recorded in #166: digest-consistent tampering of any receipt timestamp to a non-RFC3339 form can no longer remain integrity-valid.

## 3.23.1 - 2026-10-10

### Fixed

- The canonical external-gate deviation evaluator now enforces the declared receipt domain exactly as the published JSON Schema: `schema_version` must be the exact integer `1` at the integrity boundary (a boolean, float, or string that Python compares equal to `1` is rejected), and `incident.reopen_on` is capped at the schema's maximum of 32 signals at construction and verification instead of accepting arbitrary many. Digest-consistent tampering with either field no longer produces an integrity-valid, schema-invalid receipt.
- Added deterministic evaluator/JSON-Schema cross-validation fixtures covering valid receipts, nested substitute/reproduction structures, integrated-subject catch-up, and boundary mutations.

### Security and correctness

- Integrity verification can no longer be satisfied by a receipt whose `schema_version` was mutated to a non-integer representation, closing a validation gap where schema-invalid documents passed as canonical.

## 3.23.0 - 2026-10-08

### Added

- Added provider-neutral External Gate Availability / Deviation Receipt semantics separating hosted execution, product verdict, incident-scoped retries, authorized clean-room substitute and exact-subject catch-up.
- Added JSON Schema, deterministic reference evaluator, CI/CD guidance and adversarial regressions for repeated pre-runner failures.

### Security and correctness

- A zero-step hosted failure remains NOT_EXECUTED even when an exact clean-room substitute passes.
- Catch-up now requires executed PASS evidence from the original provider/gate for the exact subject, observed strictly after the deviation (historical or simultaneous green runs cannot close the obligation). Provider evidence authentication remains the trusted adapter's responsibility.


## 3.22.0 - 2026-10-08

### Added

- Added the provider-neutral Release Deliverable Manifest and Artifact Closure Receipt contracts for proving that policy-required production entrypoints, workers, migration tools, sidecars, or other deliverables are present in the exact immutable release artifact.
- Added a reference closure evaluator with canonical manifest/receipt digests, exact source/artifact/evidence identity binding, required packaged-identity checks, required smoke status, and bounded unexpected-component disposition.
- Extended the canonical protected container-release template with a blocking exact-artifact closure step before promotion, including manifest pinning, receipt/artifact-evidence digest verification, exact source/ref/digest binding, and fail-closed required deliverable identity/smoke checks.

### Security and correctness

- Source files, green tests, and documentation can no longer substitute for proof that a required deliverable is actually packaged in the artifact being published or deployed.
- Missing or unknown required deliverables, identity mismatches, non-passing required smoke, unresolved critical unexpected components, receipt tampering, or drift in source revision, artifact digest, exact-artifact evidence, or manifest identity fail closed.
- Added a Project Steward 0.9 regression fixture proving that a source-present and tested `stewardctl` still fails artifact closure when the final production artifact omits it.

## 3.21.0 - 2026-10-06

### Added

- Added an explicit CI dependency-lock contract that separates exact committed-lock candidate verification from deliberate mutable-upstream dependency refresh.
- Extended the canonical verification-bootstrap validator with typed candidate-verification and dependency-refresh operations, resolver/runtime/source provenance, refresh cache isolation, reviewable lock-diff semantics, and exact-versus-observational reproducibility claims.
- Added Python exact-hash guidance and regressions derived from a completed real-consumer lock/refresh split.

### Security and correctness

- A newer package appearing in a mutable public index no longer constitutes candidate failure when the unchanged committed lock remains the admitted dependency identity and passes its integrity checks.
- Candidate acceptance cannot silently regenerate or rewrite dependency locks, while mutable-upstream refresh cannot claim exact reproducibility without an immutable dependency-source identity.
- Resolver cache state is excluded from refresh authority unless the refresh profile explicitly uses an isolated or disabled cache; exact refresh also requires digest-bound immutable source identity, while security/vulnerability freshness remains a separate enforceable gate.

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
