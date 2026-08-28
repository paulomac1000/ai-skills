---
afds_schema_version: 2
description: Normative rules for evidence-driven, drift-resistant, accessible repository README entrypoints.
doc_id: reference.readme-architect-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification:
  kind: command
  value: Run `python skills/readme-architect/tools/audit_readme.py README.md --profile <profile>` plus the repository-owned commands that verify the README's material claims.
---

# README architect standard

## Purpose

A repository README is the public entrypoint to a project. It lets a reader identify the project, decide whether it applies to them, reach first value safely, and find the next authoritative document without turning the README into a second database of implementation facts.

This standard owns README evidence selection, product-facing structure, presentation, drift resistance, and completion checks. `afds-doc-writer` remains the owner of general documentation governance, metadata, confinement, links, and lifecycle. Domain standards remain authoritative for the behavior they describe.

## Evidence and source ownership

Material README claims MUST be grounded before prose is written. A material claim includes runtime support, installation paths, executable names, transports, endpoints, authentication, capability risk, configuration defaults, compatibility, release artifacts, security posture, testing guarantees, and standards adoption.

For each material claim, identify the canonical owner, useful corroboration, verification method, volatility, README representation, and any unresolved conflict. The ledger MAY be temporary, but the reasoning MUST exist during authoring.

Prefer evidence in this order unless the repository defines a stronger owner for the specific fact:

1. explicit machine-readable public contract or runtime introspection;
2. executable implementation and configuration;
3. tests that assert externally observable behavior;
4. package, build, deployment, and release metadata;
5. maintained canonical documentation;
6. the existing README;
7. issue, pull-request, commit, or comment text.

This order does not make one file authoritative for every fact. Runtime support, for example, often requires package metadata plus CI and artifact evidence. A security claim requires enforcement code or tests; prose describing intent is insufficient.

README MUST summarize or link to facts already owned by schemas, registries, typed settings, manifests, workflows, or dedicated documentation. It MUST NOT become the sole canonical owner of a dynamic catalog, environment-variable inventory, version matrix, release state, security policy, or deployment topology already defined elsewhere.

When sources disagree, the author MUST surface the conflict instead of manufacturing certainty. Repair the canonical source when the task permits it; otherwise omit or qualify the disputed README claim.

## Opening and audience

README MUST contain exactly one semantic H1 and SHOULD make the following understandable before deep technical detail:

- what the project is;
- what problem or use case it serves;
- who or what environment it is for;
- the important differentiator, limitation, or safety boundary.

Use one or two short opening paragraphs. A small live badge row MAY follow the title when every badge answers a concrete user question. A visual MAY appear early when it improves recognition, demonstrates output, or proves a material differentiator.

For privileged services, automation, infrastructure, browser control, finance, device control, or similar high-impact projects, a critical safety or compatibility limitation MUST appear before a command that could otherwise be used unsafely.

Headings MUST form a logical hierarchy and SHOULD use sentence case with enough information scent that a reader scanning only the outline can predict where installation, security, configuration, development, and support information lives when those topics apply.

## Quick start and verification

A runnable user-facing project MUST provide a primary path to first value near the top unless no safe local path exists. In that case README MUST say so and route the reader to the supported path.

The primary path MUST:

- use a supported distribution or installation path;
- put only blocking prerequisites before the commands;
- include the configuration needed by that path;
- include a start or use command;
- end with an observable verification step such as a health endpoint, `--version`, deterministic demo, official-client connection, safe read operation, or artifact smoke.

Prefer the normal published artifact over a source build when the project ships one. Put source-build and secondary platform variants after the primary path or in linked documentation.

Commands MUST be syntactically valid for the identified shell or platform, MUST NOT contain real credentials, and MUST use unmistakable placeholders. Dangerous commands MUST be preceded by the required operator gate or warning.

A command presented as working MUST be reconciled with current repository evidence. Execute it when a clean or bounded environment is available. For credentialed or external integrations, a deterministic mock, dry-run, schema/introspection check, `--help`, package install check, or non-destructive health probe MAY provide bounded verification. Unexecuted examples MUST NOT be reported as observed successful results.

## Adaptive structure and progressive disclosure

There is no universal README section list. The author MUST choose the smallest applicable repository profile and preserve project-specific user value. `references/structure-profiles.md` provides profiles for MCP servers, other services, CLIs, libraries, applications, monorepos, and reference repositories.

README MUST remain a landing page rather than absorb every project document. Move exhaustive schemas, complete tool/API references, threat models, production runbooks, long architecture rationale, release procedures, migration histories, and large troubleshooting matrices to focused owners and link them at the point of need.

Use numbered lists for procedures, bullets for simple sets, and tables only when rows have several comparable properties. Large or wide catalogs SHOULD move to generated or focused reference documentation.

A manual table of contents SHOULD NOT be added by default because GitHub already generates an outline from headings. It MAY be retained or added for an unusually long README when it materially improves task navigation and its anchors are validated.

Public repositories SHOULD route to existing `CONTRIBUTING.md`, `SECURITY.md`, support/discussion channels, CHANGELOG/Releases, and license owners rather than copying those documents into README.

## Security and public contracts

A networked, privileged, or data-sensitive project README MUST explain the effective operational security posture a user needs to deploy or invoke it safely. Depending on the project this includes default bind scope, authentication, read/write/destructive gates, target or resource scoping, secret handling, identity or TLS verification, unsafe opt-ins, retry/reconciliation behavior, and audit expectations.

