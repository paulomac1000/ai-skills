---
description: Maintenance procedure for immutable GitHub Action pins in workflows and reusable template files.
doc_id: workflow.github-action-sha-maintenance
type: workflow
status: active
rigor: operational
owners: [repository-maintainers]
verification: Run template pin tests and verify each updated SHA against the action repository and intended release tag.
---

# GitHub Action SHA maintenance

## Problem

Dependabot updates action references in real workflow files but does not reliably discover arbitrary `.yml.template` files. A green dependency configuration therefore does not prove template pins are current.

## Procedure

1. Inventory every parsed `uses` value in workflows and templates.
2. Exclude local actions beginning with `./`.
3. Reject references without `@` and revisions that are not full commit SHAs.
4. Resolve the intended upstream release tag to a commit using the action's official repository.
5. Review release notes and runtime changes before replacing the SHA.
6. Keep a version comment beside the immutable SHA for readability.
7. Render and parse all templates, then run security and behavior tests.
8. Update all occurrences atomically when a shared action version is part of the repository standard.

Use Renovate with a regex manager or a repository script when automated update proposals are required. The test suite remains the enforcement mechanism.

## Supply-chain checks

Prefer official or well-maintained actions, minimal permissions, no credential persistence, and attestation where artifacts are published. A pin prevents tag movement; it does not make an action trustworthy.

## Verification

Run the parsed-action traversal test. For each changed pin, independently confirm that the SHA belongs to the documented upstream release.
