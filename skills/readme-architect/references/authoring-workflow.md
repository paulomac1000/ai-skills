---
afds_schema_version: 2
description: Normative authoring detail for readme-architect - workflow steps, evidence preference order, non-negotiable constraints, and completion report content.
doc_id: reference.readme-authoring-workflow
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Run `python skills/readme-architect/tools/audit_readme.py README.md --profile <profile>` and confirm the completion report lists executed verification commands.
---

# README authoring workflow

Normative operating detail for `readme-architect`. The SKILL.md workflow steps
reference the sections below.

## Workflow detail

**Opening region.** State what the project is, who it is for, and its
distinguishing value in one or two short paragraphs. Put a safety or
compatibility callout before the happy path when a user could otherwise operate
the project unsafely or misunderstand a breaking change. Make the primary path
to first success obvious without requiring a reader to understand the
architecture first.

**Happy path.** Prefer the supported distribution artifact over a source build
when the project has one. Include only blocking prerequisites before the quick
start. Show copy-pasteable commands. End the path with an observable
verification step: health endpoint, `--version`, deterministic demo, smoke
command, client connection, or equivalent. For MCP servers, include the
recommended transport/client configuration when that is necessary to obtain
first value.

**Sections.** Summarize dynamic catalogs; link to their canonical owner or
generated reference rather than cloning them into README. Put deep
architecture, exhaustive API/tool schemas, operational runbooks, migration
history, and long troubleshooting material in dedicated docs, linked from the
point where a reader needs them.

**Presentation.** Optimize for scanning: descriptive sentence-case headings,
short paragraphs, parallel lists, compact tables, and focused code blocks. Use
visual assets only when they improve recognition or understanding. Preserve
accessibility and light/dark rendering.

**Factual verification.** Execute safe quick-start and verification commands
when the environment permits. Run repository-owned tests or focused checks that
substantiate security, transport, configuration, or public-contract claims. Do
not convert an unexecuted example into a statement that it works. For
credentialed or external integrations, use the project's deterministic mock,
dry-run, `--help`, schema/introspection endpoint, or other bounded verification
path when available.

## Evidence discipline

For a material README claim, use this preference order unless the repository
defines a stronger owner:

1. explicit machine-readable public contract or generated runtime
   introspection;
2. executable implementation and configuration;
3. tests that assert externally observable behavior;
4. package/build/deployment metadata;
5. maintained canonical documentation;
6. existing README;
7. issue text, PR text, commit messages, or comments.

This is not a rule to ignore package metadata. A runtime/version claim, for
example, often needs package metadata plus CI/runtime evidence. Use the source
that actually owns the specific fact.

## Non-negotiable constraints

- Do not invent badges, versions, coverage, test counts, download counts,
  support matrices, performance claims, compliance levels, endpoints, ports,
  tools, environment variables, or security properties.
- Do not use a static "build passing" badge or hard-coded green status.
- Do not copy secrets into README examples.
- Do not list a dynamic tool/API/configuration catalog as authoritative unless
  it is generated from the canonical source.
- Do not hand-maintain test counts, coverage percentages, line counts, tool
  counts, or similar fast-changing metrics.
- Do not make the README the canonical owner of configuration defaults when a
  schema, typed settings object, manifest, or `.env.example` owns them.
- Do not add a manual table of contents by default. GitHub already exposes an
  outline generated from headings. Add a manual contents block only when the
  repository's long-form navigation demonstrably benefits from it.
- Do not add YAML frontmatter merely for visual or process uniformity. If a
  higher repository standard explicitly governs README metadata, surface that
  contract and follow it rather than inventing a hidden sidecar.
- Do not center normal body text. Centering is acceptable for a small brand
  header, logo, or hero asset.
- Do not use decorative emoji on every heading as a substitute for information
  hierarchy.
- Do not preserve stale README content just because it existed before.
- Do not replace a precise relative repository link with a brittle absolute
  branch URL without a reason.
- Do not claim standards adoption/compliance from a badge or lock file alone.

## Completion report

State the repository profile used, which commands or checks were actually
executed, material claims that could not be verified, canonical-source
conflicts discovered, whether the change introduces new manually maintained
volatile facts, and deeper docs that should also be reviewed.
