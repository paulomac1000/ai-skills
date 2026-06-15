# ai-skills — Agent Operations Guide

## Pre-commit Hooks

This project uses pre-commit to enforce code quality before commits.

**Setup**: `pre-commit install`
**Run manually**: `pre-commit run --all-files`
**Hooks mirror CI**: The same checks run in `.github/workflows/ci.yml` lint job.
**Config**: `.pre-commit-config.yaml` follows `ref.precommit-standard` v1.1.0 (includes `detect-private-key` hook).

## Skills

This repo provides 5 persona-driven skill prompts for AI agents. Load the relevant `SKILL.md` into your agent to enforce standards during coding sessions.

| Skill | File | Purpose |
|-------|------|---------|
| AFDS Technical Writer | [`skills/afds-doc-writer/SKILL.md`](skills/afds-doc-writer/SKILL.md) | Write documentation matching AFDS schema — taxonomy router, document templates, language rules |
| MCP Server Architect | [`skills/mcp-server-architect/SKILL.md`](skills/mcp-server-architect/SKILL.md) | Build MCP servers per standard — design directives, constraints, canonical templates, consumer ergonomics |
| MCP Server Consumer | [`skills/mcp-server-consumer/SKILL.md`](skills/mcp-server-consumer/SKILL.md) | Discover, reason about, and safely invoke MCP tools — capability reasoning, decision policies, error recovery |
| CI/CD Architect | [`skills/ci-cd-architect/SKILL.md`](skills/ci-cd-architect/SKILL.md) | Design, audit, and generate GitHub Actions workflows — commit-SHA pinning, auto-tag, Semgrep, Dependabot |
| Pre-commit Hook Architect | [`skills/pre-commit-architect/SKILL.md`](skills/pre-commit-architect/SKILL.md) | Design, audit, and generate `.pre-commit-config.yaml` per standard. v1.1.0: PRECOMMIT-14 content fix, PRECOMMIT-01 sub-clause, Workflow 3 UPGRADE, 15 PRECOMMIT rules, canonical pre-commit.com references, detect-private-key in templates. |

## Installation (for AI coding tools)

The same `SKILL.md` files work across Claude Code, OpenAI Codex CLI, Google Antigravity, and OpenCode. Pick your tool and run the corresponding loop:

```bash
# Pick your destination (one of these 4)
DEST="$HOME/.claude/skills"        # Claude Code
DEST="$HOME/.agents/skills"        # Codex, Antigravity, OpenCode ≥ 0.5
DEST="$HOME/.config/opencode/skills"  # OpenCode (older)
DEST="./.claude/skills"            # project-scoped (any tool)
DEST="./.agents/skills"            # project-scoped (cross-tool)

# Install all 5 skills
mkdir -p "$DEST"
for skill in afds-doc-writer mcp-server-architect mcp-server-consumer ci-cd-architect pre-commit-architect; do
  cp -r "skills/$skill" "$DEST/$skill"
done
```

**Invocation per tool:**

- **Claude Code:** `/<skill-name>` (slash menu)
- **Codex CLI:** `$<skill-name>` (dollar prompt)
- **Antigravity:** auto-loaded via `skill` tool — no manual invocation
- **OpenCode:** `skill({ name: "<skill-name>" })` tool call

For full installation details per tool (verification steps, source URLs), see the **Installation & Tool Integration** section in `README.md`.

## Standards

Core reference documents that define authoritative rules for each domain.

| Reference | Domain | Document |
|-----------|--------|----------|
| `ref.documentation-standard` | AFDS Documentation | [`skills/afds-doc-writer/docs_standards.md`](skills/afds-doc-writer/docs_standards.md) |
| `ref.ci-cd-standard` | CI/CD | [`skills/ci-cd-architect/ci-cd-standard.md`](skills/ci-cd-architect/ci-cd-standard.md) |
| `ref.mcp-server-standards` | MCP Servers | [`skills/mcp-server-architect/mcp-server-standards.md`](skills/mcp-server-architect/mcp-server-standards.md) |
| `ref.precommit-standard` | Pre-commit Hooks | [`skills/pre-commit-architect/precommit-standard.md`](skills/pre-commit-architect/precommit-standard.md) |
| `ref.mcp-consumer-standards` | MCP Consumption | [`skills/mcp-server-consumer/mcp-consumer-standards.md`](skills/mcp-server-consumer/mcp-consumer-standards.md) |
| `ref.action-version-matrix` | CI/CD Action Pins | [`skills/ci-cd-architect/references/action-version-matrix.md`](skills/ci-cd-architect/references/action-version-matrix.md) |

## Cross-References Between Standards

The 5 standards form an integrated ecosystem. The relationships enforced by the skill suite:

| From | To | Why |
|------|----|----|
| `ref.precommit-standard` | `ref.ci-cd-standard` | Pre-commit mirrors CI lint+test jobs (`[RULE: PRECOMMIT-01]`). Ruff rules, mypy strictness, and bandit severity come from CI. |
| `ref.ci-cd-standard` | `ref.mcp-server-standards` | CI must run MCP server tests (`[RULE: TEST-CI-1]` through `[RULE: TEST-CI-4]`), including docker-smoke with tool count. |
| `ref.ci-cd-standard` | `ref.documentation-standard` | CI validates AFDS docs via `docs-validation.yml` (`[RULE: CI-CDW-29]`, `[RULE: CI-CDW-30]`). |
| `ref.precommit-standard` | `ref.documentation-standard` | Pre-commit templates include `docs-validate` hook; `excluded_dirs` must align between them (`[RULE: PRECOMMIT-12]`). |
| `ref.mcp-server-standards` | `ref.mcp-consumer-standards` | Server responses must satisfy consumer's manifest and error-handling expectations. |
| `ref.mcp-consumer-standards` | `ref.documentation-standard` | Consumer READ protocol output follows AFDS controlled-language rules. |
