---
description: Architecture decisions for the CI/CD Architect standard — template engine, config contract, multi-language, security integration, workflow structure, PR feedback patterns
doc_id: decision.003-ci-cd-architect
type: decision
status: accepted
rigor_tier: L3
ttl_days: 0
version: 1.1.0
stability: stable
ai_scope: review_only
source_of_truth: true
tags: ["adr", "ci-cd", "github-actions", "standards", "architecture"]
upstream:
  - ref.ci-cd-standard
  - ref.mcp-server-standards
supersedes: null
superseded_by: null
last_verified: 2026-05-20
owners: ["backend-team"]
verification_status:
  - human_reviewed
doc_kind: atomic
glossary_terms: []
ttl_policy: permanent
---

# ADR: CI/CD Architect Standard — Architecture Decisions

> [!NOTE]
> Architecture Decision Record — immutable after acceptance. See `ref.ci-cd-standard` for the current CI/CD standard and `decision.002-mcp-standard-decisions` for MCP server standard decisions.

## CONTEXT

The CI/CD Architect standard (`ref.ci-cd-standard`) was designed to unify GitHub Actions workflows across multiple MCP server projects (`ha-mcp-readonly`, `mikrus-mcp`, `openwrt-mcp`, `tasmota-openbk-mcp`) that had independently evolved divergent CI/CD implementations. Some projects used different action versions, some combined lint+test into a single job, one had a hardcoded Docker version tag, and three of four were missing `auto-tag.yml`. The standard evolved through three design iterations from an MCP-only scope to a universal Python+Docker scope, and finally to a multi-language standard supporting .NET and polyglot projects with integrated security scanning and dependency management. This record documents the key architectural decisions made in shaping this standard.

## DECISION

### 1. Jinja2 Templates Instead of GitHub Matrix Strategy

**Problem:** Workflow file generation needed to produce structurally different YAML files depending on project archetype — MCP tool count smoke test vs generic health check, Docker smoke vs direct pytest smoke, Mosquitto service blocks for MQTT projects, multi-stage Dockerfile targets. GitHub's `matrix` strategy is designed for running the same job with different parameters, not for generating different job structures.

**Decision:** Use Jinja2 templates (`.j2` files) with conditional blocks (`{% if is_mcp %}...{% endif %}`, `{% if services %}...{% endif %}`). All substitution variables come from the project's configuration contract (`.github/ci-cd-config.yaml`). The template engine is not prescribed — Jinja2 via Python, `envsubst`, or manual `sed` substitution are all acceptable as long as the output matches.

**Rationale:** Matrix strategies cannot add or remove entire jobs or steps — they only vary a parameter value within a fixed structure. Jinja2 conditionals enable structural variation: the MCP tool-count smoke step exists only when `is_mcp: true`; the Mosquitto service block exists only when a `services:` entry is defined; the `docker-smoke` job becomes a lightweight `smoke` job when `use_docker: false`. A single template covers all archetypes without maintaining multiple near-identical files.

**Alternatives considered:**
- GitHub matrix with composite actions: rejected — composite actions cannot conditionally include/exclude steps based on inputs
- Per-archetype template files (MCP-ci.yml, nonMCP-ci.yml, dockerless-ci.yml): rejected — creates maintenance burden; changes must be replicated across all variants
- Generate workflow files in Python at project init time: rejected — adds a runtime dependency (Python) to a YAML-only configuration concern

### 2. Configuration Contract over Hardcoded Project Parameters

**Problem:** The early standard draft (pre-v1.0.0) hardcoded project parameters in a "Project Parameter Mapping" table listing all four MCP servers by name with their specific values. This was not reusable for new projects and required editing the standard itself every time a project was added.

**Decision:** Replace the hardcoded mapping with a machine-readable configuration contract. Each project defines `.github/ci-cd-config.yaml` (preferred) or `pyproject.toml [tool.ci-cd]` containing all substitution parameters: `src_dir`, `package`, `project`, `python_version`, `is_mcp`, `expected_tools`, `rest_port`, `health_port`, `use_docker`, `language`, `use_semgrep`, `use_dependabot`, `package_ecosystems`, `use_docs_validation`, and optional .NET parameters. Templates consume this contract. The standard itself contains no project-specific values.

