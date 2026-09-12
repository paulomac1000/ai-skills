---
afds_schema_version: 2
description: Normative risk-based verification planning, exact-evidence binding, simulator freshness, and failure-attribution rules.
doc_id: reference.qa-change-verifier-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Run qa-change-verifier planner regressions and the repository exact-head gate.
---

# QA change verifier standard

## Risk planning

Verification depth follows evidence risk, not changed-line count. Plan from public/change surface, blast radius, stateful behavior, security sensitivity, external dependencies, and whether post-deploy behavior is material. The baseline layers are static, unit, integration, exact artifact, real transport, external E2E, security review, and post-deploy.

Low risk requires static and unit evidence. Medium risk adds integration and exact-artifact evidence. High risk requires the complete baseline so public/state/security/external failures cannot hide behind narrow tests.

## Exact evidence

Evidence granting candidate confidence MUST identify the exact candidate revision and an immutable artifact digest where an artifact layer applies. Evidence from another revision is stale. A simulator/model is advisory only when its revision differs from the candidate; stale simulation cannot substitute for exact artifact or real-transport evidence.

## Failure attribution

Verification MUST distinguish harness failure from product failure. A broken harness blocks the affected verification claim but is not evidence that the product failed; a product failure remains product evidence even when the harness also has faults. Mixed conditions stay explicit until separated.

## Definition of done

The risk class and required layers are deterministic; exact evidence is candidate-bound; stale simulation is invalidated; harness and product failures are not conflated; and every required layer is either satisfied by exact evidence or explicitly non-green.
