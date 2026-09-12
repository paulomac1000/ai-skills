# MCP Steward architecture standard

## Purpose

This standard defines the additional architecture required when an MCP server owns durable, multi-step work rather than only synchronous request/response capabilities. It standardizes control-plane semantics, not one business domain.

## Base standards and precedence

A Steward MUST conform to `mcp-server-architect` on its inbound/public MCP surface and to `mcp-server-consumer` for every downstream MCP interaction. This standard adds workflow durability, evidence, recovery, authority, and handoff semantics and MUST NOT weaken either prerequisite standard.

The MCP invocation kernel remains the only public execution path. The Steward application kernel sits behind it and owns multi-step workflow state. CLI, webhook, worker callback, recovery tick, and model proposal paths MUST enter the same application policy/state-transition boundary rather than bypassing it through adapters.

## Authority boundary

Every Steward MUST declare a bounded responsibility before tools are designed. The profile MUST distinguish at least state it owns, state it observes, mutations it may perform, verification authority it holds, parent/system completion authority it holds, and claims it MUST NOT make.

Possession of an API key, successful model output, worker self-report, caller metadata, issue/PR prose, or provider display labels MUST NOT create authority. A Steward MAY finalize its own durable job but MUST NOT infer permission to close, merge, deploy, publish, approve, or complete a parent work item unless a separate explicit contract grants that authority.

## Durable job and state ownership

Every long-running operation MUST have a durable job identity persisted before success is returned to the caller. The authoritative job record MUST survive the process/request lifetime and MUST distinguish operational status from domain outcome and infrastructure failure.

A durable job MUST expose enough state to reconstruct ownership and recovery: `jobId`, `lineageId`, `generation`, `attemptId`, optimistic `version`, exact subject identity, status, stage, creation/update/deadline timestamps, separate heartbeat/progress timestamps, cancellation state, active lease when owned, external-operation references, bounded evidence/artifact references, and structured failure classification.

Terminal states MUST NOT transition back to active states. In-memory queues, channels, notifications, callbacks, caches, model context, and memory systems are wake-up/acceleration mechanisms only and MUST NOT become the canonical workflow state.

## Lineage generations attempts and leases

Retrying one worker attempt and creating a new semantic generation are different operations. Recheck, refresh, replan, or replacement MUST atomically advance lineage generation when prior actionable results can become stale.

Every mutable state update MUST be fenced by the relevant job version and attempt identity. Every actionable terminal handoff MUST additionally be fenced by the current lineage generation/current job. A stale attempt or superseded generation MAY finish bounded cleanup but MUST NOT publish a current success/failure decision or mutate canonical state.

Leases MUST have explicit owner, expiry, and fencing semantics. Lease expiry means recoverable ownership loss, not domain failure. Multi-process or multi-instance deployments MUST use storage primitives that actually serialize ownership; a process-local semaphore is insufficient.

## External operations and reconciliation

Before any stateful external operation whose effect can outlive the local call, the Steward MUST durably record an operation identity/start intent or equivalent receipt bound to the job/generation/attempt, exact capability/target, canonical request digest, and non-secret credential slot identity.

The operational model MUST distinguish at least: not dispatched/not delivered, confirmed delivery or provider rejection, and delivery unknown. Timeout, disconnect, process crash, or lost response after dispatch MUST NOT be interpreted as proof that the operation did not happen.

`delivery-unknown` MUST enter bounded reconciliation. Stateful work MUST NOT be resent until provider semantics plus Steward policy establish that replay cannot duplicate an effect. A recovered remote handle MUST be resumed/polled instead of re-submitted when the upstream contract provides that path.

Remote calls MUST execute outside durable-store locks/transactions. Local reservation and post-call observation are separate durable transitions.

## Evidence identity and authority

Intent, performed work, observation/evidence, and policy decision are distinct objects. A provider result or model statement MUST NOT automatically satisfy an arbitrary criterion.

Evidence used for a material decision MUST bind the exact subject and relevant revision/generation, producer identity, provenance/source, observation time, freshness class or expiry, authority class, and immutable content/payload digest where applicable. If policy/proof-recipe identity affects meaning, the producing authority MUST attest or otherwise bind it; a Steward-local expected digest is not evidence that a producer executed that policy.

Configured, intended, observed, observed-effective, and independently verified states are different evidence classes. A source file, health endpoint, tool listing, CI badge, screenshot, commit message, resolved review thread, or model consensus MUST NOT be promoted beyond what it actually observes.

Model-generated findings are advisory unless an explicit policy assigns a stronger class. Where an irreversible negative decision requires stronger authority, advisory findings MUST be reproduced or corroborated by an approved stronger producer.

