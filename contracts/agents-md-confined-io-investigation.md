---
description: Root-cause classification and regression boundary for the agents-md-architect confined_io import failure reported against ai-skills 1.4.0.
doc_id: decision.agents-md-confined-io-packaging
type: decision
status: active
rigor: normative
owners: [repository-maintainers]
verification: Build the agents-md-architect repository-shaped bundle and execute its audit entrypoint under isolated Python with no custom PYTHONPATH.
---

# agents-md-architect `confined_io` packaging investigation

## Bound release identity

The reported version is the annotated tag `v1.4.0`, which resolves to repository commit `435061ad67ee36d77e01a993bc4f9e4379a29666`.

There is no GitHub Release asset for tag `1.4.0`; the published release identity is the tagged repository tree. Therefore the differential distinguishes the canonical tagged source tree from a consumer-created skill-folder copy rather than inventing a package artifact that the repository did not publish.

## Source differential

At the exact tagged revision:

- `contracts/confined_io.py` exists and is the repository-level owner of bounded, confined file reads;
- `skills/agents-md-architect/tools/audit_agents_md.py`/its implementation imports `confined_io`;
- the audit implementation derives the contracts location from the repository-shaped layout (`skills/<skill>/tools` beneath the repository root);
- the `agents-md-architect` manifest did not declare a repository-level shared resource dependency.

The source module is therefore not missing and no external Python dependency is required.

## Root-cause classification

`WRONG_CONSUMER_LAYOUT` is the primary root-cause class.

A consumer that materialized only `skills/agents-md-architect/` discarded the repository-level `contracts/confined_io.py` dependency while keeping an entrypoint whose import contract expected the repository-shaped tree. The old manifest/distribution model did not make that shared-resource requirement machine-readable, so the invalid layout failed only at runtime.

This is not `SOURCE_MISSING`, `UNDECLARED_DEPENDENCY`, or `STALE_REPORT`. The defect is the missing consumer/bundle contract for an internal repository-owned dependency.

## Corrected contract

`agents-md-architect/manifest.yaml` declares `contracts/confined_io.py` under `dependencies.shared_resources`.

`build_skill_bundle.py` is the canonical artifact builder for a single governed skill. It copies the complete selected skill directory plus only its declared repository-level shared resources while preserving repository-relative paths. This keeps `confined_io.py` canonically owned by `contracts/` rather than duplicating it into the skill.

Distribution then operates on the built bundle root. A bare copy of `skills/agents-md-architect/` is not a valid governed installation when shared resources are declared.

## Clean-install regression

`tests/test_skill_bundle_packaging.py` builds the current `agents-md-architect` bundle, verifies that `contracts/confined_io.py` and the audit implementation are present, removes ambient `PYTHONPATH`, starts Python in isolated mode, and executes the documented audit entrypoint against a separate consumer repository.

The regression also proves that omission of a declared shared resource fails during bundle construction with the missing repository-relative path, before a consumer sees an import traceback.
