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

1. Baseline source and candidate revisions of SKILL.md, STANDARD.md, manifest,
   references and eval corpus, plus simple/advanced cases and routing collisions.
2. Record only load-bearing original behaviors in a bounded ledger: stable ID,
   class, disposition, source and destination, activation route, positive and
   negative scenario, verification identity and removal rationale.
3. Reconcile each mandatory invariant and its negative path before removal;
   omitted permissions, safety stops, exceptions, rollback, recovery, proof
   obligations or completion conditions are blocking.
4. Check destination paths and pre-action visibility against the candidate.
   Run the existing skill checker and corpus validator; compare actual
   model-backed outcomes separately when a trusted runner is available.
   Discover supported CLI syntax instead of assuming examples are executable.
5. Keep correctness, routing, active context, context consumption cost, duration
   and reviewability as independent measurements. Unexecuted model comparison
   remains BEHAVIOR_NOT_VERIFIED.
6. Report old-to-new mapping, independent versus duplicate profile rationale,
   versions, observed checks and residual risks.

Optional static diagnostic: `tools/check_refactor_preservation.py` accepts
`--baseline`, `--ledger` and `--candidate`. The synthetic pilot lives in
`evals/skills/skill-architect/`. Its `structural: PASS` has the narrow
`normative_owner_and_route_mapping` scope; it verifies only pinned normative
source/target documents and entrypoint routes. It explicitly reports
`eval_corpus: NOT_VERIFIED` and `behavior: BEHAVIOR_NOT_VERIFIED`.
The caller must independently baseline and validate repository-scoped eval
corpus revisions with `tools/validate_skill_evals.py` plus any required
model-backed comparisons before claiming complete semantic preservation.
Historical Git tree/blob proof comes only from the executing checker's
own trusted repository checkout. The `--candidate` path must resolve to
`skills/<skill-name>` inside that checkout; a foreign or nested candidate-owned
`.git` cannot supply history, while the selected skill resolves to its own
historical subtree (not always `skill-architect`).
Run this verifier from a trusted installed checkout with the baseline Git
objects locally available; otherwise revision verification fails closed.
Never present this static result as a passing corpus migration or model
equivalence check.

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
