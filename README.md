# AI Skills

A collection of AI skills, standards, and tooling for building reliable agentic systems. Each skill is a persona-driven system prompt that you load into AI agents — Claude, Codex, Antigravity, OpenCode, or any LLM tool — to enforce proven patterns and conventions during coding sessions. The standards behind them are project-agnostic, machine-parseable, and designed for AI-assisted workflows.

## What's Included

### Skills

Skills are persona-driven system prompts. Load them into AI agents to enforce standards during coding sessions.

| Skill | File | What it does |
|-------|------|--------------|
| AFDS Technical Writer | [`SKILL.md`](skills/afds-doc-writer/SKILL.md) | System prompt — AI agent writes documentation matching AFDS schema. Includes taxonomy router, document templates, and language rules. |
| MCP Server Architect | [`SKILL.md`](skills/mcp-server-architect/SKILL.md) | System prompt — AI agent builds MCP servers per standard. Includes design directives, strict constraints, canonical template selection, consumer ergonomics, and semantic rule anchors. |
| MCP Server Consumer | [`SKILL.md`](skills/mcp-server-consumer/SKILL.md) | System prompt — AI agent discovers, reasons about, and safely invokes MCP tools. Interprets manifests (or risk prefix fallback), applies decision policies, prefers batch/composite calls, starts with minimal detail, handles errors with defined recovery strategies. |
| CI/CD Architect | [`SKILL.md`](skills/ci-cd-architect/SKILL.md) | System prompt — AI agent designs, audits, and generates GitHub Actions workflows per standard. v2.2.0: codecov v7, actions/attest v4, Semgrep org migration, SHA pinning, CI-CDW-76c fix. |
| Pre-commit Hook Architect | [`SKILL.md`](skills/pre-commit-architect/SKILL.md) | System prompt — AI agent designs, audits, and generates `.pre-commit-config.yaml` per standard. v1.1.0: PRECOMMIT-14 content fix, PRECOMMIT-01 sub-clause, Workflow 3 UPGRADE, 15 PRECOMMIT rules, canonical https://pre-commit.com/ references, hook-catalog rewritten as project pinning index. |

### Standards

Core reference documents — authoritative rules for their domains.

| Document | Domain | Covers |
|----------|--------|--------|
| [`docs_standards.md`](skills/afds-doc-writer/docs_standards.md) | AFDS | Document taxonomy, frontmatter schema, body structure, controlled language, CI validation, AI protocol |
| [`mcp-server-standards.md`](skills/mcp-server-architect/mcp-server-standards.md) | MCP Servers | Tool design, response contracts, testing hierarchy, security, canonical templates, consumer ergonomics |
| [`mcp-consumer-standards.md`](skills/mcp-server-consumer/mcp-consumer-standards.md) | MCP Consumption | Capability reasoning, decision policies, token-aware invocation, error recovery, workflow orchestration, version compatibility |
| [`ci-cd-standard.md`](skills/ci-cd-architect/ci-cd-standard.md) | CI/CD | GitHub Actions workflow structure, Docker publish, auto-tag, Semgrep, Dependabot, .NET variant |
| [`action-version-matrix.md`](skills/ci-cd-architect/references/action-version-matrix.md) | CI/CD | Pinned action versions, upgrade policy, migration checklists |
| [`precommit-standard.md`](skills/pre-commit-architect/precommit-standard.md) | Pre-commit | Hook ordering, CI mirroring, speed budgets, environment consistency, AGENTS.md integration |

### Templates

Templates are structural documents to copy and fill. They are not persona prompts — they provide the correct frontmatter YAML and body section headers.

