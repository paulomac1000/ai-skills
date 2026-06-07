---
description: Architecture decisions for the Pre-commit Hook Architect standard — skill design, template strategy, CI mirroring dependency, fail-fast policy
doc_id: decision.007-precommit-architect
type: decision
status: accepted
rigor_tier: L3
ttl_days: 0
version: 1.0.0
stability: stable
ai_scope: review_only
source_of_truth: true
tags: ["adr", "pre-commit", "standards", "architecture", "ci-cd"]
upstream:
  - ref.ci-cd-standard
supersedes: null
superseded_by: null
last_verified: 2026-06-07
owners: ["backend-team"]
verification_status:
  - human_reviewed
doc_kind: atomic
glossary_terms: []
ttl_policy: permanent
---

# ADR: Pre-commit Hook Architect — Architecture Decisions

> [!NOTE]
> Architecture Decision Record — immutable after acceptance. See `ref.ci-cd-standard` for CI/CD standard and `decision.003-ci-cd-architect` for CI/CD architecture decisions. See `todo-precommit.md` for the pre-commit skill design and implementation plan.

## CONTEXT

The CI/CD Architect standard (`ref.ci-cd-standard`) covers server-side CI — GitHub Actions workflows that run on push and PR. However, pre-commit hooks operate at a different boundary: the developer's machine, before code reaches version control. A dedicated skill was needed because:

- **Different timing**: Pre-commit runs at `git commit`, not on push/PR
- **Different constraints**: Must be fast (<30s total), must not require network, must work offline
- **Different failure modes**: `ruff format` bugs (target-version mismatch, except syntax), stale caches, language version conflicts
- **Different configuration patterns**: `local` vs `remote` repos, `system` vs `unsupported` language, `files` filtering, stage selection
- **CI mirroring requirement**: Pre-commit MUST run the same checks as CI — same tools, same config, same ordering

The gap was confirmed after deploying pre-commit to `ha-mcp-readonly` and `local-home-devices-mcp` projects, where 10 distinct pitfalls were discovered (documented in `todo-precommit.md`). These included environment mismatches between pre-commit (full local env) and CI (minimal env), `ruff target-version` compatibility bugs, and CAFDS scanning `.omo/` planning documents that lack YAML frontmatter.

## DECISION

### 1. New Pre-commit Hook Architect Skill with 13 PRECOMMIT Rules

**Problem:** No authoritative standard existed for pre-commit hook configuration across the ecosystem. Each project independently chose hooks, versions, ordering, and error handling. The CI/CD Architect skill could not be extended to cover pre-commit because the domains differ fundamentally in timing, constraints, and failure modes (server-side CI vs local developer machine).

**Decision:** Create a dedicated `skills/pre-commit-architect/` skill with an authoritative `precommit-standard.md` containing 13 semantic-anchored rules ([PRECOMMIT-01] through [PRECOMMIT-13]). The rules are organized by enforcement level:

| Rule ID | Level | Summary |
|---------|-------|---------|
| PRECOMMIT-01 | L1+ | Pre-commit MUST mirror CI lint+test checks in the same order |
| PRECOMMIT-02 | L1+ | Hook ordering: generic → lint → format → types → security → docs → tests |
| PRECOMMIT-03 | L1+ | `ruff target-version` MUST match `requires-python`, not CI runner version |
| PRECOMMIT-04 | L1+ | NEVER use `\|\| true` or `--ignore` to mask errors |
| PRECOMMIT-05 | L1+ | Use `python3` not `python` in all entry commands |
| PRECOMMIT-06 | L1+ | ALL hooks use `fail_fast: false` |
| PRECOMMIT-07 | L2+ | Heavy tests go to `pre-push`, not `pre-commit` |
| PRECOMMIT-08 | L2+ | Total runtime MUST be under 30 seconds |
| PRECOMMIT-09 | L2+ | Remote hooks use commit SHA, not version tags |
| PRECOMMIT-10 | L1+ | `.pre-commit-config.yaml` committed to repo |
| PRECOMMIT-11 | L1+ | `[[tool.mypy.overrides]]` MUST list every third-party dep |
| PRECOMMIT-12 | L1+ | CAFDS `excluded_dirs` MUST match pre-commit doc hook excludes |
| PRECOMMIT-13 | L2+ | Pre-commit MUST NOT silently pass on test collection errors |

**Rationale:** The 13 rules codify all known failure modes discovered during deployment. A dedicated skill with its own standard prevents scope creep in the CI/CD Architect skill while maintaining cross-referencing via `upstream: ref.ci-cd-standard`. The L1+/L2+ tier system mirrors the CI/CD standard convention: L1+ is mandatory for all projects, L2+ applies to projects with integration tests or heavy checks.