Reusable plans, approvals, validations, routing decisions, and completion candidates SHOULD bind a `DecisionIdentity` composed from the dimensions that can invalidate them, such as subject/repository/runtime generation, policy revision, workflow revision, capability-contract revision, authority epoch, or credential-policy revision. Identity change MUST cause explicit reuse, revalidation, replanning, reauthorization, supersession, or rejection rather than silent reuse.

## Completion and handoff

`Completed` means the declared completion contract is satisfied; it MUST NOT mean merely that a worker returned or an async method ended. Required completion obligations MUST be machine-readable and resolve to satisfied, legitimately not-applicable, or explicitly waived/deferred by sufficient authority according to policy. Unresolved mandatory obligations, unresolved ambiguous side effects, stale required evidence, or superseded lineage MUST block a clean completion.

Useful terminal partial outcomes such as `CompletedWithGaps`, `Inconclusive`, or an equivalent profile-defined state SHOULD be used instead of hanging forever or flattening optional dependency loss into generic failure.

The terminal handoff MUST be bounded and bind the exact subject, job/lineage/generation, operational status, domain outcome, evidence/artifact references, unresolved gaps or failures, external-operation receipts where relevant, correlation identity, seal time, and deterministic digest when the profile requires tamper-evident transfer.

The final publication boundary MUST re-read current lineage/subject ownership and freshness immediately before sealing when those values are mutable.

## Ports adapters and capability admission

Domain and application code MUST NOT depend on MCP SDK types, provider SDKs, raw HTTP response shapes, database implementations, filesystem APIs, environment variables, or model-provider types. Inbound MCP/CLI/webhook surfaces are adapters over semantic application operations.

Outbound ports MUST describe domain needs such as observation, mutation, reconciliation, verification, reasoning, evidence/artifact storage, durable state, credentials, time, audit, or telemetry rather than vendor names.

Each external adapter MUST expose a reviewed capability contract describing the subject/target identities it can actually observe, evidence classes it can produce, stateless/stateful interaction model, synchronous/durable-async delivery, idempotency support, recovery/status/resume capabilities, cancellation semantics, progress semantics, credential affinity/scope, request/result bounds, concurrency/rate-limit scope, and confidentiality/egress constraints.

Adapters normalize provider-specific results into application-owned outcomes. They MUST NOT decide business policy, silently rotate credentials, or retry stateful work on their own.

Before durable admission, required workflow obligations MUST be matched against configured adapter capabilities. A Steward MUST fail closed or return a typed blocked/capability-unavailable result when required work is already known to be impossible.

## Credentials and provider failover

Secrets MUST enter through an intentional secret/credential provider and MUST NOT appear in durable jobs, evidence, normal logs, prompts, tool schemas, discovery, or model-visible errors. Durable state MAY record only non-secret slot/alias identity and the minimum provider/account fingerprint needed for audit and affinity.

Credential failover is distinct from request retry and from provider/model substitution. It MAY occur only when policy proves equivalent principal/scope/tenant/target semantics and replay is safe. Authorization denial, policy denial, provider-wide prohibition, and delivery-unknown are not reasons to rotate credentials.

Once stateful remote work has a remote handle, credential affinity MUST be preserved unless the observed upstream contract explicitly permits another equivalent credential to resume the same operation.

Cross-provider/model fallback MUST be an explicit routing/policy decision because provider/model identity can change tool semantics, context/output bounds, cost, privacy/egress, and assurance. Actual provider/model identity MUST remain visible in provenance and telemetry.

Fallback attempts MUST be bounded and MUST prevent credential ping-pong.

## Progress deadlines budgets and finalization

Worker/process liveness and semantic workflow progress are separate signals. `heartbeatAt` MUST NOT reset the semantic-progress watchdog unless the underlying progress marker actually advances. Remote polling that repeatedly returns the same state is liveness, not progress.

The Steward MUST bound connect timeout, idle/progress timeout, operation deadline, parent deadline, retries, concurrency, external calls, and potentially unbounded output/artifacts. Token/cost/browser/research budgets are profile-specific but MUST be explicit when they can exhaust resources.

Execution MUST reserve bounded time/capacity for deterministic finalization: persisting observations, sealing the handoff, releasing leases, recording cancellation/cleanup, and publishing the terminal result. Main work MUST NOT be permitted to consume the entire parent deadline or every worker slot when finalization still requires resources.

Cleanup/control-plane work MAY have a separately bounded reserve so exhaustion of research/model/work budget does not make cancellation or durable closure impossible.

## Persistence recovery and shutdown

The durability claim MUST state its crash model: process restart, host crash/power loss, multi-process, and multi-node guarantees are not interchangeable.

A constrained single-owner experimental profile MAY use a file-backed store only with atomic publication, corruption isolation, recovery, and exclusive ownership. New durable single-instance Steward baselines SHOULD default to a transactional store such as SQLite or equivalent. Multi-worker/multi-instance profiles MUST use a store capable of atomic leasing/compare-and-swap or equivalent concurrency control and explicit migration/version policy.

