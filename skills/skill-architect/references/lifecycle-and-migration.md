---
description: Evolve, migrate, split, and deprecate skills from normative deltas and observed behavior instead of regenerating consumers on version changes alone.
doc_id: reference.skill-architect-lifecycle
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Compare old and target normative contracts, preserve compliant behavior, add regression evidence for changed failure modes, and record any bounded deprecation path.
---

# Skill lifecycle and migration

Read this reference for an existing skill, model upgrade, split, rename, or
deprecation.

## Semantic preservation before deletion

1. Pin old and candidate revisions of SKILL.md, STANDARD.md, manifest, references,
   tools and eval corpus. Record representative simple/advanced cases and nearest
   routing collision. A package audit is not a behavioral baseline.
2. Extract only load-bearing old rules into a bounded ledger, with stable IDs, class,
   disposition, old reference, new canonical owner and target anchor, activation
   route, positive and negative case, verification identity and reason for removal.
   Keep policy in the canonical STANDARD.md, not in the ledger.
3. Check every old required rule against its disposition. Never accept a missing
   authorization, safety stop, exception, rollback, recovery, evidence or DoD
   clause merely because the files parse or became smaller.
4. Verify target paths and pre-action triggers in the actual target package.
   Use existing package auditor and corpus validator, then compare real
   model-backed routing/behavior only when an approved runner is available.
   Do not invent unsupported tool invocations for illustrative commands.
5. Separate correctness/safety, wrong-route rate, actual task-visible context,
   file reads, tokens, latency and reviewability. If real model evidence is absent,
   preserve BEHAVIOR_NOT_VERIFIED even when every structural check passes.
6. Document the before/after contract map, independent versus duplicated
   profile decisions, exact evidence, residual risks and original/candidate SHA.

The optional read-only `tools/check_refactor_preservation.py` checks a JSON
baseline/ledger against file reachability and declared required behaviors:
`python skills/skill-architect/tools/check_refactor_preservation.py
--baseline evals/skills/skill-architect/refactor-pilot-baseline.json
--ledger evals/skills/skill-architect/refactor-pilot-ledger.json
--candidate skills/skill-architect`.
It is a static diagnostic, not a trusted issuer of behavior equivalence.

## Migration first principles

Compare the old and target STANDARD.md, manifest contract, routing boundary,
conditional references, tools, templates, and behavioral evidence before
editing consumers. A version change alone does not justify a rewrite.

Keep compliant consumer-specific behavior when the contract is unchanged;
change only the surface necessary for the normative delta.

## Real-usage maintenance

Inspect representative runs for unexpected skill selection, references always
or never opened, repeated unnecessary reads, bypassed deterministic tools, and
recurring failure modes.

Promote only selection-critical knowledge that is consistently needed. Remove
or reroute dead resources rather than preserving them for history.

## Regression and deprecation

Convert a real reusable failure into the smallest durable invariant plus a
focused regression or eval. Keep incident narratives outside the runtime
package.

When base models eliminate the measurable value of a capability-uplift skill,
simplify or deprecate it rather than accumulating instructions that no longer
improve behavior.

A split, rename, or removal identifies the replacement, compatibility impact,
notice window, and removal condition. Do not maintain parallel current owners.
