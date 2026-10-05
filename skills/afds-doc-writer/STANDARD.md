---
afds_schema_version: 2
description: Normative rules for evidence-based, retrievable, maintainable technical documentation.
doc_id: reference.afds-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Run `python skills/afds-doc-writer/validate.py --repository-root . README.md RECOVERY_AUDIT.md contracts skills` and `python -m pytest`.
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
6. **Verification is explicit where rigor requires it.** Operational and normative documents name a command, CI job, review method, or observable acceptance condition through the required metadata contract. Informative documents may omit verification.
7. **Volatile facts belong to automation.** Generated inventories and measurements are produced from sources of truth.
8. **Failure behavior is documented where relevant.** A procedure or system document states safe stop, rollback, degradation, or recovery behavior.
9. **Change impact is visible.** Contract and decision changes identify affected consumers and downstream documents.
10. **Human readability is mandatory.** Metadata supports retrieval and validation but does not replace clear prose.
11. **Decision authority is not implementation completion.** An accepted/current decision may still have unresolved implementation, migration, rollout, cleanup, or verification consequences; document lifecycle status must not collapse those facts.

## Document types

| Type | Primary question | Minimum useful content |
| --- | --- | --- |
| `workflow` | How is an operation performed safely? | Preconditions, ordered steps, verification, safe stop or rollback |
| `reference` | What facts or rules must be looked up? | Scope, definitions, constraints, examples, non-goals |
| `system` | How does a system behave and fail? | Responsibility, boundaries, interfaces, state, failure modes, observability |
| `guide` | How can a reader learn or adopt something? | Audience, outcome, walkthrough, trade-offs, pitfalls |
| `decision` | Why was one option selected? | Context, decision, alternatives, consequences, review trigger; implementation consequences when material |
| `contract` | What must producers and consumers exchange? | Inputs, outputs, errors, compatibility, security, examples; observable acceptance mapping when it is the behavioral source of truth |

Choose one primary type. Split documents when readers, ownership, lifecycle, or verification differ.

## Executable behavior and acceptance contracts

A `contract` document may specialize as the durable behavioral/acceptance source of truth for a non-trivial software change without becoming a new AFDS document type. When that specialization applies, the contract records the smallest complete set of applicable behavior dimensions: scope and non-scope, stable obligation references when the repository has them, observable acceptance criteria, normal flows, negative/edge/failure flows, public effects and compatibility constraints, decision references, and verification mapping.

The following rules are normative:

- obligations or requirements state what is required; acceptance criteria state observable/falsifiable outcomes; assumptions, examples, and evidence remain distinct statement kinds;
- criteria describe externally distinguishable acceptance outcomes rather than implementation guesses, unless the implementation mechanism itself is part of the public contract;
- stable obligation/criterion identifiers from another canonical contract may be referenced by ID/digest, but AFDS does not copy or fork that machine contract;
- verification mapping names the owning proof mechanism, criterion/evidence reference, or verification plan; mutable PASS/FAIL results, provider run state, review receipts, and timestamps remain evidence records rather than durable frontmatter;
- an `active` behavioral contract states current authority for the documented behavior, not proof that an implementation currently satisfies it;
- when a public wire/data/schema contract is machine-readable and canonical, prose explains or links to it but cannot override it.

`qa-change-verifier` remains the owner of risk-directed verification planning and exact evidence. Review/evidence receipts remain their owning systems' records and are referenced rather than copied into AFDS documents.

## Decision authority and implementation completion

For a `decision` document, **decision accepted is not the same fact as decision implemented**. `status: active` means the document is a current authoritative decision record; it does not assert that every implementation consequence has completed.

When a decision materially affects implementation, the document records or links the applicable consequences needed to make its implementation state auditable: affected obligations/criteria, affected consumers and surfaces, ordered implementation consequences, migration/compatibility, rollout, rollback, cleanup/removal of superseded paths, required verification, downstream review, and completion semantics. Omit genuinely inapplicable dimensions rather than filling them with boilerplate, but do not hide a material consequence behind generic prose.

A decision may claim implementation completion only when every **declared mandatory** consequence is resolved: satisfied consequences have current evidence or an authoritative implementation reference, and non-applicable consequences carry a reason. Any required consequence that is pending, blocked, unknown, missing required verification evidence, or still awaiting downstream review keeps the implementation claim incomplete. Acceptance authority remains intact while those consequences are unfinished unless the decision itself is superseded or otherwise changes lifecycle state.

Do not add a second global AFDS status enum, hand-maintained completion score, or `last_verified`-style field to represent this distinction. Repositories may use their own machine-readable work/change contract as the consequence source; AFDS records durable semantics and references, while executed verification, CI, review, and receipt state stays in the evidence system that owns it.

