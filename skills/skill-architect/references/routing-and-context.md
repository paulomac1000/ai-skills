---
description: Design skill discovery, trigger boundaries, and progressive context loading that can be evaluated independently of prose style.
doc_id: reference.skill-architect-routing
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Add positive routing cases and applicable near-miss or collision cases, then validate the runtime package and eval corpus.
---

# Routing and context

Read this reference when writing or changing description, SKILL.md, or the
reference topology.

## Description contract

The description is visible before the body is loaded, so it carries the minimum
information required to choose the skill:

- the outcome or operation the skill performs;
- concrete situations in which it should be selected;
- vocabulary a user or upstream agent is likely to use;
- a boundary against the closest competing skill when that collision is real.

Do not depend on hidden body text for the only copy of an activation condition.

## Routing cases

Use positive cases for representative intended requests. Add near-miss negatives
when a prompt contains similar vocabulary but belongs elsewhere. Add collision
cases when two installed skills could plausibly be selected.

Do not score routing by keyword presence. A good case tests task intent.

## Progressive disclosure

Keep common routing and safety information in SKILL.md. Route conditional
knowledge directly to a named reference with both a read condition and the
decision it owns.

Prefer a route that names the condition, concrete file, and owned decision over
a generic "see references" index.

A large reference should expose stable headings or a short map so the consumer
can seek the relevant section without loading unrelated detail.
