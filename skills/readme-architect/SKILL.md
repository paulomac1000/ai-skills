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

Read `STANDARD.md` before making substantive README decisions. The detailed
operating procedure lives in `references/authoring-workflow.md`; the references
below apply only when their subject applies.

## Required workflow

1. **Classify the repository** - pick the closest profile (`mcp-server`,
   `server`, `cli`, `library`, `application`, `monorepo`, `reference`),
   identify the primary audience and shortest supported success path, and do
   not infer the profile from the repository name alone.
2. **Collect evidence** - run `tools/collect_readme_evidence.py <repo>`,
   inspect `references/evidence-source-map.md`, and build a claim ledger
   (claim, canonical source, verification, volatility). Treat the existing
   README as a discovery clue, not authority.
3. **Resolve contradictions** - prefer executable and public-contract evidence
   over prose; when authoritative sources disagree, repair the conflict or
   report it and never silently pick one.
4. **Design the opening region** - one meaningful H1, only live useful badges,
   a short statement of what/for-whom/value, and a safety or compatibility
   callout before the happy path when a user could otherwise act unsafely.
5. **Write the shortest verified happy path** - prefer the supported artifact
   over a source build, include only blocking prerequisites, use
   copy-pasteable commands, and end with an observable verification step.
6. **Add only justified sections** - follow `references/structure-profiles.md`;
   link to canonical owners instead of cloning dynamic catalogs into README.
7. **Apply presentation rules** - follow `references/visual-presentation.md`;
   optimize for scanning, accessibility, and light/dark rendering.
8. **Verify facts** - execute safe quick-start and verification commands when
   the environment permits; never promote an unexecuted example into a claim
   that it works.
9. **Audit deterministically** - run
   `python tools/audit_readme.py README.md --profile <profile>`; fix errors and
   review warnings rather than suppressing them.
10. **Report completion** - state the profile used, the commands actually
    executed, unverified material claims, canonical-source conflicts, and any
    new manually maintained volatile facts.

The full evidence preference order, non-negotiable constraints, and completion
checklist are normative and live in `references/authoring-workflow.md`.

## Conditional references

- `references/evidence-source-map.md` - where each class of README fact comes
  from and how to verify it.
- `references/structure-profiles.md` - adaptive section ordering per profile.
- `references/visual-presentation.md` - badges, assets, diagrams, headings,
  tables, callouts, accessibility, and social presentation.
- `references/drift-and-change-impact.md` - volatility rules and source changes
  that should trigger README review.

## Relationship to other ai-skills

- Use `afds-doc-writer` for general evidence-before-prose, canonical-owner, and
  documentation-impact discipline; this skill specializes them for the public
  repository landing page.
- For MCP servers, `mcp-server-architect` is the higher domain authority for
  MCP contracts, transports, authorization, and security posture.
- Use `ci-cd-architect` when CI/release behavior itself must change rather than
  merely be described. Do not duplicate those skills' rules in README prose.

The README is a projection of repository truth. Fix the projection when it is
wrong; fix the source when the source is wrong; never make two competing truths.
