---
description: Normative repository-wide contract for governed skill distribution, capability discovery, runtime visibility, and on-demand loading.
doc_id: reference.skill-distribution-consumer-contract
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Validate the skill catalog and installation/runtime-state schemas, run focused distribution/consumer regressions, and verify the exact loaded revision in consumer evidence.
---

# Skill distribution and consumer contract

## Purpose

A governed skill has two separate lifecycles: distribution determines where an artifact is materialized and who owns it; consumption determines whether the current runtime can discover, load, and use that exact artifact. Do not infer one lifecycle from the other.

Project-controlled metadata cannot self-authorize installation into a more privileged scope, and skill prose cannot expand the runtime's tool authority.

## Distribution modes

Every installation declares exactly one mode. Omitted or unknown mode fails closed.

`GLOBAL` is machine/user-scoped and lives outside the consumer project worktree. Installing or updating it must leave the project worktree unchanged. Provenance still records its canonical owner and exact source revision/digest.

`VENDORED` is an intentional project dependency. Its artifact and installation provenance live inside the project and are normal review/CI-visible repository mutations.

`EPHEMERAL` is a bounded task/session materialization below the designated `.ai-skills/ephemeral/` project area. That area must be explicitly ignored before installation. Ephemeral artifacts are never silently staged and have deterministic cleanup.

The canonical executable helper is `skill_distribution.py`.

## Installation ownership and provenance

Every installed artifact records the structure defined by `skill-installation.schema.json`, including `skill_id`, canonical source, immutable source revision, source digest, distribution mode, install scope/path, installation time, manager, update policy, cleanup policy, and per-file ownership digests.

Reinstall of the same source revision/digest is idempotent. Before update or uninstall, verify every installer-owned file. If an owned file was modified outside the installer, fail before mutation. If unowned files appear inside the target, fail before cleanup. Uninstall removes only files whose ownership and digests are proven by the installation state.

Do not use `git add -A` safety as the ownership mechanism. GLOBAL is outside the worktree and EPHEMERAL is ignored by construction; VENDORED changes are intentionally reviewable.

## Capability catalog

`skill-catalog.yaml` is the bounded discovery index. It contains identity/version, declared capabilities, concise use/do-not-use constraints, and supported loading modes. It does not contain full skill bodies.

Resolve `task intent -> capability -> exact skill identity`. Do not guess filenames or repeatedly probe plausible skill names. Keyword similarity alone is not a routing contract.

Catalog identity is attributable through `catalog_revision` and a deterministic catalog digest. Adding catalog entries must not require injecting their full skill bodies into startup context.

## Consumer state model

Keep these states distinct:

- `catalogued`: the governed catalog contains the skill;
- `installed`: an approved distribution artifact exists;
- `runtime-visible`: the selected platform/runtime can currently discover it;
- `loadable`: a loading mode is both declared by the skill and supported by the runtime;
- `loaded`: an exact installed revision/artifact was actually injected or read;
- `compatible`: the runtime satisfies the declared compatibility contract.

`installed=true` is not evidence for runtime visibility or loadability. Repository documentation is not live runtime-visibility evidence.

The canonical runtime-state structure is `skill-runtime-state.schema.json`. The canonical resolver is `skill_consumer.py`.

## Resolution workflow

For each task phase:

1. define the required capability from the active task intent;
2. query the compact governed catalog;
3. select an exact skill identity using declared capabilities and constraints;
4. reconcile live installed, visible, compatible, and loading state;
5. load the exact `SKILL.md`/entrypoint on demand using a supported mechanism;
6. execute under that skill's normative standard and manifest;
7. record loaded skill identity and revision in task evidence or handoff when it materially affects behavior.

If resolution fails, refresh/reconcile runtime visibility once, then classify the failure. Supported classifications include `NOT_INSTALLED`, `NOT_VISIBLE`, `UNSUPPORTED_LOAD_MODE`, `INCOMPATIBLE`, `STALE_LOADED_REVISION`, `NOT_CATALOGUED`, `AMBIGUOUS`, and `UNKNOWN`.

Do not loop through guessed names. A fallback is allowed only when it is explicitly compatible with the required capability and still satisfies the task contract.

## Explicit user-required methods

When the user explicitly requires a particular skill or execution method, unavailability is not permission to silently substitute another approach. The resolver returns a blocked required-skill decision and marks deviation handling as required. The task-intent owner defined by the orchestration contract decides whether scope/method may change.

Resource pressure, context pressure, or convenience cannot widen scope or erase the required method.

## Loading and cache invalidation

Prefer on-demand loading over preloading the entire catalog. Avoid reinjecting unchanged skill bodies into one durable worker/session when the runtime can safely reference the already loaded exact revision.

Invalidate loaded/cache state when the installed revision, installed artifact digest, manifest compatibility, or catalog routing contract changes. A loaded revision that differs from the installed revision is stale and must not be treated as active evidence.

## Security boundary

Untrusted project content cannot authorize GLOBAL installation or privileged loading. Installation into GLOBAL scope requires authority external to the consumer project. Installed skill content is data/instructions within the caller's existing permissions, never a grant of additional tools, secrets, or write authority.

Provenance and runtime visibility are separate evidence. A copied directory without installation state is not a governed installation, and a governed installation that the current runtime cannot see is not loadable.

## Verification

Focused verification covers all three distribution modes, idempotence, modified-owned-file detection, deterministic cleanup, broad-staging safety for EPHEMERAL, exact source provenance, capability resolution without name guessing, installed-vs-visible-vs-loadable distinctions, explicit-required-skill blocking, and stale loaded revision invalidation.

Hosted and local validation must consume the same catalog/schema/helper revision. Final operational evidence records the exact source revision and loaded skill revision where skill behavior affects the result.
