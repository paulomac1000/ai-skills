---
name: qa-change-verifier
description: Plan risk-based verification, bind software-change acceptance to immutable obligations and exact evidence, and define candidate-specific semantic review scope for high-risk changes.
---

# QA Change Verifier

Use this skill to turn a change's admitted obligations, surface, blast radius, statefulness, security sensitivity, and external dependencies into deterministic proof and semantic-review requirements.

Read `STANDARD.md`, then use `tools/plan_verification.py`. When policy supplies admitted acceptance semantics, validate them against `contracts/change-acceptance.schema.json` and bind evidence to that exact semantic digest. Risk determines minimum proof depth; required criteria determine whether the selected evidence actually proves the intended change.

Treat missing, stale, vacuous, deferred, wrong-fixture, incompletely bound, or malformed evidence as non-green; malformed decoded input must fail closed rather than raise. Required proof identity and proof-of-exercise rules apply before PASS or FAIL can affect acceptance, and implementers cannot self-authorize waivers. See `STANDARD.md` for exact artifact/review-plan bindings, trusted known-gap snapshots, and waiver authority.

When semantic review is required, define the exact candidate/base scope with `contracts/semantic-review-plan.schema.json`: trace the important flows, identify high-consequence focus areas and invariants, and select applicable negative-space dimensions. The plan is an input to review, not the review verdict; downstream ReviewReceipt policy remains separately owned.

For persistent-schema or storage migrations, use `tools/migration_acceptance.py` to prove the declared fresh/legacy/unsupported input matrix, the pre-migration state before any current bootstrap can run, the exact production migrator identity/revision, representative data survival, and required interruption/recovery behavior. A green migration test that started from an already-current fixture or invoked another migrator is harness failure, not compatibility evidence.

Risk-only callers remain supported. Low-risk changes may stay on static/unit layers; medium and high risk progressively require integration, exact-artifact, real-transport, external E2E, security review, and post-deploy evidence as specified by the planner.
