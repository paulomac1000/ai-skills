---
name: readme-architect
description: >
  Create, repair, audit, or materially update a repository README.md from
  repository evidence. Use for public project landing pages, especially MCP
  servers, services, CLIs, libraries, and containerized applications. Enforces
  source-of-truth discipline, executable quick starts, security-aware server
  documentation, drift resistance, and professional GitHub presentation.
---

# README architect

Create a README that is a trustworthy repository landing page, not a second
database of project facts.

Read `STANDARD.md` before making substantive README decisions. Use the
references only when their subject applies.

## Required workflow

1. **Classify the repository before writing**
   - Choose the closest profile: `mcp-server`, `server`, `cli`, `library`,
     `application`, `monorepo`, or `reference`.
   - Identify the primary audience and the shortest supported success path.
   - Identify whether the README is primarily for users, operators,
     integrators, contributors, or a combination of them.
   - Do not infer the profile from the repository name alone.

2. **Collect evidence before editing prose**
   - Run `tools/collect_readme_evidence.py <repo>`.
   - Inspect the sources listed in `references/evidence-source-map.md`.
   - Build a temporary claim ledger for every material fact that may enter the
     README: claim, canonical source, corroborating source, verification method,
     volatility, and unresolved conflict.
   - Treat the existing README as a discovery clue, not as authority.

3. **Resolve contradictions**
   - Prefer executable/public-contract evidence over prose.
   - Verify supported runtime ranges against package metadata, CI, and
     container/runtime configuration rather than copying one isolated value.
   - Verify security claims against enforcement code and tests.
   - If authoritative sources disagree, do not silently choose one. Repair the
     source conflict if the task allows it; otherwise report the conflict and
     avoid a false README claim.

4. **Design the opening region**
   - Use one meaningful H1.
   - Add only live, useful badges that communicate current state or a direct
     user action.
   - State what the project is, who it is for, and its distinguishing value in
     one or two short paragraphs.
   - Put a safety or compatibility callout before the happy path when a user
     could otherwise operate the project unsafely or misunderstand a breaking
     change.
   - Make the primary path to first success obvious without requiring a reader
     to understand the architecture first.

5. **Write the shortest verified happy path**
   - Prefer the supported distribution artifact over a source build when the
     project has one.
   - Include only blocking prerequisites before the quick start.
   - Show copy-pasteable commands.
   - End the path with an observable verification step: health endpoint,
     `--version`, deterministic demo, smoke command, client connection, or
     equivalent.
   - For MCP servers, include the recommended transport/client configuration
     when that is necessary to obtain first value.

6. **Add only sections justified by the repository**
   - Follow `references/structure-profiles.md`.
   - Summarize dynamic catalogs; link to their canonical owner or generated
     reference rather than cloning them into README.
   - Put deep architecture, exhaustive API/tool schemas, operational runbooks,
     migration history, and long troubleshooting material in dedicated docs.
   - Link to those documents from the point where a reader needs them.

7. **Apply presentation rules**
   - Follow `references/visual-presentation.md`.
   - Optimize for scanning: descriptive sentence-case headings, short
     paragraphs, parallel lists, compact tables, and focused code blocks.
   - Use visual assets only when they improve recognition or understanding.
   - Preserve accessibility and light/dark rendering.

8. **Perform factual verification**
   - Execute safe quick-start and verification commands when the environment
     permits.
   - Run repository-owned tests or focused checks that substantiate security,
     transport, configuration, or public-contract claims.
   - Do not convert an unexecuted example into a statement that it works.
   - For credentialed/external integrations, use the project's deterministic
     mock, dry-run, `--help`, schema/introspection endpoint, or other bounded
     verification path when available.

9. **Perform deterministic README audit**
   - Run:
     `python tools/audit_readme.py README.md --profile <profile>`
   - Fix errors.
   - Review warnings rather than blindly suppressing them.
   - Verify rendering in GitHub-flavored Markdown when practical.

10. **Report completion**
    - State the repository profile used.
    - State which commands/checks were actually executed.
    - List material claims that could not be verified.
    - List any canonical-source conflicts discovered.
    - State whether the change introduces new manually maintained volatile
      facts.
    - Identify deeper docs that should also be reviewed.

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
- Do not use a static “build passing” badge or hard-coded green status.
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

## Conditional references

Read these only when needed:

- `references/evidence-source-map.md` — where each class of README fact should
  come from and how to verify it.
- `references/structure-profiles.md` — adaptive section ordering for MCP
  servers, other services, CLIs, libraries, apps, monorepos, and reference
  repositories.
- `references/visual-presentation.md` — badges, hero assets, screenshots,
  diagrams, headings, tables, callouts, accessibility, and repository social
  presentation.
- `references/drift-and-change-impact.md` — volatility rules and source changes
  that should trigger README review.

## Relationship to other ai-skills

- Use `afds-doc-writer` for the general evidence-before-prose, canonical-owner,
  verification, and documentation-impact discipline. This skill specializes
  those principles for the public repository landing page.
- When the target is an MCP server, use `mcp-server-architect` as the higher
  domain authority for MCP contracts, capability/risk semantics, transports,
  authorization, and security posture.
- When CI/release behavior itself must be changed rather than merely described,
  use `ci-cd-architect`.
- Do not duplicate those skills' normative domain rules inside README prose.

The README is a projection of repository truth. Fix the projection when it is
wrong; fix the source when the source is wrong; never make two competing truths.