| File | Purpose |
|------|---------|
| [`docs-template.md`](skills/afds-doc-writer/docs-template.md) | Fill-in-the-blank template for all 7 AFDS document types |
| [`ci.yml.j2`](skills/ci-cd-architect/templates/ci.yml.j2) | Python CI pipeline (MCP/non-MCP/dockerless variants) |
| [`publish.yml.j2`](skills/ci-cd-architect/templates/publish.yml.j2) | Docker publish + GitHub Release |
| [`auto-tag.yml.j2`](skills/ci-cd-architect/templates/auto-tag.yml.j2) | Automatic version tagging (Python + .NET) |
| [`semgrep.yml.j2`](skills/ci-cd-architect/templates/semgrep.yml.j2) | Security scanning (PR + push) |
| [`dependabot.yml.j2`](skills/ci-cd-architect/templates/dependabot.yml.j2) | Multi-ecosystem dependency management |
| [`dotnet-ci.yml.j2`](skills/ci-cd-architect/templates/dotnet-ci.yml.j2) | .NET CI pipeline variant |
| [`docs-validation.yml.j2`](skills/ci-cd-architect/templates/docs-validation.yml.j2) | Documentation validation workflow |
| [`pre-commit-python.j2`](skills/pre-commit-architect/templates/pre-commit-python.j2) | Base Python `.pre-commit-config.yaml` |
| [`pre-commit-mcp.j2`](skills/pre-commit-architect/templates/pre-commit-mcp.j2) | MCP variant with tool count + manifest validation |
| [`pre-commit-minimal.j2`](skills/pre-commit-architect/templates/pre-commit-minimal.j2) | Fast checks only (<10s) |
| [`pre-commit-shell.j2`](skills/pre-commit-architect/templates/pre-commit-shell.j2) | Native bash `.githooks/pre-commit` (no pre-commit framework) for .NET, Rust, Go, polyglot |

## Installation & Tool Integration

The same `SKILL.md` files work across all major AI coding tools — only the install location and invocation prefix differ. Skills are **portable**: write once, run in any tool.

### Quick install (all skills into a single tool)

```bash
# Clone once
git clone https://github.com/paulomac1000/ai-skills.git
cd ai-skills

# Then follow the per-tool section below
```

### Claude Code (Anthropic)

Claude Code discovers skills from `~/.claude/skills/<name>/SKILL.md` or a local `.claude/skills/` directory.

```bash
# One-time install — copy ALL 5 skills into user-global location
mkdir -p ~/.claude/skills
for skill in afds-doc-writer mcp-server-architect mcp-server-consumer ci-cd-architect pre-commit-architect; do
  cp -r "skills/$skill" "$HOME/.claude/skills/$skill"
done

# Or, project-scoped (only this project)
mkdir -p .claude/skills
for skill in afds-doc-writer mcp-server-architect mcp-server-consumer ci-cd-architect pre-commit-architect; do
  cp -r "skills/$skill" ".claude/skills/$skill"
done
```

**Invocation:** in a Claude Code session, type `/<skill-name>` (e.g., `/pre-commit-architect`, `/ci-cd-architect`).

**Verification:** open Claude Code, type `/` — you should see the 5 skill names in the slash command menu.

**Source:** <https://docs.anthropic.com/en/docs/claude-code/skills>

### OpenAI Codex CLI

Codex reads skills from `~/.agents/skills/<name>/SKILL.md` (the cross-tool portable location).

```bash
# Copy skills into the user-global .agents/skills/ directory
mkdir -p ~/.agents/skills
for skill in afds-doc-writer mcp-server-architect mcp-server-consumer ci-cd-architect pre-commit-architect; do
  cp -r "skills/$skill" "$HOME/.agents/skills/$skill"
done
```

**Invocation:** in a Codex session, type `$<skill-name>` (e.g., `$ci-cd-architect`).

**Verification:** start Codex in a project, type `$` — skills appear in the prompt menu.

**Source:** <https://developers.openai.com/codex>

### Google Antigravity

Antigravity uses the same `~/.agents/skills/` location as Codex (the cross-tool standard).

```bash
mkdir -p ~/.agents/skills
for skill in afds-doc-writer mcp-server-architect mcp-server-consumer ci-cd-architect pre-commit-architect; do
  cp -r "skills/$skill" "$HOME/.agents/skills/$skill"
done
```

**Invocation:** Antigravity auto-detects skills via the `skill` tool. The agent loads them when relevant to the task; no slash command required.

**Verification:** in Antigravity, ask the agent "what skills do you have available?" — it should list the 5 ai-skills.

**Source:** <https://antigravity.google/docs>

### OpenCode (sst/opencode)

OpenCode reads skills from `~/.config/opencode/skills/<name>/SKILL.md` or a project's `.opencode/skills/`.

