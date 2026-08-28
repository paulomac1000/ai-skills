---
afds_schema_version: 2
description: Defines AFDS publication and structural treatment for README files consumed by package registries, marketplaces, and repository hosting systems.
doc_id: reference.afds.ecosystem-readme-governance
type: reference
status: active
rigor: normative
owners:
  - Documentation maintainers
verification:
  kind: command
  value: python skills/afds-doc-writer/validate.py --repository-root . README.md skills
---
# Ecosystem README governance

## Rule

AFDS owns the repository decision about README metadata, publication compatibility, structural validation, link confinement, anchors, bounded input, and lifecycle. `readme-architect` (see `skills/readme-architect/STANDARD.md`) owns evidence selection, product-entrypoint content, onboarding structure, presentation, volatility policy, and README-specific completion checks.

A repository or package `README.md` MAY omit AFDS frontmatter when an external renderer would expose, reject, or misinterpret that metadata. This exception removes only the frontmatter requirement. The document MUST still pass the selected conventional-document profile for one H1, unique headings, confined relative links, valid anchors, bounded UTF-8 input, and regular-file handling.

A README using frontmatter MAY remain fully governed when every declared publication target is known to preserve the intended rendering.

A basename alone MUST NOT grant an exception. The repository governance manifest assigns the profile by a confined repository-relative pattern.

## Supported patterns

Choose exactly one repository-owned pattern:

1. **Governed README** — frontmatter is retained and renderer compatibility is tested.
2. **Conventional entrypoint** — the README uses the `conventional-document` profile and links to governed normative documents.
3. **Sidecar index** — `docs/index.yaml` records README identity, owners, lifecycle, normative destinations, and publication targets while the README remains a conventional entrypoint.

The choice among these patterns is an AFDS governance decision. It does not define the README's product-facing section order or presentation.

## README content routing

When `readme-architect` is adopted, use its standard and profile references for README content and presentation. Do not duplicate its quick-start, security-projection, badge, visual, dynamic-catalog, volatile-fact, or migration-preservation rules here.

A structural AFDS pass does not prove that a README is a useful product entrypoint. Conversely, a polished README render does not replace AFDS confinement, anchor, metadata/profile, or lifecycle checks.

For README migration, AFDS verifies the selected document profile while `readme-architect` verifies that useful existing onboarding knowledge is preserved or deliberately moved to an equally discoverable canonical owner.

## Durable ownership boundary

Use the owner whose lifecycle matches the fact:

- `README.md`: concise, durable product behavior, supported onboarding, enduring operational constraints, and links to deeper owners;
- governed architecture, contract, runbook, or reference documents: detailed durable rules and procedures;
- production-readiness or adoption assessment: current assurance and provider-backed acceptance state;
- pull-request body: current review, rollout, and process state for that pull request;
- changelog: historical facts attached to a released version;
- commit message: durable semantics and compatibility impact of the committed change.

Provider state that may change tomorrow, transient CI incidents, pending reviewer state, and current PR bookkeeping do not become durable README facts merely because they are true during migration.

## Sidecar minimum contract

A sidecar index MUST declare:

```yaml
schema_version: 1
entrypoint: README.md
profile: conventional-document
owners:
  - Documentation maintainers
normative_documents:
  - skills/example/STANDARD.md
publication_targets:
  - pypi
```

The entrypoint and every normative document MUST remain inside the repository, MUST NOT traverse symlinks, and MUST identify bounded regular UTF-8 files.

## Acceptance

The AFDS quality gate MUST validate the README under its selected profile and every linked governed document under its own profile. A successful package build or marketplace rendering does not replace structural and link validation.

Where `readme-architect` applies, its evidence, onboarding, drift, presentation, and domain-routing checks are additional acceptance criteria rather than AFDS replacements.
