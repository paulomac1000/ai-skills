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
standalone version files in the runtime skill package. A schema required by a
bundled tool is runtime material and belongs in a declared `schemas/` category.

Templates and examples are downstream projections. They cannot add exceptions
to STANDARD.md. A generator should encode stable rules but must not become the
only place where those rules are discoverable.

## Executable resource contract

Use the optional manifest `executable_resources` declaration when a bundled
resource has a supported invocation boundary. Keep internal files undeclared
until a consumer needs that stable contract; this preserves incremental
migration and prevents `tools/` from becoming an accidental public API.
Existing packages add declarations when the supported executable boundary is
next created or materially changed rather than manufacturing CLIs for every
legacy helper.

| Kind | Supported boundary |
| --- | --- |
| `library_helper` | consumed through a declared library API; direct agent execution is not promised |
| `agent_cli` | one canonical script/module/executable invocation for an agent or control plane |
| `host_adapter` | invoked by a trusted host/runtime adapter rather than arbitrary shell discovery |
| `service` | consumed through its declared service/protocol boundary |

The declaration records the bundled resource, invocation mode/entrypoint, input
reference when one exists, structured/human/internal outcome mode, process exit
mapping, timeout/cancellation behavior, explicit safe-stop disposition, effects,
replay safety, network and credential class, and bounded diagnostics. For `python_script`, the declared
Python runtime plus the resource entrypoint is the canonical invocation.

Structured outcomes are required only when machine logic depends on the result.
A human-text helper can remain `human_only`; an internal library can remain
`internal`. Conversely, an exit code cannot collapse domain states such as
PASS, NO_ACTION, INVALID_INPUT, ENVIRONMENT_NOT_READY, or
RECONCILE_REQUIRED into one opaque success/failure bit.

For mutating resources, classify replay and stopping explicitly. If delivery can
be ambiguous after timeout, cancellation, disconnect, or forced stop, use
`reconcile_before_retry` for both replay safety and safe-stop disposition and
retain the operation identity needed for reconciliation. Keep normal diagnostics
bounded; large provider output and raw logs remain behind governed references
or artifacts.

This contract declares what the skill supports. It does not prove that a
particular host installed the runtime, resolved PATH/venv dependencies, or can
invoke the entrypoint. Concrete OpenCode readiness remains owned by
`opencode-stack-guides#189`; validation-environment evidence remains owned by
`ai-skills#122`.

## Composition

When another skill owns a generic rule, depend on or route to it rather than
copying the rule. State the local delta and the condition under which the other
owner applies.

Use the authority-restatement test: if changing the canonical owner would force
a manual edit here, either the duplication is necessary for immediate routing
or it should be replaced by a link to the owner.