Durable work and its wake-up/outbox intent SHOULD be committed atomically. The runtime MUST periodically reconcile due durable work so a lost notification cannot orphan a job. Every non-terminal job MUST have a valid owner/lease, scheduled wake-up, recoverable external handle, or explicit blocked reason.

Shutdown/cancellation MUST fence new side effects, persist intent/state before releasing ownership, and perform only bounded cleanup. Recovery MUST prefer resume/reconcile from durable state over reconstructing truth from logs or model memory.

## Observability and diagnostics

Diagnostic logs, durable audit events, and decision evidence are different data classes. The Steward MUST maintain structured correlation sufficient to reconstruct a job: request/job/lineage/generation/attempt/operation identity, stage, logical port/adapter/provider, exact subject reference/digest, request digest, non-secret credential slot, transition/result classification, and trace identity as applicable.

Emit explicit events for admission, lease acquisition/loss, dispatch, delivery ambiguity, reconciliation, retry, circuit state, credential fallback, cancellation, cleanup, evidence acceptance/rejection, supersession, stale-result discard, final identity check, and handoff sealing.

Normal logs MUST use bounded sanitized metadata, digests, sizes, and references rather than secrets, full prompts, protected provider bodies, or unbounded model output. Persistence redaction, external-model disclosure, public-response redaction, and audit retention are separate policy contexts and SHOULD NOT be collapsed into one redaction switch.

Production-capable profiles MUST provide a bounded operator diagnostic/doctor view capable of reconstructing current ownership, open ambiguities, dependency/credential health, deadlines/progress, recovery backlog, and recent durable transitions without source-code inspection.

Every policy-significant stored field MUST have a defined producer, consumer, decision effect, and regression proving that effect. Metrics or flags that no policy ever consumes do not satisfy an enforcement requirement.

## Public MCP surface

Expose outcomes and hide mechanics. Long-running Steward APIs normally provide semantic submit/start, status, result/get, and cancel roles; continue/recheck/reconcile/evidence/doctor operations are added only when the domain requires them. Raw provider/browser/GitHub/Docker/SSH primitives SHOULD NOT be surfaced merely because the Steward uses them internally.

A public long-running start MUST return after durable admission rather than retaining one MCP request for the full workflow. Status/result responses MUST remain bounded and SHOULD return counts, stage, progress class, failure/gap codes, digests, next action, and references; large evidence, timelines, provider output, and artifacts use bounded pagination or explicit artifact retrieval.

Long-lived durable state MUST NOT be mirrored into an ever-growing model conversation.

## Testing and acceptance

Test state-machine and policy logic independently from transports and providers. Every safety/recovery invariant MUST have a negative regression. Use a controllable clock and deterministic barriers/events/fault points for races rather than timing sleeps.

Coverage MUST include applicable crash windows around durable reservation, external dispatch, response/handle persistence, evidence persistence, finalization, and cancellation; restart/lost-wakeup recovery; duplicate idempotency; delivery-unknown/reconciliation; retry exhaustion; lease and stale-generation publication races; cancellation versus completion; deadline/finalization edges; credential fallback and denied fallback; malformed/stale/contradictory provider responses; corruption isolation; and multi-instance ownership when claimed.

Provider adapters MUST be tested against observed upstream-contract fixtures. Test source presence is not execution evidence: canonical gates MUST demonstrate discovery/execution of required cases and distinguish product failure, harness/infrastructure failure, not-executed, stale, partial, and unknown outcomes.

Every advertised MCP transport MUST be exercised with an official client, and the exact packaged/deployed artifact MUST be smoke-tested as required by `mcp-server-architect`. Live/provider acceptance is a distinct lane and MUST remain unclaimed when credentials, target identity, runner capacity, or provider evidence are unavailable.

Historical sanitized incident replays SHOULD become regression fixtures for meaningful races and recovery failures.

## Generated baseline

A Steward generator MUST extend the canonical MCP server generator rather than fork its transport/security/SDK templates. The generated project MUST contain a working durable architecture seed: semantic domain/application/ports/adapters separation, typed Steward profile, durable job/lineage model, external-operation receipt model, idempotent intake, scheduler/recovery hooks, controllable time/fake adapters, structured audit/diagnostics, credential-policy/proof-recipe/upstream-capability templates, and failure-injection scenarios.

The generated baseline MUST demonstrate at least one durable workflow that can be admitted, interrupted after a durable checkpoint, restarted, recovered, and finalized without duplicate side effects. Generated scaffolding is architecture seed evidence only, never production acceptance.

## Verification

Before claiming conformance, validate the Steward profile and public schemas, execute state-machine/persistence/recovery/fault-injection suites, exercise the inherited MCP server and consumer controls, and verify the exact packaged artifact. Where independent assurance is required, candidate-owned tests and model review are diagnostic evidence only; final acceptance requires the configured independent authority.