**Rationale:** Separation of concerns: the standard defines HOW (workflow structure, action versions, quality gates); the config contract defines WHAT (project-specific values). Adding support for a new project requires only creating its `ci-cd-config.yaml` — the standard and templates remain unchanged. This is SSOT applied to CI/CD configuration.

**Alternatives considered:**
- Environment variables instead of YAML config file: rejected — GitHub Actions YAML can read YAML files directly; env vars require setting in repository settings, which is invisible in version control
- Per-project Jinja2 variable files (`.j2vars`): rejected — adds a second file format; YAML is already understood by GitHub Actions
- Continue with hardcoded table: rejected — fundamentally unscalable beyond 4 projects

### 3. Exactly Three Workflow Files

**Problem:** Projects were generating workflow sprawl — some had 2 files, some planned 5+. The standard needed a clear boundary for what constitutes a complete CI/CD pipeline vs what is project-specific automation.

**Decision:** Exactly three workflow files are mandated: `ci.yml`, `publish.yml`, `auto-tag.yml`. Additional CI concerns (Semgrep scanning, documentation validation) are separate workflow files that run independently, not additional jobs within the three core files. The core three form the pipeline backbone; auxiliary workflows (Semgrep, docs-validation) supplement without complicating the core.

Exception: Docker-less projects (`use_docker: false`) may omit `publish.yml`.

**Rationale:** Three files enforce a clear separation of concerns: CI (continuous integration — test every commit), CD (continuous delivery — publish on tag/merge), and Release (auto-tag). Adding more to these files creates bloated, hard-to-reason-about pipelines. Independent auxiliary workflows can fail without blocking the core pipeline, enabling security scanning to be a parallel concern rather than a blocking gate at the L1 level.

**Alternatives considered:**
- Single monolithic `ci.yml`: rejected — publish on tag vs publish on every commit require separate trigger logic; merging them creates fragile conditional evaluation
- Five+ files per project: rejected — increases cognitive load and template count without proportional benefit
- `semgrep.yml` as a job within `ci.yml`: rejected — Semgrep is a separate concern (security) that should run in parallel, not sequentially blocking tests

### 4. Integrated Security Scanning — Semgrep as L1+

**Problem:** Security scanning was absent from the early standard drafts. Each project was free to include or omit security tooling. Projects without scanning could merge secrets or OWASP Top Ten vulnerabilities without detection.

**Decision:** Semgrep security scanning is mandatory at L1+ with two workflow files: `semgrep.yml` (PR + push triggers, p/auto + p/secrets + p/owasp-top-ten rules) and `semgrep-scheduled.yml` (daily full scan). SARIF results are uploaded to GitHub Security tab. PR comments follow the marker-based pattern (see Decision 8). The Semgrep workflows run independently of the core CI pipeline — a Semgrep failure does not block unit tests from running.

**Rationale:** Security scanning is a baseline requirement for any project, not an advanced feature. Language-agnostic rules (p/auto, p/secrets, p/owasp-top-ten) work for Python, .NET, shell scripts, and configuration files without per-language configuration. Running Semgrep as an independent workflow prevents slow scans from blocking fast test feedback while still ensuring every PR is checked.

**Alternatives considered:**
- CodeQL instead of Semgrep: rejected — CodeQL requires per-language configuration; Semgrep works across 30+ languages with a single rule set
- Bandit-only (Python-specific): rejected — covers only Python, misses secrets in config files and shell scripts
- Make Semgrep a job within ci.yml: rejected — security scanning should run in parallel, not sequentially after tests; a slow scan delays test feedback

### 5. Integrated Dependency Management — Dependabot as L1+

**Problem:** Dependency update automation was inconsistent across projects. Some had no automation, others had partial Dependabot configs. Without automation, security patches in dependencies could go unapplied for weeks.