Security prose MUST match executable enforcement and negative-path tests. A public-bind acknowledgement, badge, lock file, or standards reference is not proof of authentication, authorization, confinement, or adoption.

README MAY summarize stable public interfaces, but the executable or machine-readable contract remains authoritative. Risk labels, transport names, endpoints, schemas, response semantics, and compatibility notices MUST use the vocabulary and behavior defined by the relevant domain owner.

Breaking or migration notices SHOULD appear near the top only while they materially affect likely users of the current release. Historical release detail belongs in the changelog, release notes, or migration documentation.

## Volatility and drift

Fast-changing values MUST be generated, represented by a live source, linked, or omitted rather than copied into prose when a better owner exists.

README MUST NOT hand-maintain test counts, coverage percentages, line counts, exact tool counts, moving dependency inventories, or similar measurements. Prefer a live CI badge over “build passing”, a package/release badge over a copied moving version, a coverage service over a copied percentage, runtime introspection over a hand-counted capability total, and CHANGELOG/Releases over permanent “What's new” history.

A hard-coded value MAY remain when it is itself a stable user contract and an enforced repository process keeps every required projection synchronized.

A change to a public or operational owner MUST trigger README impact assessment when it can alter installation, executable use, public CLI/API/MCP surface, ports, endpoints, transports, authentication, authorization, configuration, container execution, distribution, defaults, compatibility, security posture, or license. “Reviewed; no README change needed” is a valid outcome.

Do not create a maintenance rule that merely asks humans to synchronize several independent copies. Choose one owner, generate secondary representations where practical, link from README, and add a drift check only for the small stable subset that truly must stay visible.

## Visual presentation and accessibility

Presentation MUST serve comprehension before decoration. Badges MUST be live and truthful; a static “build passing”, guessed version/license, or guessed compliance badge is forbidden. Keep the opening badge set small, normally five or fewer, unless each additional badge supports a concrete user decision.

A logo, screenshot, terminal recording, benchmark, or diagram MAY be used when it improves identity, explains output, demonstrates workflow, or presents credible evidence. Decorative media MUST NOT delay the value proposition or quick start. Repository-owned assets SHOULD use stable relative paths; theme-sensitive assets SHOULD provide light/dark variants when needed.

Informative images MUST have meaningful alternative text. Decorative images SHOULD normally be omitted; if retained, empty alt text MAY mark them decorative. Status MUST NOT be communicated by color alone. Normal body text SHOULD remain left-aligned. Avoid flashing or gratuitous animation, repeated “click here” links, badge walls, centered prose, and decorative emoji on every heading.

Keep paragraphs focused and short, put the important distinction early, use parallel list grammar, and define uncommon acronyms on first meaningful use. Performance or superiority claims MUST link to reproducible or otherwise credible evidence.

When broader public presentation is in scope, also inspect repository description, topics, social preview, package/registry description, and documentation homepage so they use compatible terminology without creating new facts.

## MCP server profile

For an MCP server, `mcp-server-architect` remains the authority for capability semantics, safety classification, transports, identity, authorization, retry behavior, response contracts, lifecycle, and production acceptance. `readme-architect` owns how those verified facts are projected to readers.

An MCP README SHOULD describe capability groups and representative operations rather than clone a large registry. The authoritative catalog SHOULD be runtime `tools/list`, an application-owned governed registry, or a generated reference. Exact tool counts MUST NOT be hand-maintained.

The primary onboarding path SHOULD show the recommended transport and a representative client configuration when client setup is necessary for first value. Transport examples MUST match the currently supported domain contract; deprecated two-endpoint HTTP+SSE MUST NOT reappear through README examples when the server standard forbids it.

Read/write/destructive or richer multi-axis safety projections MUST match the server's application-owned policy. If writes are opt-in, destructive operations require exact approvals, HTTP is loopback-only, or production remote hosting is unsupported, those boundaries belong near the relevant start/connect instructions rather than only in deep architecture documentation.

Generated MCP project README templates are user-entrypoint seeds. They MUST satisfy this standard without becoming independent owners of MCP semantics; generator tests SHOULD detect drift from the canonical server standard.

## AFDS integration

`readme-architect` does not decide whether a rendered README carries AFDS frontmatter. The repository governance manifest and `afds-doc-writer` own that publication/profile decision.

A public README MAY be a conventional AFDS entrypoint without visible frontmatter while still passing one-H1, unique-heading, confined-link, anchor, bounded UTF-8, and regular-file checks. A governed README or sidecar MAY be used when the repository declares that pattern. README content and presentation still follow this standard where the skill is adopted.

Do not add YAML frontmatter merely for visual or process uniformity, and do not remove required metadata merely because another repository omits it. Resolve the adopting repository's explicit governance contract first.

## Change impact and completion

Before completion, record the chosen profile, evidence sources inspected, canonical conflicts, material claims that remain unverified, validation commands actually executed, quick-start/usage commands actually executed, introduced volatile projections, and downstream documentation impact.

Run `tools/collect_readme_evidence.py` before substantive authoring and `tools/audit_readme.py` after editing. The collector is discovery evidence, not a truth verdict. The auditor checks structural and drift-prone signals; it does not prove factual truth.

A README change is complete only when the selected AFDS structural profile passes, material claims are reconciled with their owners, the primary path is verified as far as the environment safely permits, domain-specific security/public-contract claims match their canonical standard and tests, links/assets resolve, audit errors are closed, warnings are reviewed, and unavailable verification is reported precisely.

A polished GitHub render, green badge, or generated template alone is not completion evidence.
