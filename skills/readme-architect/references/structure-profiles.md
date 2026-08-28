---
afds_schema_version: 2
description: Adaptive README section-order profiles for MCP servers, services, CLIs, libraries, applications, monorepos, and reference repositories.
doc_id: reference.readme-structure-profiles
type: reference
status: active
rigor: informative
owners: [repository-maintainers]
---

# README structure profiles

These are routing profiles, not mandatory templates. Omit irrelevant sections,
merge adjacent sections when that improves flow, and link deep material.

## Common opening

Recommended order:

1. H1 project name.
2. Small live badge row, if useful.
3. One- or two-paragraph value proposition.
4. Optional visual/proof asset.
5. Optional critical safety/compatibility callout.
6. Optional 3–6 highlights when the differentiators are not already obvious.
7. Quick start / installation.

Do not put architecture, project tree, long prerequisites, changelog history, or
an exhaustive catalog before first value.

## MCP server profile

Use when MCP is a primary public interface.

Recommended flow:

1. **Identity and value proposition**
   - what external system/data the server exposes;
   - whether it is read-only, write-capable, or policy-gated;
   - default/recommended transport.

2. **Quick start**
   - normal installation artifact;
   - minimal required secret/config;
   - start server;
   - connect a representative MCP client;
   - verify with client introspection or one harmless tool.

3. **Capabilities**
   - capability groups and representative tools;
   - risk vocabulary;
   - link to runtime/generated authoritative catalog.

4. **Security model**
   - default exposure and auth;
   - mutation/destructive gates;
   - target/resource identity if applicable;
   - important unsafe opt-ins;
   - credential handling.

5. **Transports/endpoints**
   - only when multiple modes or HTTP health endpoints matter.

6. **Configuration**
   - onboarding-critical variables inline;
   - full reference linked.

7. **Development/testing**
   - canonical dev checks from CI/project config.

8. **Architecture / contract**
   - short runtime mental model;
   - link deep architecture/tool-contract docs.

9. **Compatibility/migration**
   - conditional.

10. **Contributing / security reporting / license**

For large MCP catalogs, do not reproduce dozens of schema rows merely because
they fit in Markdown. A grouped summary plus canonical generated catalog is
more trustworthy.

## General server/service profile

Recommended flow:

1. identity/value proposition;
2. requirements that truly block startup;
3. quick start;
4. verify/health;
5. endpoints or supported interfaces;
6. security and exposure;
7. configuration;
8. deployment/container path;
9. development;
10. architecture/operations links;
11. contributing/security/license.

If the service can alter infrastructure or user data, move security before
configuration/deployment.

## CLI profile

Recommended flow:

1. identity/value proposition;
2. install;
3. 30–60 second example with representative output;
4. common workflows;
5. configuration;
6. command reference link / `--help`;
7. shell completion or platform notes when relevant;
8. development/contributing/license.

Do not paste the entire generated `--help` output into README if the CLI itself
is authoritative.

## Library/SDK profile

Recommended flow:

1. identity/value proposition;
2. install;
3. minimal code example that runs;
4. key capabilities;
5. compatibility/runtime support;
6. API/reference docs link;
7. design guarantees or limitations;
8. development/contributing/license.

Prefer one strong example over a large artificial “tech stack” section.

## Application profile

Recommended flow:

1. identity/value proposition;
2. screenshot/demo only if it materially explains the product;
3. quick start;
4. core workflows/features;
5. configuration;
6. deployment;
7. architecture/development;
8. contributing/license.

For a user-facing UI, visuals carry more value than for a headless server.

## Monorepo profile

Recommended flow:

1. purpose and repository scope;
2. supported packages/services map;
3. quick path for the most common user;
4. package/service table with links;
5. shared development commands;
6. architecture/release policy links;
7. contributing/license.

Each subproject that has materially different onboarding SHOULD own focused
documentation rather than forcing the root README to become all subproject
READMEs at once.

## Reference/example repository profile

Recommended flow:

1. state clearly that the repository is reference/example material;
2. explain what it demonstrates and what it intentionally does not guarantee;
3. quick example;
4. map examples/modules;
5. explicit production-readiness warning where relevant;
6. contributing/license.

Do not let example code imply production security.

## Sections that are usually conditional

Add only with evidence of reader need:
- benchmark/performance;
- screenshots/demo gallery;
- FAQ;
- troubleshooting;
- project structure tree;
- acknowledgements;
- sponsors;
- citation;
- roadmap;
- migration;
- manual table of contents.

A README that includes every possible section is usually less useful than one
that routes each audience quickly.
