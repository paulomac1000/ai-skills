---
afds_schema_version: 2
description: Upgrade-diff workflow for preserving good AGENTS.md content while adopting new standards, validators, evidence contracts, and references.
doc_id: reference.agents-md-migration-upgrade
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Compare the prior and target adoption surfaces, validate the retained instruction tree with the target validator, then run the repository quality gate.
---

# AGENTS.md migration and upgrade

Use this workflow when a repository already has a useful `AGENTS.md` and the target `agents-md-architect` version changes.

## Compare adoption surfaces before editing prose

Classify changes between the previously adopted skill and the target skill across six surfaces:

1. normative standard;
2. rule catalog and applicability;
3. validator behavior;
4. evidence and adoption contract;
5. templates;
6. references and platform guidance.

A version change is not evidence that the repository instruction prose needs a rewrite. If the normative standard and repository-specific boundaries remain satisfied, preserve the current canonical `AGENTS.md` and update only the affected integration, evidence, or validation surface.

## Reference semantics

Treat repository-relative references by semantic kind:

- **concrete file**: must resolve inside the repository to a regular non-symlink file;
- **concrete directory**: may resolve inside the repository to a real non-symlink directory; a trailing `/` is a strong directory signal and directories are appropriate routing/layout targets;
- **path pattern, glob, or placeholder** such as `tests/unit/<domain>/`, `src/*/generated/`, or `packages/{name}/`: validate lexical confinement and explain its meaning, but do not require a literal filesystem entry with that name;
- **canonical owner**: must remain a concrete named file or other explicit durable owner; a directory or pattern is not a substitute for canonical ownership.

The validator must not force natural directory references into awkward prose merely to satisfy a regular-file check.

## Upgrade decision

Prefer the smallest safe result:

- `retain`: current instructions already satisfy the target normative contract;
- `targeted-edit`: one or more repository rules or validator semantics changed and require a focused update;
- `split-or-refactor`: repository layout, ownership, or safety boundaries materially changed;
- `rewrite`: reserved for instruction systems whose canonical structure is no longer recoverable without broad replacement.

Record why the chosen class is necessary. Do not use a new skill version as the reason by itself.

## Extraction and progressive-routing safety

When moving a procedure out of an oversized `AGENTS.md`, treat extraction as a routing migration rather than a file move:

1. identify the one canonical destination;
2. preserve an always-visible trigger that is observable before the first governed action;
3. retain only genuinely pre-load-critical safety invariants beside the trigger;
4. remove substantive procedural duplication from the old location;
5. verify stale section links, backlinks, owner paths, and phase names;
6. verify the destination is not orphaned and the trigger does not exist only inside it;
7. reject two editable trigger indexes; derive any complete catalog from canonical declarations;
8. rerun transition-time and negative-routing evals and compare always-loaded authored bytes before/after.

Use the paired `agents-md: route` / `agents-md: conditional-owner` markers when the repository requires mechanical orphan and duplicate-owner detection. A successful static audit proves only the declared graph; behavioral loading timing remains separate evidence.

## Verification

Run discovery and validation with the target skill version, compare findings against the old validated tree, and distinguish validator/tooling deltas from actual repository-policy deltas. Any formatting or wording change made only to satisfy a parser should trigger a validator review before degrading the document.