```bash
# User-global install
mkdir -p ~/.config/opencode/skills
for skill in afds-doc-writer mcp-server-architect mcp-server-consumer ci-cd-architect pre-commit-architect; do
  cp -r "skills/$skill" "$HOME/.config/opencode/skills/$skill"
done

# Or project-scoped (committed to repo, shared with team)
mkdir -p .opencode/skills
for skill in afds-doc-writer mcp-server-architect mcp-server-consumer ci-cd-architect pre-commit-architect; do
  cp -r "skills/$skill" ".opencode/skills/$skill"
done
```

**Invocation:** in OpenCode, use the built-in `skill` tool — `skill({ name: "ci-cd-architect" })`.

**Verification:** in OpenCode, run `skill({ name: "pre-commit-architect" })` — the system prompt for that skill should load.

**Source:** <https://opencode.ai/docs/skills>

### Cross-tool portable install (recommended for monorepos / multi-tool teams)

A growing number of tools (Antigravity, Codex, OpenCode ≥ 0.5, future tools) read from a single shared location: `~/.agents/skills/`. Putting skills there works across all of them with one install:

```bash
# Single canonical location — works in 3 of 4 tools today
mkdir -p ~/.agents/skills
for skill in afds-doc-writer mcp-server-architect mcp-server-consumer ci-cd-architect pre-commit-architect; do
  cp -r "skills/$skill" "$HOME/.agents/skills/$skill"
done
```

Claude Code uses `~/.claude/skills/` and is not yet compatible with the cross-tool location. To cover all four tools, install into both:

```bash
mkdir -p ~/.claude/skills ~/.agents/skills
for skill in afds-doc-writer mcp-server-architect mcp-server-consumer ci-cd-architect pre-commit-architect; do
  cp -r "skills/$skill" "$HOME/.claude/skills/$skill"
  cp -r "skills/$skill" "$HOME/.agents/skills/$skill"
done
```

### Updating skills

When the ai-skills repo is updated (e.g., new `v1.1.0` of precommit-architect), re-run the `cp -r` commands above to refresh your local install. The destination directory structure (`<skill>/SKILL.md`) must be preserved — tools scan the directory name, not the file path.

## Project Layout

```
skills/
├── afds-doc-writer/              ← AFDS documentation skill
│   ├── docs_standards.md         Standard
│   ├── SKILL.md                  System prompt for AI agents
│   ├── docs_validate.py          CI validation script
│   ├── docs-template.md          Document template
│   └── afds_config.yaml          Validator configuration
├── mcp-server-architect/         ← MCP server skill
│   ├── mcp-server-standards.md   Standard
│   └── SKILL.md                  System prompt for AI agents
├── mcp-server-consumer/          ← MCP consumer skill
│   ├── mcp-consumer-standards.md Standard
│   ├── SKILL.md                  System prompt for AI agents
│   └── tools/                    Reference implementation (decision engine)
├── pre-commit-architect/         ← Pre-commit hook skill
│   ├── precommit-standard.md     Standard
│   ├── SKILL.md                  System prompt for AI agents
│   ├── templates/                4 Jinja2 templates
│   └── references/               Hook catalog + pitfalls
└── ci-cd-architect/              ← CI/CD skill
    ├── ci-cd-standard.md         Standard
    ├── SKILL.md                  System prompt for AI agents
    ├── templates/                Jinja2 workflow templates
    └── references/               Action version matrix

tests/                            Pytest tests covering all standards
decisions/                        Architecture Decision Records
```

## Quick Start

```bash
pip install pyyaml pytest

# Validate all standards and decisions
python3 skills/afds-doc-writer/docs_validate.py \
  --config skills/afds-doc-writer/afds_config.yaml \
  skills/afds-doc-writer/docs_standards.md \
  skills/mcp-server-architect/mcp-server-standards.md \
  skills/mcp-server-consumer/mcp-consumer-standards.md \
  skills/ci-cd-architect/ci-cd-standard.md \
  decisions/

# Run tests
python3 -m pytest tests/ -v
```

## Philosophy

- **Single Source of Truth** — every rule in one location, referenced, never duplicated
- **AI-first documentation** — deterministic structure for agents, readable for humans
- **Operationally relevant** — document boundary conditions that affect production behavior
- **Self-validating** — the standard validates itself against its own rules
- **Project-agnostic** — no hardcoded project names, configurable per domain
- **Tool-portable** — same `SKILL.md` runs in Claude Code, Codex, Antigravity, OpenCode

## License

See individual skill directories for license information.
