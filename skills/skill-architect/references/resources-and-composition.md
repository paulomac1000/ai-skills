---
description: Choose the right skill resource type, degree of freedom, and dependency relationship without duplicating canonical policy.
doc_id: reference.skill-architect-resources
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Review each bundled resource for a real activation need, canonical owner, and representation appropriate to the operation's risk and determinism.
---

# Resources and composition

Read this reference when deciding whether knowledge belongs in prose, a
reference, template, schema, example, or tool.

## Representation matrix

| Need | Preferred representation |
| --- | --- |
| Context-dependent judgment | normative prose |
| Conditional detailed guidance | reference |
| Adaptable repeated structure | template |
| Strict machine-readable shape | schema |
| Deterministic repeated mechanics | tool |
| Fragile or high-impact mechanics | tool plus validation gate |
| One illustrative application | example |

Use the lowest degree of freedom that still permits necessary judgment.

## Resource discipline

Do not create optional directories until a real task requires them. Do not
bundle developer reports, benchmark output, eval corpora, a local changelog, or
standalone version files in the runtime skill package.

Templates and examples are downstream projections. They cannot add exceptions
to STANDARD.md. A generator should encode stable rules but must not become the
only place where those rules are discoverable.

## Composition

When another skill owns a generic rule, depend on or route to it rather than
copying the rule. State the local delta and the condition under which the other
owner applies.

Use the authority-restatement test: if changing the canonical owner would force
a manual edit here, either the duplication is necessary for immediate routing
or it should be replaced by a link to the owner.
