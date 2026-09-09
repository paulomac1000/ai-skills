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

The canonical classifier is `tools/agents_md_gate_sources.py`. Its current policy revision is `agents-md-gate-sources-1`. Change that revision whenever classification semantics or the default budget change, and add a regression that distinguishes the old and new behavior.

The budget applies to independently meaningful CI/task entrypoints, not to every file that happens to live under `scripts/` or have a script extension. The classifier counts:

- discovered CI workflow/configuration files;
- well-known repository task-runner entrypoints such as `Makefile`, `Justfile`, `Taskfile.*`, `build.sh`, and `build.ps1`;
- commands in the explicit `bin/` entrypoint namespace;
- repository-relative command paths referenced by CI or another public task surface, even after they move outside `scripts/` or `bin/`;
- Python script-shaped files that expose an explicit `if __name__ == "__main__":` entrypoint.

A `.py`, `.sh`, or `.ps1` suffix alone is not proof of an independently invokable task. Executable filesystem mode alone is also not proof because mode preservation and execution semantics can differ across archives, filesystems, and checkout environments. A helper remains part of discovery inventory but does not consume the entrypoint budget unless public execution evidence makes it an entrypoint.

Classification is static and fail-conservative about evidence: it never executes repository-controlled files. A command reference is counted only when the referenced path exists in the discovered revision.

## Output and merge gate

The classifier and `audit_agents_md.py` expose:

- `policy_revision`;
- `count`;
- `limit`;
- `headroom = limit - count`;
- every considered path with `classification`, `counted`, and `reason`.

The same classifier revision and limit must be used by local validation and hosted/pre-merge validation. A negative headroom is blocking. Zero headroom is allowed but must be visible so that the next true entrypoint cannot become a post-merge surprise.

Do not hide the budget by excluding files from discovery. Full inventory and budget classification are separate concerns.

## Supported remediation

When the budget is exhausted or a source is classified incorrectly:

1. Consolidate genuinely separate public tasks behind a smaller stable task surface when that improves the repository interface.
2. Reclassify a helper only by removing false public-entrypoint evidence and keeping the real entrypoint as its owner. Do not rename or move a true task merely to evade the classifier.
3. If the existing limit or classification model no longer matches legitimate repository structure, revise the policy deliberately: update the policy revision, documentation, focused regressions, and hosted/local parity evidence together.

Raising the limit solely to make a new file pass is not a supported remediation.

## Historical regression anchor

The September 2026 `stack-hassio` incident is the motivating production case. Revision `414dd5467da6dfc42c537878925eb10246b6fb29` was immediately followed by `14496ffdfd2f05d81a7d89818e086e5e284c21c6`, whose change removed the obsolete `scripts/maintenance/finalize_pr10_bot_review.py` public check and explicitly restored the AGENTS audit under the 64-source limit without relaxing the safety cap.

The regression fixture in `tests/test_agents_md_gate_sources.py` intentionally models that threshold shape rather than claiming that every historical path was a valid independent task. It proves the durable invariant: sixty-four real entrypoints plus an unreferenced helper remain at `count=64`, while a sixty-fifth real entrypoint produces negative headroom.
