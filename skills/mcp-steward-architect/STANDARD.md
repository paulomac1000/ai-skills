---
description: Normative architecture and production rules for durable MCP Steward control planes.
doc_id: reference.mcp-steward-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Validate Steward Design Pack schemas and rule-map coverage; execute state-machine, mutation-admission, persistence, recovery-equivalence, reconciliation, cancellation, evidence-promotion, generator, official-client, exact-artifact, and applicable independent/live acceptance lanes.
---

# MCP Steward architecture standard

## Purpose

This standard defines additional architecture required when an MCP server owns durable, multi-step work rather than only synchronous request/response capabilities. It standardizes control-plane semantics, not one business domain.

## Base standards and precedence

A Steward MUST conform to `mcp-server-architect` on its inbound/public MCP surface and to `mcp-server-consumer` for downstream MCP interaction. This standard adds durable workflow, authority, evidence, recovery, and handoff semantics and MUST NOT weaken either prerequisite standard.

The MCP invocation kernel remains the only public execution path. The Steward application kernel sits behind it. CLI, webhook, worker callback, recovery tick, maintenance supervisor, and model proposal paths MUST enter the same application policy/state-transition boundaries rather than bypassing them through adapters.

Findings owned by prerequisite standards MUST be routed to those canonical owners rather than copied into Steward policy.

## Authority boundary

Every Steward MUST declare state it owns, state it observes, mutations it may perform, verification authority it holds, parent/system completion authority it holds, and claims it MUST NOT make.

When `parent_completion` is `explicit-contract-only`, the profile MUST carry a snapshotted `parent_contract` binding system/work/run identity, parent generation and contract digest, delegated authority ceiling, inherited deadline/budget, and the required terminal handoff contract. A standalone Steward MUST use `parent_completion: none` and `parent_contract: null`; it MUST NOT infer parent authority from caller metadata.

A supervised Steward MUST admit the profile-schema parent contract snapshot at Work Admission, bound to the job generation, with typed unsupported/stale/insufficient-authority/re-admission outcomes; material contract or policy changes force a new generation. Effective authority is local ∩ delegated-minus-forbidden ∩ current facts; supervised budgets only narrow. Terminal results carry exact parent identity, distinct from parent task state.

API-key possession, successful model output, worker self-report, caller metadata, provider display labels, or caller-declared authority fields MUST NOT create authority. A Steward MAY finalize its own job but MUST NOT infer permission to merge, deploy, publish, approve, independently verify, or complete a parent item without an explicit contract.

Authority-bearing values are non-defaultable. Lease identity/expiry, exact revision, generation, target identity, effective authority, capability-contract identity, candidate digest, and equivalent values MUST come from an authoritative source. Missing or invalid values MUST fail closed rather than becoming `unknown`, `HEAD`, `latest`, synthetic expiry, random identity, or a caller assertion.

## Design pack and enforcement gates

Before implementation, an applicable Steward MUST define a machine-readable Design Pack containing the profile, state machine, mutation policy, proof recipe, upstream capability contracts, and acceptance plan. Legacy state-machine and acceptance documents MAY remain individually readable/validatable for bounded migration, but a current conformance claim MUST use the closure-bearing contract revisions required by the current Design Pack; legacy document validity is not current Steward conformance.

The design MUST identify four application-level gates:

1. **Work Admission Gate** proves durable work is admissible from exact identity, authority, capability, completion obligations, and budget.
2. **Mutation Admission Gate** runs immediately before every authority-bearing side effect and proves current lineage/generation/attempt, effective authority, lease where required, exact subject/candidate, reviewed capability provenance, durable operation identity, ambiguity disposition, and budget/deadline reserve.
3. **Evidence Promotion Gate** limits claims to what producer, binding, coverage, freshness, and authority actually prove.
4. **Completion Publication Gate** proves the Steward's declared responsibility is fulfilled and current before terminal actionable publication.

Gate results MUST be typed outcomes such as `Admitted`, `LostAuthority`, `StaleCandidate`, `CapabilityUnavailable`, `ReconciliationRequired`, `InsufficientEvidence`, or `BudgetUnavailable`; a bare boolean is insufficient for material failure/recovery semantics.

