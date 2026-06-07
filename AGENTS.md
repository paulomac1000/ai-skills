## Pre-commit Hooks

This project uses pre-commit to enforce code quality before commits.

**Setup**: `pre-commit install`
**Run manually**: `pre-commit run --all-files`
**Hooks mirror CI**: The same checks run in `.github/workflows/ci.yml` lint job.
**Config**: `.pre-commit-config.yaml` follows `ref.precommit-standard` v1.0.0.

## Skills

This repo provides 5 persona-driven skill prompts for AI agents. Load the relevant `SKILL.md` into your agent to enforce standards during coding sessions.

| Skill | File | Purpose |
|-------|------|---------|
| AFDS Technical Writer | [`skills/afds-doc-writer/SKILL.md`](skills/afds-doc-writer/SKILL.md) | Write documentation matching AFDS schema — taxonomy router, document templates, language rules |
| MCP Server Architect | [`skills/mcp-server-architect/SKILL.md`](skills/mcp-server-architect/SKILL.md) | Build MCP servers per standard — design directives, constraints, canonical templates, consumer ergonomics |
| MCP Server Consumer | [`skills/mcp-server-consumer/SKILL.md`](skills/mcp-server-consumer/SKILL.md) | Discover, reason about, and safely invoke MCP tools — capability reasoning, decision policies, error recovery |
| CI/CD Architect | [`skills/ci-cd-architect/SKILL.md`](skills/ci-cd-architect/SKILL.md) | Design, audit, and generate GitHub Actions workflows — commit-SHA pinning, auto-tag, Semgrep, Dependabot |
| Pre-commit Hook Architect | [`skills/pre-commit-architect/SKILL.md`](skills/pre-commit-architect/SKILL.md) | Design, audit, and generate `.pre-commit-config.yaml` per standard |

## Standards

Core reference documents that define authoritative rules for each domain.

| Reference | Domain | Document |
|-----------|--------|----------|
| `ref.documentation-standard` | AFDS Documentation | [`skills/afds-doc-writer/docs_standards.md`](skills/afds-doc-writer/docs_standards.md) |
| `ref.ci-cd-standard` | CI/CD | [`skills/ci-cd-architect/ci-cd-standard.md`](skills/ci-cd-architect/ci-cd-standard.md) |
| `ref.mcp-server-standards` | MCP Servers | [`skills/mcp-server-architect/mcp-server-standards.md`](skills/mcp-server-architect/mcp-server-standards.md) |
| `ref.precommit-standard` | Pre-commit Hooks | [`skills/pre-commit-architect/precommit-standard.md`](skills/pre-commit-architect/precommit-standard.md)