**Alternatives considered:**
- Extend CI/CD Architect skill to include pre-commit: rejected — would violate single-responsibility; CI/CD (server-side, push/PR-triggered) and pre-commit (client-side, commit-triggered) have distinct constraints, failure modes, and configuration patterns
- Document pre-commit as a reference document without a skill: rejected — a skill persona is needed to enforce the rules during coding sessions; a static reference would be read but not reliably followed
- Include pre-commit rules in MCP Server Architect skill: rejected — pre-commit applies to all Python projects, not just MCP servers

### 2. Three Templates Instead of One Monolithic Template

**Problem:** A single `.pre-commit-config.yaml` template would need to cover three distinct project types: generic Python projects, MCP servers (with tool-count smoke tests), and minimal/fast-only projects. Conditionals would make a single template unreadable and hard to maintain, mirroring the same problem the CI/CD Architect team faced with GitHub matrix strategies vs Jinja2 conditionals.

**Decision:** Provide three template variants:

| Template | Project Type | Key Hooks |
|----------|-------------|-----------|
| `pre-commit-python.j2` | Generic Python | ruff, mypy, bandit, pytest, yaml/json validation, end-of-file fixer |
| `pre-commit-mcp.j2` | MCP servers | All Python hooks + tool-count assertion, REST API health check, semgrep |
| `pre-commit-minimal.j2` | Fast bootstrap | ruff format + ruff check only (no types, no security, no tests) |

Each template is a complete `.pre-commit-config.yaml` with `fail_fast: false`, pinned hook revisions (commit SHA for remote hooks), and the correct hook ordering per PRECOMMIT-02.

**Rationale:** Three templates cover three project archetypes with zero conditional complexity. A developer picks the template closest to their project type and customizes from there. This mirrors the CI/CD Architect's strategy of separate templates per language/language variant rather than one template with conditionals.

**Alternatives considered:**
- Single template with Jinja2 conditionals: rejected — the same rationale as CI/CD Decision 1 applies: conditionals make templates unreadable when the variants are structurally different (MCP specific hooks, minimal vs full test suite)
- Two templates (Python + minimal): rejected — the MCP variant has distinct hooks (tool-count, health-check, semgrep) that don't fit in the generic Python template
- Per-project manual configuration without templates: rejected — defeats the purpose of a standard; templates ensure consistent hook ordering, versions, and fail_fast policy

### 3. Upstream Dependency: `ref.ci-cd-standard`

**Problem:** Pre-commit hooks run locally; CI runs on GitHub Actions. Without an explicit dependency link between the two standards, developers might configure pre-commit checks that differ from CI checks, creating a "passes locally, fails in CI" scenario that erodes trust in both systems.

**Decision:** The Pre-commit standard MUST declare `upstream: ref.ci-cd-standard` in its frontmatter and enforce PRECOMMIT-01: pre-commit checks MUST mirror CI lint+test jobs in the same order. The standard's first rule (PRECOMMIT-01) makes this dependency explicit and non-negotiable. The SKILL.md persona includes instructions to cross-reference the CI/CD standard when generating pre-commit configurations.

The declaration ensures:
- AFDS validation can detect orphaned pre-commit skills that aren't paired with a CI/CD standard
- AI agents are prompted to load both skills when generating pre-commit configs
- Auditors can verify pre-commit vs CI alignment as a single check

**Rationale:** Explicit upstream dependency prevents the most common integration failure: locally passing pre-commit checks that fail in CI. The `upstream` frontmatter field makes the dependency machine-checkable (AFDS validator can verify the referenced standard exists). This follows the same pattern as MCP Server Architect declaring `upstream: ref.mcp-consumer-standards` or `ref.ci-cd-standard`.

**Alternatives considered:**
- No upstream declaration: rejected — siloed standards inevitably diverge; the upstream link forces the agent to consider both domains
- Declare the CI/CD Architect skill as the upstream, not the standard: rejected — skills are personas; standards are the authoritative rules. The skill references the standard, not vice versa
- Hardcode CI commands in the pre-commit standard: rejected — duplication; the CI/CD standard owns the CI specification; pre-commit references it

### 4. `fail_fast: false` as Global Default

**Problem:** Pre-commit's default behavior (`fail_fast: true` per hook, no global default) stops at the first hook failure. This means a developer sees only one error per commit cycle — fix it, commit again, hit the next error. For a configuration with 10 hooks, this can require 10 commit cycles to fix a single batch of issues.

