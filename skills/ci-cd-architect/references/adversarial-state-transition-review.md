---
afds_schema_version: 2
description: Reusable adversarial review playbook for state machines, durable jobs, leases, and recovery transitions.
doc_id: reference.adversarial-state-transition-review
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Execute the adversarial state-transition fixture regressions against every changed stateful boundary.
---

# Adversarial state-transition review

## Review method

Draw the allowed state graph before reviewing implementation details. For each externally observable transition, identify the authority that authorizes it, the generation/lease it is bound to, its idempotency/replay semantics, and the durable evidence that distinguishes attempted, effected, reconciled, tombstoned, and recovered states.

Exercise every changed stateful boundary against these defect classes: illegal state-graph edges; stale generation evidence; unsafe replay; timeout after an effect with no reconciliation; concurrent writers without serialization; tombstone reuse; lease reuse across generations; partial effects without recovery; and recovery performed on a new generation without rebinding authority/evidence.

## Fail-closed expectations

Stale or ambiguous generation evidence cannot authorize mutation. Timeout-after-effect enters reconciliation before replay. Concurrent writers require one serialization or compare-and-swap authority. Tombstones remain terminal unless a new canonical identity is created. Leases are generation-bound. Partial effects remain explicit until reconciled. Recovery on a new generation requires fresh binding rather than reuse of prior acceptance evidence.

Use `references/adversarial-state-transition-fixtures.yaml` as the minimum executable corpus and `tools/review_state_transitions.py` for stable finding codes. Repositories may add domain-specific cases but must not remove the baseline classes.
