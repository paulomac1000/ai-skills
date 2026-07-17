# AI Skills

A project-independent collection of skills, standards, executable helpers, and tested workflow templates for AI-assisted software engineering.

## Included skills

| Skill | Purpose | Bundled resources |
| --- | --- | --- |
| `afds-doc-writer` | Create and review evidence-based technical documentation. | Markdown validator |
| `ci-cd-architect` | Design and audit secure, reproducible delivery pipelines. | Python, .NET, documentation, and container-publish workflow templates |
| `mcp-server-architect` | Design secure and agent-friendly MCP servers. | Normative server standard |
| `mcp-server-consumer` | Select and invoke MCP capabilities safely and efficiently. | Pure-Python decision engine |
| `pre-commit-architect` | Design fast local checks that preserve CI authority. | Normative local-check standard |

Each skill contains a required `SKILL.md` and a detailed `STANDARD.md`. A skill may also contain executable scripts or templates when they provide reusable behavior rather than historical context.

## Repository layout

```text
skills/
├── afds-doc-writer/
│   ├── SKILL.md
│   ├── STANDARD.md
│   └── validate.py
├── ci-cd-architect/
│   ├── SKILL.md
│   ├── STANDARD.md
│   └── templates/
├── mcp-server-architect/
│   ├── SKILL.md
│   └── STANDARD.md
├── mcp-server-consumer/
│   ├── SKILL.md
│   ├── STANDARD.md
│   └── tools/
└── pre-commit-architect/
    ├── SKILL.md
    └── STANDARD.md
```

Bundled resources are limited to files needed for agent execution, deterministic validation, or reusable workflow generation. Historical development records remain in Git history and the changelog.

## Local validation

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/ci.py
```

The command compiles Python sources, validates governed Markdown, and runs the complete test suite. It is the local equivalent of the GitHub Actions quality gate.

## Using a skill

1. Load the relevant `SKILL.md` into an agent-compatible skills directory.
2. Let the agent read the accompanying `STANDARD.md` before it changes code or documentation.
3. Copy or adapt bundled templates only after inspecting the target repository.
4. Run the repository's own verification commands before accepting generated output.

## Design principles

- Preserve one canonical source for each rule.
- Keep procedural instructions in `SKILL.md` and detailed constraints in `STANDARD.md`.
- Bundle executable helpers only when deterministic behavior is valuable.
- Prefer project-independent contracts over examples tied to one deployment.
- Treat validation as evidence of structure and behavior, not proof that prose is factually true.

## License

MIT. See [LICENSE](LICENSE).