**Decision:** Set `fail_fast: false` as the global default in `.pre-commit-config.yaml` and on every individual hook. This ensures all hooks run to completion on every commit, reporting every error at once. The developer sees the full picture in a single commit attempt.

```yaml
# .pre-commit-config.yaml — global default
fail_fast: false  # ALL hooks collect errors before failing
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: "v0.11.0"
    hooks:
      - id: ruff
        fail_fast: false  # explicit per-hook, matches global
```

**Rationale:** Developer experience: collecting all errors in one commit attempt is strictly better than discovering them one by one. The cost is minimal (a few extra seconds per commit), and the benefit is significant — no "commit → fail → fix → recommit → fail" cycles. This is enforced as PRECOMMIT-06.

**Alternatives considered:**
- `fail_fast: true` (pre-commit default): rejected — creates the N-commit cycle described above; tolerable for CI (where each run is automated) but unacceptable for developer workflow
- No global default, let each hook decide: rejected — leads to inconsistent behavior; some hooks would be fast-fail, others would collect, and developers would be confused about which pattern applies
- `fail_fast: false` at global level, allow per-hook overrides: rejected — PRECOMMIT-04 already forbids `--ignore` and masking; allowing `fail_fast: true` on individual hooks would reintroduce the N-commit cycle for those hooks

## ALTERNATIVES_CONSIDERED

The alternative considered for each sub-decision is documented within the category above. Across all categories, the consistent rejection patterns were:

- **Skill scope creep (extending CI/CD Architect instead of creating a new skill):** Rejected because pre-commit and CI/CD operate at fundamentally different boundaries (developer machine vs GitHub runner) with different constraints (offline, <30s, no network) and different configuration patterns (local vs remote repos, system vs unsupported language)
- **Monolithic template (one template to rule them all):** Rejected because the three project archetypes (Python, MCP, minimal) have structurally different hook sets; a single template with conditionals would be unreadable and fragile
- **Siloed standards (no upstream link):** Rejected because pre-commit must mirror CI — without an explicit link, the two will inevitably diverge, creating "passes locally, fails in CI" failures
- **Fast-fail-first (default pre-commit behavior):** Rejected because the N-commit cycle degrades developer workflow; collecting all errors in one attempt is strictly better

## CONSEQUENCES

**Positive:**
- 13 PRECOMMIT rules codify all known failure modes from `ha-mcp-readonly` and `local-home-devices-mcp` deployment
- Three templates cover three project archetypes with zero conditional complexity
- Explicit `upstream: ref.ci-cd-standard` dependency forces pre-commit↔CI alignment, preventing "passes locally, fails in CI" failures
- `fail_fast: false` eliminates the N-commit cycle — developers see all errors in a single commit attempt
- The skill persona enforces pre-commit rules during AI-assisted coding sessions, preventing the pitfalls documented in `todo-precommit.md`

**Negative:**
- Three templates must be maintained in sync — adding a new hook type requires updating all three templates
- `fail_fast: false` means developers see more errors per commit, which may be overwhelming for large refactors (mitigation: pre-commit can be skipped with `git commit --no-verify` for intentional WIP commits)
- The upstream dependency means the Pre-commit Architect skill cannot be used in isolation — the CI/CD standard must also exist in the knowledge base
- PRECOMMIT-11 (mypy overrides for all third-party deps) adds maintenance overhead when adding new dependencies

**Risks:**
- Template drift: the three templates may diverge over time if a hook is added to one but not the others
- `ruff target-version` rule (PRECOMMIT-03) depends on the developer reading `requires-python` in `pyproject.toml` — if misread, the same Python 3.13/3.14 compatibility bug will recur
- Environment mismatch between pre-commit (full local env) and CI (minimal env) persists as a systemic risk — PRECOMMIT-11 mitigates but does not eliminate it

**Mitigations:**
- Template review checklist: every PR adding a hook to one template must add it to all three (documented in skill SKILL.md)
- PRECOMMIT-03 includes a verification command: `grep 'target-version' .pre-commit-config.yaml && grep 'requires-python' pyproject.toml`
- Pre-commit-to-CI alignment is validated by the CI/CD Architect skill during CI generation — the agent cross-references `.pre-commit-config.yaml` when generating `ci.yml`

## STATUS

- `proposed: 2026-06-07` — Based on deployment experience from `ha-mcp-readonly` and `local-home-devices-mcp`, plus research on FastAPI, Django, and professional Python projects
- `accepted: 2026-06-07` — Approved with 4 architecture decisions covering skill design, template strategy, upstream dependency, and fail-fast policy
- `updated:` — (none)

## CHANGELOG

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-06-07 | Initial ADR documenting 4 architecture decisions for the Pre-commit Hook Architect standard | opencode |