**Decision:** `.github/dependabot.yml` is mandatory at L1+. The `github-actions` ecosystem is always present (weekly interval, grouped updates). Additional ecosystems (`pip`, `nuget`, `docker`, `gomod`, `npm`) are declared in the configuration contract's `package_ecosystems` field. All ecosystems use `groups:` with `patterns: ["*"]` to batch updates into single PRs.

**Rationale:** Automated dependency updates reduce the maintenance burden from N individual PRs per week to 1-2 grouped PRs. GitHub Actions themselves are dependencies that need updating — the `github-actions` ecosystem ensures workflow action versions stay current. Grouping eliminates the noise problem that caused many teams to disable Dependabot in earlier GitHub iterations.

**Alternatives considered:**
- Renovate instead of Dependabot: rejected — Dependabot is native to GitHub, requires no additional app installation, and has identical capability for the ecosystems we use
- Weekly vs daily interval: weekly chosen to reduce PR noise while still applying security patches within 7 days
- No groups (individual PRs): rejected — N individual PRs per week for a project with pip + github-actions creates unacceptable notification fatigue

### 6. Multi-Language Support — Python Primary, .NET Variant

**Problem:** The standard was initially Python-only. The discovery of `.NET` CI pipelines in the `cortexa` and `hand-codec` projects showed that many CI patterns (restore, build, test, pack, publish) are universal but the tooling differs. A separate standard for each language would duplicate the shared patterns (Semgrep, Dependabot, docs validation, concurrency, PR feedback).

**Decision:** Python is the primary language (most projects in scope are Python). .NET is supported as a variant through `language: dotnet` in the config contract, which switches the CI template from `ci.yml.j2` to `dotnet-ci.yml.j2`. Shared workflows (Semgrep, Dependabot, docs-validation, auto-tag) are language-agnostic and apply to all languages. The `language: polyglot` option supports projects using both Python and .NET, generating both CI templates.

**Rationale:** Shared infrastructure (Semgrep, Dependabot, concurrency, PR comments) is language-agnostic and should not be duplicated. Language-specific differences (Python: ruff+mypy+bandit+pytest; .NET: dotnet format+dotnet build+dotnet test+ReportGenerator) justify separate CI templates. The config contract's `language` field is a clean dispatch mechanism.

**Alternatives considered:**
- One CI template with per-language conditionals: rejected — the Python and .NET pipelines share almost no steps; conditionals would make the template unreadable
- Separate standard for each language: rejected — duplicates 5 of 9 templates and all shared rules
- Make .NET the primary, Python a variant: rejected — 4 of 4 MCP servers are Python

### 7. Concurrency and Node Compatibility on Every Workflow

**Problem:** Rapid pushes to a branch would queue multiple CI runs. JavaScript-based GitHub Actions would fail intermittently because the runner's built-in Node version lagged behind what actions required.

**Decision:** Two rules applied uniformly to every workflow file:

1. `concurrency:` block with `cancel-in-progress: true` — the group key includes the workflow name and Git ref, ensuring only the latest push runs to completion. PR-specific workflows use the PR number as the concurrency group.

2. `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` — forces the runner to use Node 24 for JavaScript-based actions (`actions/github-script`, `tj-actions/*`, `dorny/*`, `marocchino/*`). Applied at the workflow level rather than per-job to ensure consistency.

**Rationale:** Concurrency prevents wasteful CI minutes (observed in the cortexa project where rapid saves on a branch would queue 5+ redundant runs). Node compatibility prevents the most common source of GitHub Actions runtime failures — version mismatches between the runner's built-in Node and what an action expects. Applying at workflow level rather than per-job reduces ceremony and prevents accidental omission.

**Alternatives considered:**
- Concurrency only on publish workflows: rejected — CI on rapid pushes also wastes minutes; a failed lint step from an outdated push is worse than no CI at all
- `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` only on jobs using JS actions: rejected — future action additions could be missed; workflow-level is safer and costs nothing
- Using `actions/setup-node` to pin Node version: rejected — adds a build step and ~30s to every CI run; the env var achieves the same result with zero overhead

