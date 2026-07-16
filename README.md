# AI Skills

Small, testable skills for agents that build documentation, MCP integrations, CI/CD, and local developer checks.

## Design

This repository separates five concerns that were previously mixed together:

1. `SKILL.md` is a short routing and execution prompt.
2. The core standard contains stable, language-neutral rules.
3. References contain framework, language, and project-specific guidance loaded only when needed.
4. Scripts validate or generate facts that should not be copied into prose.
5. Benchmarks prove that a standard improves retrieval and defect detection before it becomes mandatory.

The skills follow progressive disclosure. An agent starts with `SKILL.md`, loads the core standard for the task, and opens only the relevant references.

## Skills

| Skill | Purpose | Core standard |
|---|---|---|
| `afds-doc-writer` | Create, update, retrieve, and audit engineering documentation | `docs_standards.md` |
| `mcp-server-architect` | Design and implement MCP servers in Python or .NET | `mcp-server-standards.md` |
| `mcp-server-consumer` | Select and invoke MCP capabilities safely and efficiently | `mcp-consumer-standards.md` |
| `ci-cd-architect` | Audit and build property-driven GitHub Actions workflows | `ci-cd-standard.md` |
| `pre-commit-architect` | Design fast local checks that complement CI | `precommit-standard.md` |

## Install

Use the installer instead of copying a hardcoded skill list:

```bash
python3 scripts/install_skills.py --target ~/.agents/skills
python3 scripts/install_skills.py --target ~/.claude/skills
python3 scripts/install_skills.py --target ~/.config/opencode/skills
```

The source tree is copied one directory per skill. Tool-specific invocation syntax is deliberately not embedded here because it changes independently of the skills.

## Validate

```bash
python3 skills/afds-doc-writer/docs_validate.py \
  skills/afds-doc-writer/docs_standards.md \
  skills/mcp-server-architect/mcp-server-standards.md \
  skills/mcp-server-consumer/mcp-consumer-standards.md \
  skills/ci-cd-architect/ci-cd-standard.md \
  skills/pre-commit-architect/precommit-standard.md
python3 -m pytest -q
python3 benchmarks/afds/benchmark.py --check --output benchmarks/afds/latest-results.json
python3 scripts/dependency_catalog.py
```

## Dependency versions

Package and action versions belong in manifests and lock files. Dependabot updates those files. `scripts/dependency_catalog.py` derives a readable catalog from the repository state; standards and skills refer to the catalog rather than copying version numbers.

## MCP reference lab

`examples/dotnet-mcp-reference-lab` ports the strongest patterns from the author's Python servers into isolated .NET experiments:

- read-only Home Assistant boundary,
- write authorization and confirmation for Kontomierz,
- OpenWrt command allowlisting,
- Mikrus adapter composition,
- local-device discovery isolation.

The examples share a policy library but intentionally test different design choices. They are a laboratory, not five production replacements.

## Repository rules

- Stable rules live once in a core standard.
- Framework details live in references.
- Generated facts are marked and regenerated.
- Examples may demonstrate alternatives; standards state the chosen default.
- A new mandatory rule requires a validator, test, benchmark, or a documented reason why automation is impossible.
