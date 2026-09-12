---
name: qa-change-verifier
description: Plan risk-based verification layers for software changes and bind release confidence to exact evidence rather than stale simulators or harness noise.
---

# QA Change Verifier

Use this skill to turn a change's surface, blast radius, statefulness, security sensitivity, and external dependencies into a deterministic verification plan.

Read `STANDARD.md`, then use `tools/plan_verification.py`. Treat exact evidence binding, simulator freshness, and harness-vs-product failure classification as part of the verification result, not optional commentary.

Low-risk changes may stay on static/unit layers. Medium and high risk progressively require integration, exact-artifact, real-transport, external E2E, security review, and post-deploy evidence as specified by the planner.