For every material invariant, the Design Pack SHOULD identify authoritative source, enforcement point, durable proof, failure outcome, and negative regression. An invariant with no enforcement point is documentation, not control.

## Durable job and state ownership

Every long-running operation MUST have durable job identity persisted before success is returned. Authoritative state MUST survive request/process lifetime and distinguish operational status, domain outcome, delivery state, and infrastructure failure.

A durable job MUST expose enough state to reconstruct ownership and recovery: job/lineage/generation/attempt/version, exact subject and candidate where applicable, stage/status, deadline/finalization timestamps, heartbeat/progress timestamps and stable progress revision/marker, cancellation state, active lease, external-operation references, bounded evidence/artifact references, and structured failure classification.

Terminal states MUST NOT become active again. In-memory queues, callbacks, caches, model context, and memory systems are wake-up/acceleration mechanisms only.

## Producer reachability and liveness closure

Every intended reachable material transition or gate MUST name at least one real authorized production producer path. Valid producer classes include public MCP/API ingress, a worker stage, reconciler, trusted administrative/domain command, migration/recovery path, provider-result adapter, or scheduler. The Design Pack MUST bind each declared producer to a concrete runtime entrypoint or adapter owned by the implementation, a versioned producer contract/reference, its authority source, and an explicit boundary class such as public, internal, trusted-only, or recovery-only. Constructing a domain object, row, state, or command directly in a test does not prove production reachability.

Every non-terminal state MUST declare a liveness condition equivalent to active owned work, scheduled bounded work, a recoverable external operation, deterministic recovery/remediation, or an explicit authorized blocker/input wait. It MUST also declare the bounded orphan/convergence disposition used when that condition is no longer true. A state with no valid owner, wake-up, recoverable external handle, reconciliation path, explicit blocker, or terminal/partial-terminal convergence is non-conformant.

Recovery MAY recreate missing deterministic next work only through generation- and idempotency-fenced canonical state, at most once for the same semantic slot. It MUST NOT revive stale-generation work, turn delivery-unknown or otherwise non-replay-safe work into a retry merely to restore liveness, or emit repeated work/events when an unchanged liveness sweep observes the same healthy/blocked state.

Generated/reference runtimes MUST either demonstrate the applicable producer/liveness paths through their real public/worker/recovery boundaries or explicitly declare a non-applicable transition/state. Test-only construction is never a substitute for that proof.

## Lineage generations attempts and leases

Retrying an attempt and creating a new semantic generation are different operations. Recheck, refresh, replan, replacement, or invalidation MUST advance generation when prior actionable work becomes stale.

Optimistic version and semantic generation MUST NOT be overloaded when stale work could inherit a newer epoch. A worker captures generation at admission/claim; successors, deferred continuations, side effects, evidence, candidates, and publication MUST carry/fence that captured generation. Persistence MUST NOT substitute the latest generation for stale work.

Every mutable update MUST be fenced by relevant version/attempt identity. Every actionable terminal publication MUST also be fenced by current lineage generation/current job.

A lease is a mutation-authority primitive, not merely a scheduler hint. Operations that require a lease MUST re-check authoritative owner, epoch/fencing token, and expiry at the Mutation Admission Gate. Renewal MUST use upstream/storage-authoritative expiry/epoch; it MUST NOT infer success from `now + requestedDuration`. Ambiguous renewal blocks mutation. Long operations MUST have enough remaining lease/deadline for the operation plus deterministic finalization reserve.

## Semantic checkpoints and dependency-scoped reuse

Execution attempt, workflow generation, and semantic input identity are distinct. A retry of the same semantic work MUST NOT manufacture a new meaning merely because the attempt changed; conversely, a changed load-bearing semantic dependency MUST NOT inherit an artifact solely because its stage name or payload looks similar.