### 8. Marker-Based PR Comment Pattern

**Problem:** CI bots posting PR comments would create duplicates on every CI run. A bot posting "Ruff check failed" on push 1 would post an identical "Ruff check failed" on push 2, accumulating stale failure comments that were later resolved but still visible.

**Decision:** Every CI bot that posts PR comments MUST use a hidden HTML marker (`<!-- bot-name -->`) as the first line of the comment body. Before posting, the bot searches for an existing comment with the same marker (by the `github-actions[bot]` user) and updates it. If the check passes on a subsequent run, the failure comment is updated to indicate success rather than being orphaned. This pattern is documented as Canonical Implementation in `ci-cd-standard.md` Rule 21.

**Rationale:** The marker pattern provides a lightweight idempotency mechanism without requiring a database or external state. The hidden HTML comment is invisible in the rendered UI but searchable via the GitHub API. Updating instead of deleting preserves the comment history while keeping only one status message visible at a time.

**Alternatives considered:**
- Always create new comments: rejected — creates comment spam; a project with 4 bot checks and 10 pushes per PR accumulates 40+ comments
- Delete old comments, create new: rejected — loses comment history; if a bot comment contains error details, it should remain accessible
- Use GitHub Checks API instead of comments: rejected — Checks API requires a GitHub App, which is heavier infrastructure; comments work with the standard `GITHUB_TOKEN`

### 9. MCP vs Non-MCP Smoke Test Variants

**Problem:** MCP servers have a specific smoke test requirement: verify exact tool count (e.g., 122 tools for ha-mcp-readonly) and REST API tools endpoint returns the expected total. Non-MCP projects need a simpler health check. Forcing MCP tool-count semantics on non-MCP projects creates false failures.

**Decision:** The `is_mcp` field in the configuration contract gates MCP-specific smoke test steps. When `is_mcp: true`, the docker-smoke job includes: (a) an import-time tool count assertion via `from server import get_tool_count`, and (b) a REST API health + tools endpoint verification with exact tool count match. When `is_mcp: false`, only the generic health endpoint check runs. When `use_docker: false`, the docker-smoke job is replaced entirely by a `smoke` job running `pytest tests/smoke/`.

**Rationale:** The MCP tool count check is an integration-level assertion that verifies the server registered all expected tools — a critical safety check for MCP servers where a missing tool means an AI agent cannot perform an action. For non-MCP services, a health check suffices. The `is_mcp` flag keeps the template clean without per-project overrides.

**Alternatives considered:**
- Always run tool count check, make it a SHOULD: rejected — non-MCP projects have no `get_tool_count` function; the step would fail or require a mock
- Separate Dockerfile for smoke testing with tool count built in: rejected — violates "build once" principle (Decision 3 rationale)
- Hardcode per-project smoke test logic: rejected — exactly the problem the config contract solves

### 10. Source Layout Variants — Three Patterns

**Problem:** Python projects in the ecosystem use different source directory layouts. MCP projects use `tools/` (ha-mcp-readonly, tasmota-openbk-mcp) or `src/<package>/` (mikrus-mcp, openwrt-mcp). A single hardcoded path in CI templates would fail for half the projects.

**Decision:** Define three source layout variants driven by the `src_dir` config field:

| Variant | `src_dir` value | Mypy/Bandit path | `--cov` |
|---------|----------------|------------------|---------|
| A: Standard `src/` | `src/<package>/` | `src/<package>/` | `<package>` |
| B: Flat `tools/` | `tools/` | `tools/` | `tools` or `.` |
| C: Nested | `src/<package>/tools/` | `src/<package>/` | `<package>` |

The `src_dir` field drives three substitutions: `mypy <SRC_DIR>/ --strict`, `bandit -r <SRC_DIR>/ -ll`, and `--cov=<PACKAGE>`. Ruff always runs on the entire repository (`.`).

