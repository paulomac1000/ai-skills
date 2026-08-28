---
afds_schema_version: 2
description: Normative rules for evidence-driven changelogs, semantic release classification, and one-version-per-release-boundary metadata.
doc_id: reference.changelog-release-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Run the history-aware release validator against the candidate and its merge-base, then execute repository-owned version, changelog, and release gates.
---

# Changelog and release versioning standard

## Purpose

A changelog is a curated consumer-facing record of notable release differences, not a commit archive or implementation diary. A repository version is a compatibility contract, not an iteration counter for agents.

## Release boundary and baseline

By default, one pull request is one release boundary. Commits, review fixes, generated-file repairs, and follow-up edits inside it are not releases.

A repository may declare a larger release boundary, such as a release branch collecting several pull requests. The explicit repository contract then controls the boundary, but agent iterations still must not create intermediate versions.

Let `M` be the merge base between the candidate and its selected base ref. `V_base` is the canonical repository version at `M`; `V_branch` is the current version. Every automatic target calculation MUST use `V_base`, never `V_branch`.

A candidate must contain at most one distinct repository-version transition after `M`. History such as `1.3.0 -> 1.4.0 -> 1.5.0` is invalid even if the final tree is internally consistent.

## Canonical ownership and lock state

Every versioned repository SHOULD have one canonical repository-version owner. Package files, runtime constants, lockfiles, manifests, badges, and discovery output may mirror it only when the repository contract requires them.

Discover ownership from explicit release policy, repository instructions, release automation, version-sync checks, package/build metadata, and established convention, in that order. Conflicting owners fail closed.

Classify the candidate:

- `UNCLAIMED`: current version equals the baseline and no candidate release heading establishes a target.
- `CLAIMED`: exactly one internally consistent target differs from the baseline.
- `CONFLICT`: sources disagree, multiple targets/headings exist, the target is not one direct allowed transition, or current scope requires a higher class than the claimed target.

A `CLAIMED` target is reused by later agents. Re-running the workflow must converge on the same version.

## Evidence and changelog content

Use the candidate diff as the primary source of shipped behavior. Public contracts determine compatibility. PR metadata supplies intent; commits are only a discovery index. Tests, hosted CI, artifacts, and live-system observations support only the claims and exact revisions they actually verify.

A change is notable when a consumer, operator, integrator, or maintainer may need it to use a capability, adapt behavior, migrate, avoid a regression, understand compatibility or security, or deploy/configure correctly.

Prefer `Breaking Changes`, `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, and `Security`. Additional sections such as `Migration Notes`, `Compatibility`, `Dependencies`, `Infrastructure`, `Verification`, `Known Limitations`, or `Deferred` are allowed when they materially help. Do not create empty catch-all sections.

Deduplicate by outcome. Internal refactors, formatting, ordinary test churn, branch bookkeeping, and the fact that a version number changed are normally excluded.

Quantitative claims such as test counts, coverage, latency, tool counts, and package sizes require exact evidence and should appear only when they materially support a release guarantee.

## Semantic version classification

For stable `1.0.0+` releases:

- `MAJOR`: a correct consumer of the previous public contract may need to change to upgrade.
- `MINOR`: backward-compatible public functionality or a public deprecation is added.
- `PATCH`: backward-compatible defects, reliability, security hardening, packaging, or documentation usability are corrected.

The highest impact in the complete release boundary wins. Classification follows behavior, not changed-line count or commit prefix.

Unless the repository defines a different pre-1.0 policy, use the next `0.(Y+1).0` for additive or breaking public capability changes and `0.Y.(Z+1)` for compatible fixes.

A direct stable transition from `X.Y.Z` is one of `X.Y.(Z+1)`, `X.(Y+1).0`, or `(X+1).0.0`. Skipped intermediate numbers are not automatically inferred.

## Scope growth and idempotence

Materialize the version only after intended public scope is reasonably stable; `Unreleased` may accumulate changes before that point.

If later work requires a higher SemVer class after the target is claimed, report `VERSION_SCOPE_CONFLICT`. Prefer splitting the new scope. Retargeting requires explicit maintainer authorization and history normalization so the final PR still represents one version transition.

Repeated runs update the same release section, add new evidenced outcomes, remove invalidated claims, and never increment because the workflow ran again.

If the base advances, recompute the merge base. A target that no longer forms a valid single transition produces `BASELINE_DRIFT`; do not bump around it automatically.

## MCP compatibility profile

For MCP servers, the public compatibility surface includes tool/resource/prompt names, input schemas, required arguments, response semantics, errors, manifests, discovery, transports, authentication/authorization, target selection, retry/ambiguous-outcome behavior, and externally relevant session state.

Removing or renaming public components, adding required parameters, removing relied-on fields, or incompatibly changing transport, authorization, target, retry, or error semantics is normally `MAJOR`.

Adding a component, semantics-preserving optional parameter, ignorable response metadata, or an additional transport is normally `MINOR`.

Correcting documented behavior or hardening lifecycle, security, redaction, concurrency, logging, or artifacts without changing the public contract is normally `PATCH`.

`mcp-server-architect` remains the canonical owner of MCP contract semantics. This standard maps that evidence to repository SemVer and changelog only.

## Legacy and release dates

A repository without a discoverable changelog/version contract requires discovery of tags, provider releases, package metadata, runtime output, published artifacts, and historical workflows before mutation. Do not reconstruct uncertain releases from commit dates; report `RELEASE_CONTRACT_MISSING` when current identity cannot be established.

A versioned heading should use the actual release date. Branch creation, first commit, and agent execution dates are not automatically release dates. Use `Unreleased` or the repository-defined finalization convention until the date is established.

## Verification and findings

Before completion verify: base ref and merge base; canonical baseline version; no more than one version transition; no more than one new release heading; current target is a direct permitted transition; required mirrors agree; SemVer class matches public impact; material claims have exact evidence; and repository release gates pass.

Stable findings are:

- `RELEASE_CONTRACT_MISSING`
- `BASE_REF_AMBIGUOUS`
- `VERSION_SOURCE_CONFLICT`
- `MULTIPLE_VERSION_TRANSITIONS`
- `MULTIPLE_RELEASE_HEADINGS`
- `VERSION_SCOPE_CONFLICT`
- `SEMVER_CLASSIFICATION_CONFLICT`
- `CHANGELOG_EVIDENCE_MISSING`
- `REVISION_EVIDENCE_STALE`
- `VERSION_MIRROR_DRIFT`
- `BASELINE_DRIFT`

`VERSION_ALREADY_CLAIMED` is informational: reuse the target.

## Definition of done

The release boundary and baseline are explicit; one canonical owner is known; at most one repository-version transition exists; mirrors agree; the changelog describes the complete notable consumer impact; breaking/deprecation/migration information is actionable; claims are bound to appropriate evidence; repeated execution preserves the same target; and repository release gates pass or unavailable checks are reported precisely.