A reusable canonical checkpoint MUST bind stable checkpoint/stage identity, exact canonical artifact reference and digest, workflow generation, state-machine identity/revision, the complete declared semantic dependency identities required for that artifact, exact upstream checkpoint artifact references/digests, the legal resume state, and the mechanical recovery bindings needed by a fresh worker (subject/candidate, authority/ownership, progress, budgets/deadlines, blockers and external-operation references as applicable). Recovery subject/candidate identities MUST agree with the corresponding current semantic dependency identities; schema-valid but cross-subject/cross-candidate recovery context is stale. A resume state MUST be non-terminal and MUST have a legal state-machine path to the checkpoint state. Dependency dimensions MAY include subject/candidate, effective evidence, target, policy, model/capability contract, validation environment, external-gate identity, or another explicitly governed input. Unknown/missing load-bearing identity is stale.

For one current generation, checkpoint currentness is derived mechanically from exact dependency identity plus transitive upstream checkpoint currentness. A changed dependency invalidates only checkpoints that declare it and their downstream dependents. An unrelated late-stage provider/gate outage MUST NOT stale earlier CURRENT artifacts/evidence merely because the later operation failed. A checkpoint from an older workflow generation is stale by default and MUST NOT satisfy the new generation without an explicit policy-owned compatibility proof.

The deterministic supervisor SHOULD expose a bounded derived resume result equivalent to:

~~~yaml
earliestSafeStage: ...
reusableArtifactRefs: [...]
staleArtifactRefs: [...]
requiredRecomputations: [...]
dependencyDigest: sha256:...
reasonCodes: [...]
~~~

`earliestSafeStage` is the first legal stage whose required checkpoint is non-current; if every required checkpoint is current, no recomputation is required. Restart with the same durable state and semantic dependencies MUST derive the same result without replaying prior model conversation/transcript. A losing retry/CAS path reloads the canonical winning checkpoint before deriving successors. Similarity, reviewer prose, or a model assertion is not compatibility proof.

## Persistent context provenance

Persistent artifacts that can influence a later session MUST carry a bounded trusted provenance envelope with trust class, explicit scope, currentness, load-bearing dependency identities, and permitted influence. Persistence never upgrades authority: model/repository/user prose cannot grant capabilities, policy exemptions, merge/deploy/lifecycle authority, or satisfy a stronger evidence gate merely because it survived. Derived load-bearing summaries retain evidence refs; unknown provenance/currentness is not current truth.

Fresh-session assembly MUST prefer current higher-authority facts over stale/lower-trust context, invalidate declared dependencies when subject/runtime/environment/policy generations change, and fail conservative on incompatible cross-project/cross-user scope. Useful advisory lessons MAY influence planning only when applicability/currentness are proven; they remain non-authoritative. Storage stays product-owned and conformance requires bounded refs/summaries, not private chain-of-thought or raw transcripts. See `references/persistent-context-provenance.md`.

## Mutation admission and candidate identity

Each authority-bearing effect MUST have a declared mutation policy binding authority source, lease requirement, exact subject dimensions, exact candidate requirement, capability contract, durable operation requirement, budget reserve, ambiguity disposition, and typed failure outcomes.

For stateful external effects, durable admission and operation reservation MUST commit before the first byte of dispatch. An operation identity existing only in memory does not satisfy this rule.

Where verification/approval applies to a mutable artifact or proposed change, `CandidateIdentity` is first-class and immutable. It MAY be a tree/commit identity, artifact/content digest, deployment-plan digest, bundle digest, configuration snapshot, or equivalent exact candidate. `verify(candidate X)` MAY authorize only `publish(candidate X)`. Candidate drift between proof and publication invalidates that proof and MUST force revalidation or rejection.

The mutation gate MUST re-read mutable authority/identity facts immediately before the effect. Admission from stale cached facts MUST fail closed.

## Integration authority and lease

When a Steward may integrate a candidate into a governed repository target, generic write/push capability is insufficient. Integration requires an authority-owned lease bound to exact principal, repository/change, candidate head/tree, target/base policy, merge strategy, evidence-set/policy identity, execution generation, and expiry. The lease MUST be resolved or verified through an authority-controlled store/issuer boundary whose trust anchor is host-owned rather than caller/model supplied. Immediately before reservation the Mutation Admission Gate MUST re-read those facts plus current provider controls; stale candidate/base/evidence/policy or lost authority fails closed.

