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

## Migration first principles

Compare the old and target STANDARD.md, manifest contract, routing boundary,
conditional references, tools, templates, and behavioral evidence before
editing consumers. A version change alone does not justify a rewrite.

Preserve compliant repository-specific behavior when the normative contract is
unchanged. Change the smallest surface that closes the actual delta.

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
