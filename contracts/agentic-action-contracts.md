---
description: Normative cross-skill contracts for layered action outcomes, runtime identity, tool-result provenance, deployment leases, durable audit events, and diagnostic reasoning.
doc_id: reference.agentic-action-contracts
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Validate the referenced schemas and run focused regressions for ambiguous outcomes, exact runtime identity, provenance separation, lease admission/replay, append-only audit history, and evidence-driven diagnostic transitions.
---

# Agentic action contracts

## Layered outcomes

`action-outcome.schema.json` is the canonical generic result model. Preserve transport, execution, side effect, artifact publication, verification, disposition, and retry safety as separate axes. A terminal wrapper label or model statement such as `done` is not a substitute for authoritative evidence on those axes.

A client timeout after dispatch may coexist with a confirmed external mutation. A worker process may exit successfully while its required artifact is missing. A published artifact may coexist with failed verification. `verification=stale` means the evidence was valid for an older revision/runtime and cannot prove the current target. When `side_effect=unknown`, disposition remains `pending` or `reconcile_required`; do not collapse an unresolved external effect into terminal `failed` before reconciliation establishes what happened.

Retry policy consumes side-effect state plus an independently reviewed idempotency contract. Transport failure alone never proves replay safety.

## Runtime identity chain

`runtime-identity.schema.json` describes a running instance. `runtime_identity.py` verifies the generic acceptance identity chain:

`source revision -> built artifact digest -> candidate runtime self-report -> deployed runtime self-report`.

Candidate and deployed runtime identity are queried from the running artifacts; they are not inferred from checkout, tag, deployment request, or image label alone. Acceptance fails if source revision or artifact digest differs from the expected candidate.

Artifact identity is stable across a restart of the same artifact. `instance_generation` is instance-scoped and changes when policy requires a new process/deployment generation. Evidence bound to a previous generation is stale for generation-sensitive claims even when the artifact digest is unchanged.

## Tool-result provenance

`tool-result-envelope.schema.json` keeps provider/tool source material and runtime-authored annotations in separate structural domains. `tool_result_envelope.py` hashes exact source bytes before annotation and adds runtime guidance without rewriting source data.

Single-part responses bind `data` to explicit provenance. Multipart or streamed material is represented as source parts, each with its own provenance and optional source-byte digest. Runtime annotations may exist at the envelope or part level but are never attributed to the provider/tool.

Do not solve provenance by stripping known reminder prefixes after source text has already been mutated. Evidence and memory consumers select source data directly from the structured envelope.

## Deployment leases

`deployment-lease.schema.json` is the generic high-impact deployment approval contract. A lease binds the principal/session, exact project/environment/resource, exact artifact digest and optional source revision, one action, keyed normalized-argument digest, policy revision, validity window, and state.

`deployment_lease.py` is the reference admission primitive. It requires an active, unexpired, unconsumed lease and exact matches on every protected dimension. The caller supplies the current `policy_revision`; stale policy authority is rejected. `source_revision` is optional only when neither the lease nor the requested operation binds one; when either side declares it, both sides must provide the same immutable full revision. A parent principal's lease does not authorize a delegated child because principal identity must match. Rollback, restart, migration, promotion, and deployment are distinct actions.

Repository content, prompt text, or child output cannot mint, extend, or reactivate a lease. Credentials stay behind the trusted executor/broker boundary. A timeout after deployment dispatch is reconciled against target runtime identity before any retry; the lease itself does not prove that replay is safe.

## Durable audit events

`audit-event.schema.json` is the common event shape. Preserve event/correlation identity, actor/session, logical capability/operation/target, layered outcome, runtime identity where relevant, artifact/evidence/policy/approval references, and explicit retention class.

Sensitive arguments are represented by approved opaque identity or keyed digest. The common schema accepts `hmac-sha256:` normalized argument digests and deliberately rejects plain `sha256:` argument fingerprints. Raw secrets remain prohibited by the secret-taint contract.

