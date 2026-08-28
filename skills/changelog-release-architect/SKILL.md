---
name: changelog-release-architect
description: Create, update, audit, and verify human-facing changelogs and semantic release versions from branch and pull-request evidence while enforcing one version transition per release boundary.
---

# Changelog release architect

Use this skill when creating or reviewing a changelog, selecting a repository SemVer target, preparing release metadata, or diagnosing release-version drift.

The central invariant is: **one branch or pull request represents at most one repository-version transition unless the repository explicitly declares a larger release boundary.**

Read `STANDARD.md` before mutating release metadata.

## Workflow

1. Discover the repository release contract: instructions, changelog, package manifests, version files, release workflows, tags, version-sync checks, and publication scripts.
2. Resolve the base branch and compute its merge base with `HEAD`. Treat that merge base as the immutable release baseline.
3. Identify the canonical repository version owner and required mirrors. Never create a second owner for convenience.
4. Read `BASE_VERSION` from the canonical owner at the merge base and `BRANCH_VERSION` from the current worktree. Never compute a new target from `BRANCH_VERSION`.
5. Classify the branch as `UNCLAIMED`, `CLAIMED`, or `CONFLICT`. Reuse a valid claimed target; do not bump it again because another agent, commit, or review round arrived.
6. Gather candidate changes from the merge-base diff, public contracts, PR metadata, commits as a discovery index, tests, provider evidence, and exact-revision live evidence.
7. Curate consumer-visible outcomes into `Breaking Changes`, `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, and `Security`; add domain sections only when useful.
8. Choose the highest SemVer impact required by the complete candidate scope. Use domain standards, including MCP compatibility rules, when they refine public-contract classification.
9. If the branch is `UNCLAIMED`, calculate exactly one target from `BASE_VERSION`. If it is `CLAIMED`, edit the existing release section and keep the target unchanged.
10. If later work requires a higher SemVer class after a target was claimed, report `VERSION_SCOPE_CONFLICT`; split the scope or obtain explicit maintainer authorization to retarget and normalize history.
11. Update the changelog idempotently: merge new evidence, remove obsolete claims, deduplicate outcomes, and never create an intermediate release heading.
12. Verify quantitative, security, compatibility, artifact, performance, and live-system claims against evidence bound to the exact revision or artifact they describe.
13. Run `tools/check_release_branch.py` plus repository-owned version, changelog, package, build, test, and release gates.
14. Report the base ref, merge-base SHA, baseline version, target version, SemVer class, version-lock state, canonical owner, mirrors, evidence, and unresolved findings.

## Source priority

Use evidence in this order:

1. merge-base-to-HEAD behavior-bearing diff;
2. public contracts, schemas, manifests, and compatibility declarations;
3. PR title, body, labels, linked issues, and accepted review decisions;
4. commits only as an index for discovering changes;
5. tests and machine-generated evidence;
6. hosted/provider evidence;
7. exact-revision live-system evidence.

Chat summaries, plans, memory, and commit titles alone are not evidence of shipped behavior.

## Writing rule

Write for a consumer deciding whether and how to upgrade. Prefer outcomes over implementation mechanics.

Do not copy `git log`, invent issue links or metrics, or preserve review bookkeeping as release history. A useful breaking-change entry states what changed, who is affected, and the migration path when one exists.

Prefer `Unreleased` as the staging area when the repository follows Keep a Changelog. A versioned heading is materialized once per release boundary; later branch work edits that heading instead of creating another.

## MCP routing

For an MCP server, use `mcp-server-architect` to determine MCP public-contract compatibility. This skill owns the repository-level SemVer target and changelog materialization; MCP capability/schema versions remain independently governed.

## CI/CD routing

Use `ci-cd-architect` for protected release workflows, exact-artifact promotion, provider trust, and publication. This skill decides the release metadata; CI/CD consumes and enforces that decision rather than incrementing it independently.

## Constraints

- Never calculate the next version from the version already changed on the branch.
- Never create a second release heading for review fixes in the same release boundary.
- Never treat a commit as a release boundary.
- Never infer compatibility solely from Conventional Commit prefixes.
- Never reuse evidence from an older SHA to certify a later head.
- Never fabricate a release date; use the repository-defined finalization point or `Unreleased`.
- Never rewrite shared history automatically to repair a multi-bump violation.
- Never publish, tag, deploy, or create a provider release unless explicitly requested.
