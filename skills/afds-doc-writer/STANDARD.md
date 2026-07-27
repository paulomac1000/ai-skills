---
description: Normative rules for evidence-based, retrievable, maintainable technical documentation.
doc_id: reference.afds-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run `python skills/afds-doc-writer/validate.py README.md RECOVERY_AUDIT.md skills` and `python -m pytest`.
---

# AFDS documentation standard

## Purpose

This standard defines how technical documentation is selected, structured, verified, and maintained for human and agent readers. It keeps the core rules concise while delegating lifecycle and type-specific detail to focused playbooks.

## Core invariants

1. **Evidence before prose.** Durable claims come from implementation, configuration, tests, runtime evidence, authoritative specifications, or accepted decisions.
2. **One canonical owner.** Every durable fact or rule has one authoritative location. Other documents summarize and link.
3. **Answer first.** Put the operational answer, contract, decision, or procedure before background.
4. **Retrieval is designed.** Titles, identifiers, descriptions, aliases, and headings use terms readers will search for.
5. **Statement kinds remain distinct.** Requirements, observations, examples, assumptions, hypotheses, and open questions are not interchangeable.
6. **Verification is explicit.** Operational and normative documents name a command, check, review method, or observable acceptance condition.
7. **Volatile facts belong to automation.** Generated inventories and measurements are produced from sources of truth.
8. **Failure behavior is documented where relevant.** A procedure or system document states safe stop, rollback, degradation, or recovery behavior.
9. **Change impact is visible.** Contract and decision changes identify affected consumers and downstream documents.
10. **Human readability is mandatory.** Metadata supports retrieval and validation but does not replace clear prose.

## Document types

| Type | Primary question | Minimum useful content |
| --- | --- | --- |
| `workflow` | How is an operation performed safely? | Preconditions, ordered steps, verification, safe stop or rollback |
| `reference` | What facts or rules must be looked up? | Scope, definitions, constraints, examples, non-goals |
| `system` | How does a system behave and fail? | Responsibility, boundaries, interfaces, state, failure modes, observability |
| `guide` | How can a reader learn or adopt something? | Audience, outcome, walkthrough, trade-offs, pitfalls |
| `decision` | Why was one option selected? | Context, decision, alternatives, consequences, review trigger |
| `contract` | What must producers and consumers exchange? | Inputs, outputs, errors, compatibility, security, examples |

Choose one primary type. Split documents when readers, ownership, lifecycle, or verification differ.

## Required metadata

```yaml
description: One non-empty sentence stating the question answered
doc_id: <type>.<stable-slug>
type: workflow | reference | system | guide | decision | contract
status: draft | active | evolving | deprecated | archived
rigor: informative | operational | normative
owners: [team-or-role]
verification: Concrete command, check, or review method
```

`description`, `doc_id`, `type`, `status`, and `rigor` are strings. `owners` is a non-empty list of non-empty role or team names. `doc_id` is stable and begins with the selected type. Optional `aliases`, `entities`, `upstream`, `downstream`, `supersedes`, and `review_triggers` are used only when meaningful.

Do not author automation-owned fields such as `last_verified`, generated backlinks, semantic hashes, dependency versions, or fitness scores.

## Structure and links

Every governed document has exactly one H1 outside code examples. H2 sections separate independently retrievable answers. Headings remain unique after normalization.

Relative inline and reference-style links resolve from the containing document. Fenced code, inline code spans, escaped pseudo-links, and image destinations are not treated as documentation links. Valid Markdown titles, angle-bracket destinations, nested parentheses, and longer closing fences are supported.

## Evidence and uncertainty

- Name repository paths, commands, tests, logs, measurements, or authoritative sources when claims depend on them.
- Mark assumptions and state what would verify them.
- Record unresolved questions separately from accepted behavior.
- When sources disagree, state the conflict and the authority selected for current operation.
- Examples are non-authoritative unless explicitly promoted to a contract.

## Canonical ownership and lifecycle

Before adding a document, search for an owner. Update that owner when possible. Permitted duplication is limited to a short linked summary, a labeled example, generated output with a named source, or a migration comparison.

Lifecycle and change-impact rules are defined in [Lifecycle and impact](references/lifecycle-and-impact.md). Document-specific acceptance criteria are defined in [Type playbooks](references/type-playbooks.md).

## Quality gate

A governed document is acceptable when metadata types are valid, one H1 exists, headings are unique, relative links resolve, verification is explicit where required, claims are grounded or labeled uncertain, and ownership is unambiguous.

## Verification

Run the AFDS validator and the repository test suite. Reviewers additionally compare normative claims with the implementation or authoritative source they govern. Structural validation proves consistency, not factual truth.
