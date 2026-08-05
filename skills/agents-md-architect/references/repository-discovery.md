---
description: Discover repository evidence before creating or changing AGENTS.md instructions.
doc_id: guide.agents-md-repository-discovery
type: guide
status: active
rigor: operational
owners: [repository-maintainers]
verification: Apply the inventory to a repository and confirm every selected command, owner, and boundary against the assessed revision.
---

# Repository discovery for AGENTS.md

## Outcome

Produce a compact evidence inventory that explains which rules belong in `AGENTS.md`, which belong elsewhere, and which claims remain unverified.

## Discovery sequence

1. Identify the repository root, default branch, assessed revision, active worktree, and any existing root or nested agent instruction files.
2. Read package manifests, solution or workspace files, task runners, container definitions, and environment examples.
3. Trace local and hosted quality gates. Record the fastest focused check and the complete acceptance path separately.
4. Locate architecture decisions, public contracts, generated artifacts, registries, schemas, release procedures, and ownership declarations.
5. Identify sensitive data, secrets, network boundaries, privileged mounts, physical control, external sends, destructive operations, and payment-triggering actions.
6. Inspect recent incidents, review threads, and recurring failures. Keep only lessons that remain likely and are not already enforced automatically.
7. Map distinct work modes and subtrees. Decide independently whether the layout is `single` or `monorepo`, then select the domain profile.
8. Verify every proposed reference and command on the exact revision. Distinguish an executed command from a statically located entry point and from an unverified guess.

## Ignore policy

Discovery ignores a small fixed set of metadata, dependency, and cache directories. It does not ignore every directory named `bin`: root `bin/` scripts and language entry points such as `src/bin/*.rs` may be canonical commands. `.NET` `bin/` and `obj/` directories are ignored only below a detected project root. Treat `.gitignore` and repository manifests as evidence during manual review rather than assuming that a directory name is universally generated output.

## Evidence inventory

Record the following before authoring:

| Question | Evidence |
| --- | --- |
| What is the canonical build entry point? | Repository script, manifest, or CI command |
| What is the smallest meaningful test? | Test runner command and target selection |
| What is the full completion gate? | Repository-owned script or hosted workflow |
| Which files are generated? | Generator, registry, schema, or checked-in notice |
| Which architecture rules are non-obvious? | Decision, dependency graph, or executable test |
| Which operations are high impact? | Authorization policy, deployment boundary, or incident evidence |
| Which documents own specialized procedures? | Task-routed reference with an explicit use condition |
| Which claims could not be verified? | Missing environment, credential, service, authority, or exact invocation |

## Selection test

Add a rule to the root file only when it is needed in many tasks, prevents a costly repository-specific mistake, changes the agent's permissions, or routes the agent to the correct canonical owner. Otherwise place it in a focused workflow, reference, skill, test, or automation.

## Safe stop

Stop authoring when two normative sources disagree, a command cannot be located, generated-file ownership is unclear, or a safety boundary cannot be confirmed. Report the conflict rather than creating a third interpretation.
