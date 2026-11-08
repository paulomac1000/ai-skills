---
description: Normative gate-source budget and deterministic entrypoint classification for AGENTS.md repository audits.
doc_id: reference.agents-md-gate-source-budget
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run `python skills/agents-md-architect/tools/agents_md_gate_sources.py <repository>` and `python skills/agents-md-architect/tools/audit_agents_md.py --strict <repository>` with the same configured limit.
---

# Gate-source budget and entrypoint classification

Use this reference when `audit_agents_md.py` reports the CI/task gate-source budget, when a repository is near the limit, or when a new helper appears to change the count unexpectedly.

## Canonical policy

The canonical classifier is `tools/agents_md_gate_sources.py`. Its current policy revision is `agents-md-gate-sources-13`. Change that revision whenever classification semantics or the default budget change, and add a regression that distinguishes the old and new behavior.

The budget applies to independently meaningful CI/task entrypoints, not to every file that happens to live under `scripts/` or have a script extension. The classifier counts:

- discovered CI workflow/configuration files;
- well-known repository task-runner entrypoints such as `Makefile`, `Justfile`, `Taskfile.*`, `build.sh`, and `build.ps1`;
- commands in the explicit `bin/` entrypoint namespace;
- repository-relative command paths referenced by CI or another public task surface, even after they move outside `scripts/` or `bin/`;
- Python module invocations such as `PYTHONPATH=.agents python -m tools.validator` and direct-script imports resolved against the invocation working directory and effective `PYTHONPATH`, regardless of the target's repository path. Module roots are resolved against the ordered checkout context before local files are attributed: pinned external modules are recorded with their exact external identity and are not inspected as candidate-local code, while nested local candidate checkouts remain eligible. Workflow-, job-, and step-level `PYTHONPATH` and command-local assignments are honored; Python options and versioned interpreters are recognized. `$PWD` resolves against the invocation working directory, and `$GITHUB_WORKSPACE` resolves to the workspace root only when the root checkout is known. Absolute `PYTHONPATH` roots are real-path resolved against the audited checkout rather than classified by string prefix: resolved in-checkout directories become repository-relative roots, existing roots outside the checkout remain non-repository roots, and missing or unresolvable roots produce an inventory issue;
- independently invoked scripts and module targets reached through a bounded CI/task wrapper chain;
- Python script-shaped files that expose an explicit `if __name__ == "__main__":` entrypoint.

A `.py`, `.sh`, or `.ps1` suffix alone is not proof of an independently invokable task. Executable filesystem mode alone is also not proof because mode preservation and execution semantics can differ across archives, filesystems, and checkout environments. A repository-local Python dependency imported by a counted entrypoint is classified as `library`, appears with its importer origin in the source inventory, and is included in the bounded audit read set, but does **not** consume the independent-entrypoint budget unless it has separate invocation evidence. Transitive imports resolve through the same ordered checkout snapshot as entrypoints; pinned external dependencies are recorded by identity and never read as candidate-local libraries. Parent package `__init__.py` files are included for dotted imports, imported initializers retain package context so relative imports remain in the audit read set, and a file that is itself an invoked entrypoint is still traversed under each importer's roots so its dependencies resolve per importing context while its entrypoint classification is unchanged. Wrapper and module descent passes the invoking command's effective `PYTHONPATH` — including command-local assignments — into the nested scan context, and suffixed `$GITHUB_WORKSPACE` roots keep the workspace frame so external vendor content is never re-anchored into a local candidate checkout. Import matching resolves checkout ownership before searching discovered files, so workspace-framed roots inside a local candidate checkout and real-path normalized absolute roots both keep the candidate frame and candidate-relative dependencies cannot silently disappear. Parent package initializers pass through the same ownership resolution before membership checks, so initializer-only dependencies inside a local candidate checkout are found. Module invocations and package mains resolve ownership before the discovered-file check, and normalized absolute roots that already carry the owning checkout alias resolve as workspace paths without double re-anchoring, while candidate-relative roots always retain their directory components under the prepended alias. An invocation that resolves nowhere locally records external ownership for every root that maps into an external checkout, independent of candidate-local file existence, so external-only invocations remain visible in the evidence instead of returning a silent complete inventory. Non-GitHub CI surfaces such as Jenkinsfiles and repository YAML pipelines route through the executable-command parsers, and package.json script bodies are scanned as command sources alongside their public invocation names, so manifest- and CI-owned task references keep their entrypoint coverage instead of silently disappearing. Import roots resolve in runtime order with the invocation directory first, so an earlier external root that could own an invoked module is recorded and blocks complete inventory instead of being silently bypassed by a later candidate-local lookalike. Shell run blocks preserve statically resolvable cd and pushd transitions for subsequent command ownership and fail closed on unresolvable transitions, and local GitHub composite action steps are scanned with unresolved local action references failing closed. An imported dependency or invoked module entrypoint whose module target or ancestor matches a discovered repository symlink is reported as an explicit incomplete-inventory issue; symlink targets are never followed, read, or executed. Missing-module checks recognize the standard library and known installed tooling such as `pip` only when no repository-local namespace could own the target; unresolved repository namespaces remain blocking. Proven `bin/`, shebang, or direct entrypoint evidence takes precedence over a coincident unresolved-module candidate so `count` and `headroom` stay accurate while the unresolved-root issue remains blocking. Import discovery is static AST inspection, bounded to four levels, 256 distinct repository files, and 1,024 distinct import contexts; the same file may be inspected under multiple import roots without consuming the distinct-file budget, while equivalent contexts are deduplicated. It never executes candidate code. Ambiguous module resolution, unresolved ownership, unreadable invoked sources, or exhausted bounds are explicit inventory issues and fail the audit closed rather than silently dropping sources.

