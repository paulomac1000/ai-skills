---
name: qa-change-verifier
description: Plan risk-based verification, bind software-change acceptance to immutable obligations and exact evidence, and define candidate-specific semantic review scope for high-risk changes.
---

# QA Change Verifier

Use this skill to turn a change's admitted obligations, surface, blast radius, statefulness, security sensitivity, and external dependencies into deterministic proof and semantic-review requirements.

Read `STANDARD.md`, then use `tools/plan_verification.py`. When policy supplies admitted acceptance semantics, validate them against `contracts/change-acceptance.schema.json` and bind evidence to that exact semantic digest. Risk determines minimum proof depth; required criteria determine whether the selected evidence actually proves the intended change.

Treat missing, stale, vacuous, deferred, wrong-fixture, incompletely bound, or malformed runtime evidence/policy input as non-green for a required criterion; malformed decoded input must fail closed rather than raise. Exact-artifact proof must carry a current exact artifact binding, and semantic-review proof must carry the digest of the validated current review plan. A model/implementer may report a known gap but cannot self-authorize a waiver or declare a required criterion not applicable. Acceptance requires a trusted complete known-gap snapshot bound to the exact candidate and contract; the snapshot's full gap records are authoritative, so caller omission or mutation cannot erase durable gap semantics. Supply waiver authority only through a separate trusted policy record bound to the gap scope, exact candidate, acceptance-contract digest, and durable waiver reference.

When semantic review is required, define the exact candidate/base scope with `contracts/semantic-review-plan.schema.json`: trace the important flows, identify high-consequence focus areas and invariants, and select applicable negative-space dimensions. The plan is an input to review, not the review verdict; downstream ReviewReceipt policy remains separately owned.

Risk-only callers remain supported. Low-risk changes may stay on static/unit layers; medium and high risk progressively require integration, exact-artifact, real-transport, external E2E, security review, and post-deploy evidence as specified by the planner.
