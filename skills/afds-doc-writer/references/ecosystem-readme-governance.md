---
afds_schema_version: 2
description: Defines AFDS treatment for README files consumed by package registries, marketplaces, and repository hosting systems.
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

A repository or package `README.md` MAY omit AFDS frontmatter when an external renderer would expose, reject, or misinterpret that metadata. This exception removes only the frontmatter requirement. The document MUST still pass the conventional-document profile for one H1, unique headings, confined relative links, valid anchors, bounded UTF-8 input, and regular-file handling.

A README using frontmatter MAY remain fully governed when every declared publication target is known to preserve the intended rendering.

A root repository README is primarily a product and user entrypoint. Structural validity is necessary but not sufficient. Migration, assurance, provider-control, exact-artifact, and detailed compliance evidence SHOULD be summarized briefly and linked to the canonical governed owner instead of replacing the product-facing entrypoint with an audit report.

A migration MUST NOT replace a useful existing README structure with an assessment or compliance dump unless the repository explicitly declares and justifies that audience change. Before rewriting an existing README, inventory the user-value it already provides, including purpose, quick start, configuration, normal usage, public tools or APIs, security constraints, testing, troubleshooting, and links. Preserve that value or move it deliberately to an equally discoverable canonical destination with a clear README link.

## Supported patterns

Choose exactly one repository-owned pattern:

1. **Governed README** — frontmatter is retained and the renderer compatibility is tested.
2. **Conventional entrypoint** — the README uses the `conventional-document` profile and links to governed normative documents.
3. **Sidecar index** — `docs/index.yaml` records the README identity, owners, lifecycle, normative destinations, and publication targets while the README remains a conventional entrypoint.

A basename alone MUST NOT grant an exception. The repository governance manifest assigns the profile by a confined repository-relative pattern.

## Migration preservation

README migration is a preservation task before it is a restructuring task. The migration assessment SHOULD record which high-value entrypoint functions were preserved, intentionally changed, or moved. A mechanically generated replacement MUST NOT erase project-specific operational knowledge merely because equivalent compliance metadata exists elsewhere.

Do not require one universal heading vocabulary. Evaluate semantic entrypoint functions rather than exact labels. A concise project may combine quick start and usage; a library and a service may expose different navigation. The invariant is that a new reader can still understand what the product is, how to start safely, where its public interface is described, and where deeper governed material lives.

## Durable and volatile information

Put information where its lifetime matches the document:

- `README.md`: durable product behavior, supported usage, enduring constraints, and links to deeper owners;
- production-readiness or adoption assessment: current assurance and provider-backed acceptance state;
- pull-request body: current review, rollout, and process status for that pull request;
- changelog: historical facts attached to a released version;
- commit message: durable semantics and compatibility impact of the committed change.

Provider configuration that may change tomorrow, a current PR draft instruction, pending reviewer state, or a transient CI incident does not belong in durable user documentation or a squash commit message merely because it is true during migration. Prefer automation or the governed assessment that owns the volatile fact.

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

For migrations, structural validation MUST be accompanied by a semantic preservation review of the root README. Passing headings, links, anchors, and UTF-8 checks does not prove that the README remains a useful product entrypoint.