`audit_log.py` is the canonical cross-event semantic validator. `validate_audit_sequence()` rejects duplicate or conflicting event identities, idempotency-key rebinding to another actor/action/target/argument identity, contradictory successful histories, and a second equivalent terminal success for the same idempotency identity. One logical idempotent operation has one canonical successful audit result. A later observation of that already-completed operation must be represented as non-success replay/reconciliation evidence that refers back to the canonical result rather than as another successful terminal event.

`validate_audit_append()` additionally proves that a candidate history preserves the previously accepted history byte-semantically at every existing position. Truncation or rewriting of an accepted prefix is a blocking finding. An append-only storage implementation may enforce stronger durability and concurrency guarantees, but it MUST preserve these same semantic invariants.

Provider-specific details extend `extensions`; they do not replace common outcome or identity semantics.

## Diagnostic reasoning

`diagnostic-state.schema.json` is the bounded provider-neutral representation of observations, hypotheses, planned or executed probes, causal assessment, effective-configuration provenance, and remediation attempts. Observations and facts remain distinct from hypotheses. A transport/status signal may support a hypothesis, but it is not itself proof of root cause.

`diagnostic_reasoning.py` owns deterministic transitions. A probe result can support, contradict, or remain inconclusive. Contradicting evidence moves a hypothesis to `disproven`. A disproven hypothesis persists across handoff/compaction and cannot return to active or supported state unless `reopen_hypothesis()` records a higher revision and genuinely new evidence. Reusing old evidence or silently dropping the disproven hypothesis is invalid.

Repairs are hypotheses too. Before mutation, record the predicted observable postcondition. `record_remediation_result()` then binds the observed postcondition to durable evidence. If the predicted postcondition is absent, the associated hypothesis is disproven rather than blindly retried. Partial or unknown outcomes remain non-terminal evidence.

A configuration candidate is not causal evidence until the effective runtime source is proven. When a causal hypothesis names `config_source_refs`, semantic validation requires each source to be `runtime-proven`. Process liveness, action-specific capability health, dependency health, and configuration observations remain separately scoped.

Causal assessment may be multi-causal. Preserve primary, contributing, necessary-precondition, and credible alternative causes. At most one primary cause is permitted. A caller-provided `support=proven` label is not proof: `validate_diagnostic_state()` resolves every causal evidence reference against observations or executed probes, requires independent source groups for a proven primary cause, verifies that the cited evidence is actually bound to the winning hypothesis, and requires at least one executed probe whose observed outcome matches the winner's prediction while differing from a credible alternative. Correlated evidence from one underlying source is not independent corroboration merely because it appears through multiple model summaries or derived artifacts.

The next diagnostic action is the planned probe with the greatest prediction-separation power across unresolved hypotheses. `select_discriminating_probe()` ranks probes by the number of hypothesis pairs whose declared predictions they distinguish, then by hypothesis coverage and stable probe identity. Repeated wording does not make a probe discriminating, and an identical prediction for every hypothesis has zero discrimination value.

## Composition

These contracts are orthogonal. A deployment audit event may reference a DeploymentLease, include a RuntimeIdentity, and carry an ActionOutcome whose transport and side-effect states disagree until reconciliation. A delegated task can use the same outcome/audit primitives without inheriting deployment authority. Diagnostic reasoning may consume those audit/evidence references without changing their provenance or authority.

Secret-bearing flows additionally follow `secret-taint-standard.md`: prior model visibility never makes raw credentials safe to place in audit records, tool arguments, prompts, or argv.

## Verification

Focused regression coverage includes timeout-plus-confirmed-side-effect, unknown-side-effect reconciliation, completed worker with missing artifact, published artifact with failed verification, stale verification, runtime identity mismatch, same-artifact new-generation checks, source-hash stability under runtime annotations, per-part provenance, expired/revoked/replayed or mismatched deployment leases, delegated-principal denial, rejection of plain secret fingerprints in audit events, duplicate/rebound/conflicting audit histories, duplicate equivalent terminal success, explicit diagnostic reopen, persistence of disproven hypotheses, failed-remediation postconditions, runtime-proven configuration provenance, independent evidence-source enforcement, discriminating-probe ranking, process-vs-capability health separation, and multi-causal assessments.