The durable integration operation MUST be reserved before dispatch and reservation consumes the one-shot lease. Timeout or lost acknowledgement enters reconciliation on that same operation and MUST NOT reactivate/replay the lease. Successful reconciliation proves exact candidate-to-integrated revision lineage for the selected strategy; squash/rebase/merge consumers MUST NOT assume candidate SHA equals integrated SHA. See `references/integration-lease.md`.

## External operations and reconciliation

Before a stateful external operation whose effect can outlive the call, the Steward MUST durably record an operation identity/start intent bound to job/generation/attempt, exact capability contract and target, canonical request digest, non-secret credential slot, and admitted mutation decision.

Operation identity is semantic: receipts bind the workflow slot; distinct slots with identical payloads stay distinct operations.

Stateful operations carry a durable absolute deadline: nested bounds clamp to it, restart never resets it, and post-dispatch expiry is delivery ambiguity, never proven `not-delivered`.

Outcome taxonomy MUST distinguish pre-dispatch failure, provider rejection, confirmed delivery, delivery unknown, caller cancellation, and cancellation-delivery-unknown when applicable. These states MUST NOT be flattened into one error.

`delivery-unknown` MUST enter bounded reconciliation. Stateful work MUST NOT be resent until policy and upstream semantics prove replay safe. Recovered remote handles MUST be resumed/polled rather than replaced when supported.

Once a provider-assigned remote identity/handle has been observed, local binding-persistence failure MUST NOT regress the operation to not-dispatched/reserved. The durable model MUST preserve binding uncertainty or provide provider-side lookup by durable operation/idempotency identity.

Remote calls MUST execute outside durable-store locks/transactions.

## Cancellation and external wait isolation

Cancellation of stateful async work is itself a stateful external effect when it can change remote reality. Its contract MUST declare cancel delivery model, idempotency, reconciliation, handle/credential affinity, and the relationship between local terminal state and remote stop.

Cancellation provenance is semantic state with typed causes (`caller_cancel`, `parent_superseded`, `service_shutdown`, `application_deadline`, `transport_timeout`, `provider_cancel`, `unknown`); a transport timeout is never caller cancellation, and local cancellation never claims remote stop without upstream proof.

A local `cancelled` status MUST NOT imply upstream work stopped unless the upstream contract and observed cancellation outcome establish that fact. If cancel delivery is unknown, the Steward MUST reconcile before claiming confirmed remote cancellation or replaying a non-idempotent cancel.

Cancellation MUST first fence new side effects. A public cancellation request and a remote cancellation dispatch are distinct transitions: every non-terminal state accepted by the public cancel entrypoint MUST declare its local transition into cancellation handling, while any later remote cancel call is a separately mutation-gated external effect owned by the workflow/recovery path. Not-delivered work may be abandoned safely; delivery-unknown work must be reconciled; delivered/running work follows the upstream cancel/observe contract. Cleanup remains bounded.

A durable Steward MUST NOT hold a primary workflow worker solely while waiting for an external durable operation whose state is reconstructable from durable local state. Such waiting SHOULD be checkpointed and handled by a bounded external-maintenance/reconciliation lane. Control/cancellation work MAY use a separately bounded reserve so saturation cannot prevent safe closure.

## Evidence identity and authority

Intent, performed work, observation, evidence, claim, and policy decision are distinct objects. A provider result or model statement MUST NOT automatically satisfy an arbitrary criterion.

Material evidence MUST bind exact subject, relevant revision/generation, candidate when applicable, producer identity, provenance/source, observation time, freshness/expiry, authority class, canonical claim/criterion, proof-recipe identity, binding status, and immutable payload/content digest.

Configured, intended, observed, observed-effective, functionally-ready, and independently verified states are different grades. Sources MUST NOT be promoted beyond what they actually observe.

Model findings are advisory unless explicit policy assigns a stronger class; irreversible negative decisions requiring stronger authority need reproduction/corroboration by an approved producer.

## Claim binding and epistemic promotion

A claim whose validity depends on ownership, runtime, resource, revision, deployment, candidate, or execution relationships MUST declare binding obligations. Evidence MAY satisfy that claim only when the required binding chain is complete. Incomplete binding MUST prevent promotion beyond the strongest class justified by the completed prefix.

