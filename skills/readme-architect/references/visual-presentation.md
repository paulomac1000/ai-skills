---
afds_schema_version: 2
description: Presentation and accessibility guidance for README openings, badges, visuals, diagrams, headings, tables, code blocks, and public repository metadata.
doc_id: reference.readme-visual-presentation
type: reference
status: active
rigor: informative
owners: [repository-maintainers]
---

# README visual presentation

Presentation serves comprehension first and branding second.

## Opening composition

Prefer:
- one H1;
- a restrained badge row;
- a crisp tagline/value proposition;
- one strong visual only when it demonstrates identity, output, or a verified
  differentiator;
- an obvious route to Quick start.

Avoid:
- multiple screens of logos/badges before the project is explained;
- centered body paragraphs;
- badge walls;
- animated decoration;
- an emoji prefix on every heading;
- giant project trees or config tables above onboarding.

## Badges

Good opening badges answer concrete questions:
- does CI currently pass?
- what package/release should I install?
- what runtime versions are officially supported?
- what license applies?
- where are the docs/container/package?

Rules:
- use live badge sources;
- link a badge to its relevant destination;
- provide alt text;
- normally keep the opening set to five or fewer;
- do not duplicate information already obvious and stable;
- never fabricate a badge with static `build-passing`, `coverage-XX%`,
  `version-X.Y.Z`, or “compliant” state merely to make the README look mature.

## Hero assets and screenshots

Use an asset when a reader gains information:
- UI screenshot for an application;
- architecture diagram for a non-obvious system boundary;
- terminal result that demonstrates a key workflow;
- benchmark chart with credible methodology;
- logo for identity.

For theme-sensitive assets use a `<picture>` element with light/dark sources
when needed. Always provide meaningful `alt` for informative images.

Keep repository-owned assets in a stable repository path and prefer relative
links.

Do not use a screenshot as the only place where instructions, status, or
configuration are communicated.

## Diagrams

A Mermaid or image diagram is justified when it communicates a stable mental
model faster than prose.

A diagram SHOULD:
- remain small enough to understand without zooming;
- use terms that match code/configuration;
- avoid embedding volatile counts/versions;
- have surrounding prose that states what the reader should learn from it.

Do not add architecture art merely to make a headless server look “modern”.

## Headings and scanning

Use:
- sentence case;
- descriptive nouns for conceptual sections;
- action-oriented headings for tasks;
- a logical H1 → H2 → H3 hierarchy;
- unique headings.

A reader scanning only headings should be able to locate installation,
verification, configuration, security, development, and support when those
topics exist.

GitHub already produces an outline from headings. A manual contents list is
therefore an exception, not the default.

## Paragraphs, lists, and tables

- Keep paragraphs focused and short.
- Put the important distinction in the first sentence.
- Use numbered lists for actual procedures.
- Use bullets for simple sets.
- Keep list grammar parallel.
- Use tables for records with several comparable properties.
- Move very wide or very long tables to reference docs.

Do not use HTML tables or alignment tricks as page layout.

## Code blocks

Code examples should:
- use the correct language fence;
- be copy-pasteable;
- contain the minimum context required to succeed;
- use obvious placeholder secrets;
- show one primary path before alternatives;
- avoid stale captured output unless output itself teaches something.

Use `<details>` for secondary platform/install variants only when it reduces
noise without hiding essential safety information.

## Callouts

GitHub callouts such as NOTE, TIP, IMPORTANT, WARNING, and CAUTION can improve
salience when used sparingly.

Use:
- IMPORTANT for a prerequisite or contract a user is likely to miss;
- WARNING/CAUTION for unsafe exposure, destructive behavior, or breaking
  compatibility;
- NOTE/TIP for optional acceleration.

Do not convert ordinary prose into a wall of callouts.

## Accessibility

- Provide useful alt text for informative images; omit decorative images where
  possible, or use empty alt text when they should be ignored by assistive
  technology.
- Do not encode meaning by color alone.
- Keep normal text left-aligned.
- Avoid flashing/flickering or gratuitous animation.
- Use descriptive link text instead of repeated “here”.
- Define uncommon acronyms.
- Preserve semantic headings.
- Avoid unnecessarily complex tables.

## Repository presentation companion

When public presentation is in scope, align the README opening with:
- GitHub repository description;
- repository topics;
- social preview image;
- package/registry description;
- documentation homepage.

A good social preview is branding metadata, not a replacement for a clear README
opening. Verify that it is legible when cropped and in light/dark contexts where
applicable.
