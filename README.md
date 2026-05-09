---
description: AI skills, standards, and tooling for building reliable agentic systems — documentation framework, MCP server patterns, validator, and persona-driven agent prompts
doc_id: ref.readme
type: ref
status: active
rigor_tier: L1
ttl_days: 365
ttl_policy: extended
stability: stable
ai_scope: editable
upstream:
  - ref.documentation-standard
last_verified: 2026-05-08
owners: ["docs-maintainers"]
doc_kind: atomic
glossary_terms: []
---

# AI Skills

A collection of AI skills, standards, and tooling for building reliable agentic systems. Each skill is a persona-driven system prompt that you load into AI agents — Claude, Cursor, or any LLM tool — to enforce proven patterns and conventions during coding sessions. The standards behind them are project-agnostic, machine-parseable, and designed for AI-assisted workflows.

## Standards Included

### Documentation Standards

| File | Domain | Covers |
|------|--------|--------|
| [`docs_standards.md`](skills/afds-doc-writer/docs_standards.md) | AFDS | Document taxonomy, frontmatter schema, body structure, controlled language, CI validation, AI protocol |
| [`mcp_standards.md`](skills/mcp-server-architect/mcp_standards.md) | MCP Servers | Tool design, response contracts, testing hierarchy, security, canonical templates |

### Skills

Skills are persona-driven system prompts. Load them into AI agents (Claude, Cursor, and similar tools) to enforce standards during coding sessions.

| Skill | File | What it does |
|-------|------|--------------|
| AFDS Technical Writer | [`skill.md`](skills/afds-doc-writer/skill.md) | System prompt — AI agent writes documentation matching AFDS schema. Includes taxonomy router, document templates, and language rules. |
| MCP Server Architect | [`skill.md`](skills/mcp-server-architect/skill.md) | System prompt — AI agent builds MCP servers per standard. Includes design directives, strict constraints, canonical template selection, and semantic rule anchors. |

### Templates

Templates are structural documents you copy and fill. They are not persona prompts — they provide the correct frontmatter YAML and body section headers.

| File | Purpose |
|------|---------|
| [`docs-template.md`](templates/docs-template.md) | Fill-in-the-blank template with frontmatter examples for all 6 document types and correct body section headers |

## Project Layout

```
skills/
├── afds-doc-writer/              ← AFDS documentation skill
│   ├── docs_standards.md         Standard
│   ├── skill.md                  System prompt for AI agents
│   ├── docs_validate.py          CI validation script
│   └── afds_config.yaml          Validator configuration
└── mcp-server-architect/         ← MCP server skill
    ├── mcp_standards.md          Standard
    └── skill.md                  System prompt for AI agents

templates/
└── docs-template.md              Copy-and-fill template for new docs

tests/                            90 pytest tests covering all standards
decisions/                        Architecture Decision Records for each standard
```

## Tooling

| Tool | Path | Purpose |
|------|------|---------|
| Validator | `skills/afds-doc-writer/docs_validate.py` | AFDS CI validation — checks frontmatter, section presence, banned words, link integrity |
| Config | `skills/afds-doc-writer/afds_config.yaml` | Project-specific document type definitions, section schemas, exempt files |
| Tests | `tests/` | 90 pytest tests covering all standards and templates pass validation |

## Quick Start

```bash
pip install pyyaml pytest

# Validate all standards and decisions
python3 skills/afds-doc-writer/docs_validate.py --config skills/afds-doc-writer/afds_config.yaml \
  skills/afds-doc-writer/docs_standards.md skills/mcp-server-architect/mcp_standards.md \
  templates/docs-template.md decisions/decision.001-docs-standard-decisions.md \
  decisions/decision.002-mcp-standard-decisions.md

# Run tests
python3 -m pytest tests/ -v
```

## Philosophy

- **Single Source of Truth** — every rule in one location, referenced, never duplicated
- **AI-first documentation** — deterministic structure for agents, readable for humans
- **Operationally relevant** — document boundary conditions that affect production behavior
- **Self-validating** — the standard validates itself against its own rules
- **Project-agnostic** — no hardcoded project names, configurable per domain domain