Implementation consequences flow through the existing AFDS lifecycle/change-impact protocol. A decision that changes a consumer or public/operational promise must enumerate that downstream review result rather than creating a parallel dependency graph.

## Required metadata

Every newly authored governed document uses the current AFDS document schema identified by `afds_schema_version: 2`:

```yaml
afds_schema_version: 2
description: One non-empty sentence stating the question answered
doc_id: <type>.<stable-slug>
type: workflow | reference | system | guide | decision | contract
status: draft | active | evolving | deprecated | archived
rigor: informative | operational | normative
owners: [team-or-role]
verification:
  kind: command | ci-job | manual-review | observable
  value: Concrete method or acceptance condition
```

`description`, `doc_id`, `type`, `status`, and `rigor` are strings. `owners` is a non-empty list of non-empty role or team names. `doc_id` is stable and begins with the selected type. Optional `aliases`, `entities`, `upstream`, `downstream`, `supersedes`, and `review_triggers` are used only when meaningful.

For `operational` and `normative` documents with `afds_schema_version: 2`, `verification` is required and is an object containing exactly `kind` and `value`. `value` is a non-empty string. `Informative` documents may omit verification; when present it uses the same typed shape.

A `## Verification` section explains commands, criteria, or review detail for readers. In the current versioned schema it never substitutes for metadata. The metadata names the method; executed results belong to conformance, evidence, CI, or review records rather than durable document frontmatter.

The machine-readable schema is `contracts/afds-frontmatter.schema.json`. The standalone validator additionally enforces relationships such as `doc_id` type prefixes, repository confinement, and document structure.

Do not author automation-owned fields such as `last_verified`, generated backlinks, semantic hashes, dependency versions, or fitness scores.

### Legacy migration

A governed document without `afds_schema_version` is read using the legacy implicit version 1 contract. That compatibility mode remains readable during migration and may use a non-empty metadata value or `## Verification` section for operational or normative rigor.

Legacy compatibility is not the target authoring format. Repositories complete migration by converting verification to the current object form, adding `afds_schema_version: 2`, and enabling:

```text
python skills/afds-doc-writer/validate.py \
  --repository-root . \
  --minimum-document-schema 2 \
  <governed-inputs...>
```

The strict option returns a deterministic migration finding for implicit-version documents. Unknown schema versions fail closed. A repository must not label itself fully migrated while its governed scope still depends on legacy compatibility.

## Governance profiles

A repository assigns validation behavior through `governance.yaml`; a document is never exempted only because its basename is `README.md`, `SKILL.md`, or `CHANGELOG.md`.

The `governed` profile requires AFDS metadata, one H1, unique headings, confined links, valid anchors, and verification according to rigor. The `conventional-document` profile may omit AFDS frontmatter but still checks structure, links, anchors, bounded input, and repository confinement. `human-facing` remains a compatibility alias with the same structural guarantees. Additional profiles must state every enabled check explicitly and fail closed when the governance file is malformed.

Assignments are repository-relative POSIX globs. The repository declares one default profile and a reviewed ordered list of overrides. A filename convention may select a profile only through this explicit manifest.

When a conventional document contains AFDS frontmatter, the validator validates that metadata rather than treating the file as exempt. Ecosystem entrypoints such as a root README follow [Ecosystem README governance](references/ecosystem-readme-governance.md): use supported frontmatter, a sidecar index, or an informational entrypoint linked to governed documents.

## Structure and links

Every governed document has exactly one H1 outside code examples. H2 sections separate independently retrievable answers. Headings remain unique after normalization.

Relative inline and reference-style links resolve from the containing document. Fenced code, inline code spans, escaped pseudo-links, and image destinations are not treated as documentation links. Valid Markdown titles, angle-bracket destinations, nested parentheses, and longer closing fences are supported.

The validator receives a repository root and confines both source documents and relative link targets to it. Source paths and link targets are regular, bounded UTF-8 files with no symlink or reparse-point component. Absolute paths, parent traversal, backslash-based ambiguity, directory targets, oversized targets, and repository escapes fail closed. A `#fragment` must resolve to an actual normalized heading anchor in the target document; existence of the target file alone is insufficient.

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

A governed document is acceptable when metadata types are valid, one H1 exists, headings are unique, relative links and anchors resolve within the repository, verification is explicit where required, claims are grounded or labeled uncertain, and ownership is unambiguous. A human-facing or conventional document is acceptable only when its selected profile passes every enabled structural and confinement check.

Legacy implicit-version compatibility proves only that an older document remains readable. Full AFDS conformance additionally requires the strict minimum-document-schema gate over the declared governed scope.

## Verification

Run the AFDS validator with the repository governance file and the repository test suite. Reviewers additionally compare normative claims with the implementation or authoritative source they govern. Structural validation proves consistency, not factual truth.
