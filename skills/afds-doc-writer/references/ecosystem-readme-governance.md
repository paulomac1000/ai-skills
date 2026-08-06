---
description: Defines AFDS treatment for README files consumed by package registries, marketplaces, and repository hosting systems.
doc_id: reference.afds.ecosystem-readme-governance
type: reference
status: active
rigor: normative
owners:
  - Documentation maintainers
verification:
  method: manual-review
  command: python skills/afds-doc-writer/validate.py --repository-root . README.md skills
---
# Ecosystem README governance

## Rule

A repository or package `README.md` MAY omit AFDS frontmatter when an external renderer would expose, reject, or misinterpret that metadata. This exception removes only the frontmatter requirement. The document MUST still pass the conventional-document profile for one H1, unique headings, confined relative links, valid anchors, bounded UTF-8 input, and regular-file handling.

A README using frontmatter MAY remain fully governed when every declared publication target is known to preserve the intended rendering.

## Supported patterns

Choose exactly one repository-owned pattern:

1. **Governed README** — frontmatter is retained and the renderer compatibility is tested.
2. **Conventional entrypoint** — the README uses the `conventional-document` profile and links to governed normative documents.
3. **Sidecar index** — `docs/index.yaml` records the README identity, owners, lifecycle, normative destinations, and publication targets while the README remains a conventional entrypoint.

A basename alone MUST NOT grant an exception. The repository governance manifest assigns the profile by a confined repository-relative pattern.

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