Proof producers are first-class contracts. A producer definition MUST state producer identity/trust class, observation kind, subject dimensions, claim classes, binding capabilities/requirements, independence class, and freshness semantics relevant to its evidence.

Epistemic promotion MUST be fail-closed and monotonic. Missing observation is not a negative observation. Unknown/unobserved/contradictory coverage MUST NOT be collapsed into a complete negative claim. A complete negative aggregate requires the proof recipe's declared coverage semantics to be satisfied for every required member/dimension.

Health/liveness, process readiness, protocol initialization, capability presence, functional canary success, and business criterion proof are distinct observations and MUST NOT substitute for one another.

Reusable plans, approvals, routing decisions, and completion candidates SHOULD bind `DecisionIdentity` dimensions that invalidate reuse. Identity change requires explicit reuse/revalidation/replanning/reauthorization/supersession/rejection.

## Completion and handoff

`Completed` means the declared completion contract is satisfied, not merely that code returned. Inbound work/completion obligations that affect final authority MUST be preserved durably; evidence satisfies only the criterion it actually measured.

The obligation set MUST be snapshotted with revision and digest at Admission; planner decomposition refines but never replaces it. Derived work MUST trace to an admitted obligation, and completion evaluates the snapshot, never the live profile. Supersession stays authority-bound; restart preserves the lineage.

Required obligations MUST be machine-readable and resolve to satisfied, legitimately not-applicable, or explicitly waived/deferred by sufficient authority. Unresolved mandatory obligations, unresolved stateful side effects/cancellation, stale evidence, stale candidate, or superseded lineage block clean completion.

Useful partial terminal outcomes such as `CompletedWithGaps` or `Inconclusive` SHOULD be used rather than hanging forever or flattening optional dependency loss.

The terminal handoff MUST bind exact subject/candidate where applicable, job/lineage/generation, operational status, domain outcome, evidence/artifact/external-operation references, unresolved gaps/failures, correlation identity, seal time, and deterministic digest when required. Final publication MUST re-read current lineage/subject/candidate/authority/freshness immediately before sealing.

## Ports adapters and capability admission

Domain/application code MUST NOT depend on MCP/provider SDK types, raw HTTP shapes, database/filesystem implementations, environment variables, or vendor model types. Ports describe semantic needs.

Every external adapter MUST expose a reviewed capability contract with explicit provenance: contract source, id, revision and digest; exact subject/target dimensions; evidence classes; stateless/stateful model; sync/durable-async delivery; idempotency; recovery/resume; submit and cancel semantics; stable progress semantics; credential affinity; bounds; rate/concurrency scope; deadline policy; and confidentiality/egress constraints.

The capability digest MUST cryptographically bind the complete reviewed semantic capability definition, not only its source/id/revision tuple. Unless a schema defines an explicit versioned semantic projection, the projection is the entire machine-readable capability document with only `contract.digest` removed; object keys are canonicalized, array order is preserved, and schema/revision fields remain included. Any behavior-significant capability change without a matching reviewed digest MUST fail closed as capability unavailable.

Capability truth and health are distinct. `healthy=true` MUST NOT manufacture feature support. Capability MUST come from a negotiated/discovered trusted contract, pinned reviewed contract, or explicit operator configuration; liveness/readiness is an additional runtime condition.

Before durable work admission, required obligations MUST be matchable to reviewed capabilities/producers. Known impossible work fails closed with typed capability-unavailable/blocked outcome.

Disclosure-bearing adapters require a policy-approved disclosure-safe projection before dispatch. Prompt-role separation and injection defenses do not authorize egress. Unknown/mixed disclosure state fails closed unless policy permits a bounded redacted projection.

Adapters normalize provider results into application-owned outcomes. They MUST NOT decide business policy, silently rotate credentials, or replay stateful work on their own.

## Credentials and provider failover

Secrets enter through intentional credential providers and MUST NOT appear in durable jobs, evidence, normal logs, prompts, schemas/discovery, or model-visible errors. Durable state records only non-secret slot/alias and minimum provider/account fingerprint needed for affinity/audit.

Credential failover is distinct from retry and provider/model substitution. It MAY occur only when equivalent principal/scope/tenant/target semantics and replay safety are proven. Authorization/policy denial and delivery ambiguity are not reasons to rotate credentials.

