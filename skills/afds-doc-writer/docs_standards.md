---
description: Normative core for engineering documentation optimized for reliable human and agent use
doc_id: reference.documentation-standard
type: reference
status: active
rigor: normative
owners: [docs-maintainers]
schema_version: 3
---

# AI-First Documentation Standard (AFDS) v3

## PURPOSE

Define the minimum rules that make engineering documentation accurate, retrievable, maintainable, and useful during real work. AFDS does not reward template compliance by itself; it rewards correct knowledge transfer.

## PRINCIPLES

1. **Evidence before prose.** A factual claim must be supported by code, configuration, tests, runtime evidence, an authoritative external source, or an explicitly identified human decision.
2. **One canonical owner per fact.** Other documents link to the owner. A short incident-critical invariant may be repeated with a canonical link and a reason.
3. **Answer first.** Put the procedure, contract, decision, or operational state before history and explanation.
4. **Retrieval is a design constraint.** Titles, summaries, identifiers, aliases, and section boundaries must let an agent locate the relevant fragment without reading the repository.
5. **Normative and informative content are distinct.** Requirements, current facts, examples, rationale, and hypotheses must not be presented as the same kind of statement.
6. **Automation owns volatile facts.** Versions, generated inventories, timestamps, coverage, and dependency catalogs come from scripts or manifests.
7. **Human readability remains mandatory.** Machine-readable metadata must not turn the body into a database dump.

## DOCUMENT MODEL

Every governed document has YAML frontmatter with these required fields:

```yaml
description: One sentence that says what question this document answers
doc_id: <type>.<stable-slug>
type: workflow | reference | system | guide | decision | contract
status: draft | active | evolving | deprecated | archived
rigor: informative | operational | normative
owners: [team-or-role]
schema_version: 3
```

Optional retrieval fields:

```yaml
aliases: [terms users or agents may search]
entities: [stable identifiers, services, commands, settings]
upstream: [canonical doc_ids this document depends on]
supersedes: [older doc_ids]
verification:
  method: command, test, runtime probe, review, or source
  target: concrete command, test name, URL label, or artifact
```

Automation-owned fields may be generated into a separate index. Authors must not manually maintain `last_verified`, dependency versions, semantic hashes, fitness scores, or backlinks.

## REQUIRED BODY PROPERTIES

A document must satisfy the selected type profile in `references/document-types.md` and all of the following:

- The H1 names the subject, not the document category.
- The first substantive section answers the primary retrieval intent.
- Commands are copyable and identify the execution context.
- Preconditions and destructive effects appear before the relevant action.
- Boundary conditions that change production behavior are explicit.
- Validation states what observable result proves success.
- Failure handling distinguishes symptom, likely cause, evidence, and recovery.
- Examples are labeled as examples and do not silently define the contract.
- Unknowns state what is unknown, why it matters, and how to resolve it.

## LANGUAGE

Use direct language. In normative sections, use `MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, and `MAY` only with their standards meaning. Elsewhere, natural language is preferred.

Do not globally ban words such as “usually” or “might”. A linter may flag weak language only when it hides an operational condition, probability, owner, or decision.

Bad: “The service might sometimes retry.”

Good: “The client retries `TIMEOUT` twice with 1 s and 2 s delays. It does not retry `AUTH_FAILED`.”

## LINKS AND DEPENDENCIES

- `upstream` points only to documents whose facts are required to understand or execute this document.
- Links must use repository-relative paths or stable external labels.
- A document must not require more than three dependency hops for its primary task. Create a local operational summary when deeper traversal would block incident response.
- Deprecation preserves the old `doc_id`, points to the replacement, and explains the migration impact.

## CHANGE RULES

- Edit the canonical document when a fact changes.
- Update dependent documents only where the changed fact is repeated or changes their procedure.
- Record durable architectural choices as decisions; do not turn every edit into an ADR.
- Contracts use semantic versioning only when consumers can observe compatibility.
- Delete obsolete generated outputs; archive historical decisions that remain useful.

## VALIDATION LEVELS

| Level | Intended use | Required checks |
|---|---|---|
| Informative | explanations and onboarding | metadata, links, headings, no obvious duplication |
| Operational | runbooks and system docs | informative checks plus prerequisites, validation, rollback or safe stop, tested commands |
| Normative | standards, policies, contracts, decisions | operational checks plus explicit rule IDs or testable clauses, conflict scan, owner approval |

Structural validation is necessary but not sufficient. Repository adoption requires both:

1. mutation tests showing the validator catches known documentation defects, and
2. retrieval benchmarks showing the format improves search quality without unacceptable context cost.

## CONFLICT RESOLUTION

When documents conflict:

1. quote both claims and identify their evidence,
2. prefer executable or runtime evidence over prose,
3. prefer the canonical owner over a derivative document,
4. prefer an accepted decision or contract within its scope,
5. do not silently choose between equal evidence; record a knowledge conflict and assign an owner.

## NON-GOALS

AFDS does not prescribe a documentation site generator, embedding model, vector database, prose style, team topology, or one repository layout. It does not replace source code, tests, schemas, or runtime observability.