**Rationale:** Mypy and bandit need the source root; ruff can scan everything. The three variants cover every observed layout without requiring `find` or glob magic in CI. The config contract makes the layout explicit and machine-checkable.

**Alternatives considered:**
- Enforce a single layout: rejected — legacy projects cannot be restructured without breaking imports; the standard must accommodate existing projects
- Auto-detect layout in CI: rejected — fragile; CI should be deterministic, not dependent on runtime directory structure heuristics
- Use `find` or glob patterns for all tools: rejected — `find` output ordering is non-deterministic and platform-dependent; explicit paths are reproducible

## ALTERNATIVES_CONSIDERED

The alternative considered for each sub-decision is documented within the category above. Across all categories, the consistent rejection patterns were:

- **Over-coupling (merging everything into CI):** Rejected when separation of concerns improves maintainability — Semgrep as independent workflow, PR comments as a pattern rather than CI step
- **Under-standardization (per-project freedom):** Rejected when inconsistency created maintenance burden — action versions, job structure, concurrency, dependabot config
- **Tool-specific lock-in:** Rejected when a binding to one tool limited applicability — Jinja2 as suggestion not requirement, Dependabot over Renovate for simpler GitHub-native integration
- **One-size-fits-all:** Rejected when projects genuinely differ — MCP vs non-MCP smoke tests, Docker vs Dockerless, Python vs .NET

## CONSEQUENCES

**Positive:**
- Four MCP server projects unified under identical workflow structure, action versions, and quality gates
- Configuration contract enables adding new projects without editing the standard
- Jinja2 templates cover 4 archetypes (Python+MCP+Docker, Python+non-MCP+Docker, Python+Dockerless, .NET+NuGet) from a single template per workflow
- Semgrep + Dependabot provide security and maintenance automation that was absent before
- Concurrency eliminates redundant CI runs; Node compatibility prevents intermittent failures
- Marker-based PR comments eliminate bot comment spam
- Source layout variants accommodate existing project structures without forced migration

**Negative:**
- Template generation adds an abstraction layer — developers must understand the config contract to modify CI behavior
- Jinja2 templates require a processing step (manual or automated); not directly usable as GitHub workflow files
- .NET variant is validated only against the two projects in `/var/apps/data/` (cortexa, hand-codec), not a diverse .NET ecosystem
- `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` assumes Node 24 is available on all GitHub runners; if GitHub deprecates Node 24, this becomes a hard failure requiring standard update

**Risks:**
- Python 3.14 is a pre-release; using `check-latest: true` may be needed once 3.14 stabilizes
- Semgrep `p/auto` rule set may produce false positives that require baseline exemptions
- Dependabot grouped PRs may become too large if many packages update simultaneously
- Multi-arch Docker builds (`linux/amd64,linux/arm64`) add ~3 minutes to publish time

**Mitigations:**
- Python version is configurable per project in the config contract; a standard update can bump the default
- Semgrep scheduled scans run nightly; PR scans catch only new issues in changed code (diff-aware)
- Dependabot `groups:` with `patterns: ["*"]` produces one PR per ecosystem per week, manageable by design
- Multi-arch builds use GitHub Actions cache (`type=gha`) to minimize rebuild time

## STATUS

- `proposed: 2026-05-20` — Consolidated from three design iterations (MCP-only → Python+Docker → Multi-language) and deployment across 4 production MCP servers
- `accepted: 2026-05-20` — Approved after full deployment to openwrt-mcp, ha-mcp-readonly, tasmota-openbk-mcp, and mikrus-mcp

## CHANGELOG

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-05-20 | Initial ADR documenting all architecture decisions for the CI/CD Architect standard | opencode |
| 1.1.0 | 2026-05-20 | Post-deployment fixes: pull_request trigger base-branch behavior, Codecov secrets gating, mypy dependencies, Python 3.14 asyncio compat, exempt_files validator bugfix, banned word /etc handling, .NET auto-tag variant, duplicate tag guard, REST API format standardization, MCP standard upstream ref | opencode |