Remote-handle work preserves credential affinity unless the reviewed upstream contract explicitly permits an equivalent credential to resume it. Provider/model fallback is a separate explicit policy decision recorded in provenance.

## Progress deadlines budgets and finalization

Worker liveness and semantic progress are distinct. Durable jobs MUST record `heartbeatAt`, `progressAt`, and stable `progressRevision`/marker. Heartbeat or repeated identical remote state MUST NOT advance semantic progress.

Terminal external observation MUST be persisted canonically once. If it cannot satisfy proof policy, the workflow MUST move to an explicit blocked/inconclusive/failed/partial outcome or await a declared new producer/action; it MUST NOT hot-poll the same terminal observation merely because no evidence was promoted.

Status/result SHOULD expose stable progress revision plus bounded server-side wait, `retryAfter`, `nextPollAt`, or next-action guidance when supported.

Before starting a worker leg or provider call, the Steward MUST establish sufficient durable wall-clock/call/cost/resource budget for that leg and deterministic finalization. Restart MUST NOT reset elapsed wall-clock budget. Transport/library timeouts MUST NOT silently be shorter than the admitted application operation deadline unless that earlier bound is intentional policy.

Execution MUST reserve bounded time/capacity for persisting observations, reconciliation/cancellation, sealing handoff, releasing leases, and terminal publication.

## Persistence recovery and shutdown

The durability claim MUST state process-restart, host/power-loss, multi-process, and multi-node guarantees separately, and MUST declare the runtime/process topology (client multiplicity, server process multiplicity, store ownership, writer model, shared-state scope, restart boundary) so deployment cannot claim stronger durability than the storage profile supports; competing writers on a single-owner store fail as a typed, diagnosable topology conflict.

Retry-safe persistence is canonical-first. If a stable identity already has committed artifact/result A, a retry proposing B must converge on A; dedupe/CAS/no-op persistence MUST return/reload the canonical value/reference/digest and downstream work MUST consume it.

Durable work and wake-up/outbox intent SHOULD commit atomically. Every nonterminal job MUST satisfy the producer/liveness closure contract: current owned work, scheduled bounded work, recoverable external handle/reconciliation, or an explicit authorized blocker with a declared convergence disposition.

Recovery equivalence is required: for the same durable input and externally observed reality, uninterrupted and restarted execution MUST converge on the same canonical observation/evidence/decision semantics. Recovery MUST NOT bypass mutation admission, evidence promotion, completion gates, disclosure policy, or candidate binding.

A decision composing authoritative records MUST observe one consistent snapshot or carry a read-set revalidated before it becomes actionable; a write-side CAS never repairs a torn read. Stateful admission controllers MUST epoch-version decisions; older-epoch decisions are history only.

Shutdown/cancellation fence new effects, persist intent before releasing ownership, and perform bounded cleanup. Recovery prefers durable state/resume/reconciliation over logs/model memory.

## Observability and diagnostics

Logs, durable audit events, and decision evidence are separate classes. Correlation MUST reconstruct request/job/lineage/generation/attempt/operation/candidate identity, stage, logical port/adapter/provider, subject, request digest, non-secret credential slot, mutation decision, transition/result class, and trace identity as applicable.

Emit events for admission gates, lease decisions, mutation admission/rejection, dispatch, delivery ambiguity, reconciliation, retry, cancellation, evidence acceptance/rejection, claim promotion/rejection, supersession, stale-result discard, recovery, candidate revalidation, and handoff sealing.

Normal logs use bounded sanitized metadata/digests/references rather than secrets, full prompts, protected provider bodies, or unbounded output. Persistence, external-model disclosure, public response, and audit retention are separate policy contexts. Sanitized canonical evidence/summary MUST NOT reintroduce a secret removed at an earlier boundary.

Production-capable profiles MUST provide bounded doctor diagnostics for current ownership, mutation blockers, open delivery/cancellation ambiguity, dependency/credential/capability health, deadlines/progress, recovery backlog, and recent durable transitions.

Every policy-significant field MUST have producer, consumer, decision effect, and regression.