An invocation path outside the repository is never read through the repository root or counted as local code. It is listed as `excluded` only when a matching `actions/checkout` path in the same workflow identifies a pinned external commit, the exact trusted-authority output pair (`steps.authority.outputs.repository` / `steps.authority.outputs.revision`), the reusable-workflow authority pair (`job.workflow_repository` / `job.workflow_sha`), or the exact candidate-input pair (`inputs.candidate_repository` / `inputs.candidate_sha`). Same-repository checkout refs are local only when absent or exactly one of `github.sha`, `github.event.pull_request.head.sha`, `github.event.pull_request.head.sha || github.sha`, or `github.event.workflow_run.head_sha`; other dynamic revisions remain inventory issues. Checkout bindings are scoped to the ordered steps of one job and never leak across jobs. Dynamic checkout paths and working-directory escapes remain inventory issues; a path expression is never treated as a literal alias. A dynamic default shell is accepted only for command invocations that both supported shell parsers identify identically; ambiguous source commands remain inventory issues. External identities remain separate acceptance evidence and must be verified by the owning trust-lock or workflow-identity check. An out-of-root path with no matching declared external checkout is an inventory issue and fails closed.

Classification is static and fail-conservative about evidence: it never executes repository-controlled files. A command reference is counted only when the referenced path exists in the discovered revision. Every path row records its classification, count disposition, reason, and invocation/import origins (source path and line when available).

## Output and merge gate

The classifier and `audit_agents_md.py` expose:

- `policy_revision`;
- `count`;
- `limit`;
- `headroom = limit - count`;
- every considered path with `classification`, `counted`, `reason`, and `origins`;
- `issues`, which must be empty for a complete inventory.

The same classifier revision and limit must be used by local validation and hosted/pre-merge validation. A negative headroom is blocking. Zero headroom is allowed but must be visible so that the next true entrypoint cannot become a post-merge surprise.

Do not hide the budget by excluding files from discovery. Full inventory and budget classification are separate concerns.

## Supported remediation

When the budget is exhausted or a source is classified incorrectly:

1. Consolidate genuinely separate public tasks behind a smaller stable task surface when that improves the repository interface.
2. Reclassify a helper only by removing false public-entrypoint evidence and keeping the real entrypoint as its owner. Do not rename or move a true task merely to evade the classifier.
3. If the existing limit or classification model no longer matches legitimate repository structure, revise the policy deliberately: update the policy revision, documentation, focused regressions, and hosted/local parity evidence together.

## Consumer upgrade and rollback

Consumers pin the immutable ai-skills commit that declares the expected `policy_revision`, run the source inventory on the exact candidate/base revisions, and retain the machine-readable count, limit, headroom, classified paths, origins, and issues. Upgrade only after reviewing the newly included invocation paths and the consumer's exact count.

If the new revision exposes a parser defect (for example, an invocation is mis-resolved), keep acceptance blocked, correct the upstream parser with a fixture, and re-run the exact candidate. A consumer may temporarily restore its previously approved pin only under an explicitly owned rollback decision; that rollback does not satisfy #212 source-coverage acceptance. If the corrected inventory legitimately exceeds the unchanged limit, do not restore a path-blind pin, add exclusions, or raise the limit as a shortcut. Consolidate real public entrypoints or request a separately governed capacity decision, then re-run the exact-SHA consumer audit.

Raising the limit solely to make a new file pass is not a supported remediation.

## Historical regression anchor

The September 2026 `stack-hassio` incident is the motivating production case. Revision `414dd5467da6dfc42c537878925eb10246b6fb29` was immediately followed by `14496ffdfd2f05d81a7d89818e086e5e284c21c6`, whose change removed the obsolete `scripts/maintenance/finalize_pr10_bot_review.py` public check and explicitly restored the AGENTS audit under the 64-source limit without relaxing the safety cap.

The regression fixture in `tests/test_agents_md_gate_sources.py` intentionally models that threshold shape rather than claiming that every historical path was a valid independent task. It proves the durable invariant: sixty-four real entrypoints plus an unreferenced helper remain at `count=64`, while a sixty-fifth real entrypoint produces negative headroom.
