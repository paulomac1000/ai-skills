---
name: changelog-release-architect
description: Create, update, audit, verify, and finalize human-facing changelogs and semantic releases from branch, pull-request, integration, and provider evidence while enforcing one version transition per release boundary.
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
14. After integration, inspect the repository publication mode. When it declares `automatic-after-integration`, bind to the integrated SHA, require the declared hosted gates to be terminal-green, and let the protected release path create or converge the declared tag, provider release, and package artifacts without asking for a second publication confirmation.
15. Verify provider-side release identity and artifact checksums against the integrated release SHA. Treat a missing, mismatched, or failed automatic publication as an unresolved release finding rather than stopping at “merged”.
16. Report the base ref, merge-base SHA, baseline version, target version, SemVer class, version-lock state, publication mode, canonical owner, mirrors, integrated SHA, provider release identity, evidence, and unresolved findings.

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

Use `ci-cd-architect` for protected release workflows, exact-artifact promotion, provider trust, and publication. This skill decides the release metadata and publication mode; CI/CD consumes and enforces that decision rather than incrementing it independently. In an `automatic-after-integration` repository, a release-bearing task is not complete merely because its pull request merged: the protected publisher must reach a terminal, identity-verified outcome.

## Constraints

- Never calculate the next version from the version already changed on the branch.
- Never create a second release heading for review fixes in the same release boundary.
- Never treat a commit as a release boundary.
- Never infer compatibility solely from Conventional Commit prefixes.
- Never reuse evidence from an older SHA to certify a later head.
- Never fabricate a release date; use the repository-defined finalization point or `Unreleased`.
- Never rewrite shared history automatically to repair a multi-bump violation.
- When the repository contract declares `automatic-after-integration`, do not ask for an additional publication confirmation after the release boundary is integrated and its required exact-SHA gates are green.
- Publish, tag, package, or deploy only the surfaces explicitly declared by the repository release contract; never invent a deployment target, bypass provider protection, or silently retag a mismatched release.
- If automatic publication is declared but its authority, exact integrated identity, provider controls, or artifact evidence is unavailable, fail closed as `RELEASE_PUBLICATION_BLOCKED` instead of downgrading the repository to a manual-by-default workflow.