## Public MCP surface

Expose outcomes and hide mechanics. Long-running APIs normally provide submit/start, status, result/get, cancel, and optional bounded continue/recheck/reconcile/evidence/doctor roles. Do not surface raw provider/GitHub/Docker/SSH primitives merely because they are internal dependencies.

Start returns after durable admission. Status/result remain bounded and SHOULD expose stage, progress revision/class, failure/gap codes, digests, authoritative next action, and references.

Known transition preconditions MUST be discoverable before mutation: exact subject/revision/generation/candidate, lease/assignment, verification/completion profile, effective authority, capability contract, and required evidence. A caller MUST NOT discover deterministic requirements only through repeated rejected mutations.

Rejected transitions SHOULD return typed unmet precondition plus authoritative expected value/reference and safe next semantic action when disclosure permits.

Long-lived durable state MUST NOT be mirrored into an ever-growing model conversation.

## Testing and acceptance

Every safety/recovery invariant MUST have a negative regression. Use controllable time and deterministic barriers/events/fault points, not timing sleeps, for races.

Coverage MUST include reservation/dispatch/handle/result/evidence/finalization/cancellation crash windows; lost wakeups; idempotency; delivery and cancel ambiguity; lease/renewal fencing; stale-generation successor races; cancellation versus completion; canonical A versus retry-local B; production-producer reachability; stranded non-terminal states; semantic-checkpoint currentness and minimum recomputation; cross-generation checkpoint rejection; candidate drift after verification; capability provenance versus health; private-egress sentinels; incomplete claim binding; negative-plus-unobserved aggregation; terminal-result insufficient-authority no-hot-loop; deadline/finalization edges; recovery equivalence; and exact packaged runtime prerequisites.

Provider adapters MUST be tested against observed upstream-contract fixtures. Test source presence is not execution evidence.

Historical sanitized incidents SHOULD become regression fixtures.

## Acceptance ladder and exact workflow artifact

Acceptance claims are layered and non-substitutable:

1. implementer/focused validation;
2. canonical full repository gate;
3. deterministic fault/restart/recovery suite;
4. inherited `mcp-server-architect` and `mcp-server-consumer` conformance;
5. independent exact-delta review when the profile requires independent assurance;
6. exact packaged/deployed artifact execution;
7. live/profile-specific full-path proof when claiming production workflow acceptance.

A structural/conformance claim MAY omit unavailable live credentials when clearly scoped. A production workflow acceptance claim MUST NOT be made until the exact candidate artifact exercises the applicable path from admission through worker/upstream, stateful effect, observation/evidence, completion/publication, and at least one representative restart/recovery boundary.

Exact-artifact assurance MUST validate runtime prerequisites required by the real workflow, not only process startup, MCP handshake, or `tools/list`. Missing executable/config/provider/runtime dependency is an artifact failure.

Implementer tests, candidate-owned evidence, independent review, exact artifact, and live evidence are different authority classes; none silently substitutes for a stronger required layer.

## Generated baseline

The generator MUST extend canonical MCP server generators. It MUST emit a working durable architecture seed plus Steward Design Pack: profile, state-machine, mutation-policy, proof-recipe, upstream capability, acceptance plan, idempotent intake, scheduler/recovery hooks, controllable time/fake provider, operation and cancellation reconciliation, progress revision, structured audit/doctor, evidence promotion, completion gate, and fault injection.

The generated baseline MUST demonstrate durable admission, pre-dispatch commit, crash/restart reconciliation, captured-generation fencing, canonical-first retry/observation, terminal-result no-hot-loop behavior, safe cancellation of stateful external work, recovery equivalence, and digest-bound publication. Generated scaffolding remains architecture-seed evidence, never production acceptance.

## Verification

Before conformance, validate the Design Pack and runtime instance schemas, execute contextual mutation/evidence/completion validators, run state-machine/persistence/reconciliation/cancellation/fault/recovery suites, execute inherited MCP gates, and verify the exact packaged artifact.

Where independent assurance is required, the candidate revision MUST NOT be the sole authority used to approve itself. Findings outside Steward ownership MUST be routed to their canonical prerequisite standard rather than duplicated here.
