# AI Skills

A collection of AI skills, standards, and tooling for building reliable agentic systems. Each skill is a persona-driven system prompt that you load into AI agents — Claude, Cursor, or any LLM tool — to enforce proven patterns and conventions during coding sessions. The standards behind them are project-agnostic, machine-parseable, and designed for AI-assisted workflows.

## What's Included

### Skills

Skills are persona-driven system prompts. Load them into AI agents to enforce standards during coding sessions.

| Skill | File | What it does |
|-------|------|--------------|
| AFDS Technical Writer | [`SKILL.md`](skills/afds-doc-writer/SKILL.md) | System prompt — AI agent writes documentation matching AFDS schema. Includes taxonomy router, document templates, and language rules. |
| MCP Server Architect | [`SKILL.md`](skills/mcp-server-architect/SKILL.md) | System prompt — AI agent builds MCP servers per standard. Includes design directives, strict constraints, canonical template selection, consumer ergonomics, and semantic rule anchors. |
| MCP Server Consumer | [`SKILL.md`](skills/mcp-server-consumer/SKILL.md) | System prompt — AI agent discovers, reasons about, and safely invokes MCP tools. Interprets manifests (or risk prefix fallback), applies decision policies, prefers batch/composite calls, starts with minimal detail, handles errors with defined recovery strategies. |
| CI/CD Architect | [`SKILL.md`](skills/ci-cd-architect/SKILL.md) | System prompt — AI agent designs, audits, and generates GitHub Actions workflows per standard. v2.0.0: commit-SHA action pinning, auto-tag→publish chain, .NET 10 support, Semgrep migration. |

### Standards

Core reference documents — authoritative rules for their domains.

| Document | Domain | Covers |
|----------|--------|--------|
| [`docs_standards.md`](skills/afds-doc-writer/docs_standards.md) | AFDS | Document taxonomy, frontmatter schema, body structure, controlled language, CI validation, AI protocol |
| [`mcp-server-standards.md`](skills/mcp-server-architect/mcp-server-standards.md) | MCP Servers | Tool design, response contracts, testing hierarchy, security, canonical templates, consumer ergonomics |
| [`mcp-consumer-standards.md`](skills/mcp-server-consumer/mcp-consumer-standards.md) | MCP Consumption | Capability reasoning, decision policies, token-aware invocation, error recovery, workflow orchestration, version compatibility |
| [`ci-cd-standard.md`](skills/ci-cd-architect/ci-cd-standard.md) | CI/CD | GitHub Actions workflow structure, Docker publish, auto-tag, Semgrep, Dependabot, .NET variant |
| [`action-version-matrix.md`](skills/ci-cd-architect/references/action-version-matrix.md) | CI/CD | Pinned action versions, upgrade policy, migration checklists |

### Templates

Templates are structural documents to copy and fill. They are not persona prompts — they provide the correct frontmatter YAML and body section headers.

| File | Purpose |
|------|---------|
| [`docs-template.md`](skills/afds-doc-writer/docs-template.md) | Fill-in-the-blank template for all 6 AFDS document types |
| [`ci.yml.j2`](skills/ci-cd-architect/templates/ci.yml.j2) | Python CI pipeline (MCP/non-MCP/dockerless variants) |
| [`publish.yml.j2`](skills/ci-cd-architect/templates/publish.yml.j2) | Docker publish + GitHub Release |
| [`auto-tag.yml.j2`](skills/ci-cd-architect/templates/auto-tag.yml.j2) | Automatic version tagging (Python + .NET) |
| [`semgrep.yml.j2`](skills/ci-cd-architect/templates/semgrep.yml.j2) | Security scanning (PR + push) |
| [`dependabot.yml.j2`](skills/ci-cd-architect/templates/dependabot.yml.j2) | Multi-ecosystem dependency management |
| [`dotnet-ci.yml.j2`](skills/ci-cd-architect/templates/dotnet-ci.yml.j2) | .NET CI pipeline variant |
| [`docs-validation.yml.j2`](skills/ci-cd-architect/templates/docs-validation.yml.j2) | Documentation validation workflow |

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

## License

See individual skill directories for license information.
