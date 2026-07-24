# AI Skills

A production-oriented collection of reusable skills, standards, implementation playbooks, executable policy helpers, and tested workflow templates for AI-assisted software engineering.

## Included skills

| Skill | Purpose | Reusable resources |
| --- | --- | --- |
| `afds-doc-writer` | Create, validate, and maintain evidence-based technical documentation. | Validator, lifecycle and impact playbooks, governed-document template |
| `ci-cd-architect` | Design secure and reproducible local and hosted quality gates. | Python, .NET, MCP, documentation, security, packaging, dependency, and container workflows |
| `mcp-server-architect` | Design secure, observable, and agent-friendly MCP servers. | Language-neutral core, Python/FastMCP and .NET profiles, testing, security, operations, examples |
| `mcp-server-consumer` | Select and invoke MCP capabilities safely and efficiently. | Deterministic decision engine and workflow, retry, pagination, and trust playbooks |

Local pre-commit and pre-push design is part of `ci-cd-architect`. It is not a separate architectural domain.

## Repository model

Every skill contains:

- `SKILL.md` — concise agent workflow and routing instructions;
- `STANDARD.md` — stable cross-project invariants and acceptance criteria;
- `manifest.yaml` — versioned compatibility, maturity, dependency, deprecation, resource-category, and required-entry-point contract.

A skill may also contain `references/`, `templates/`, `examples/`, `tools/`, or reviewed dependency `locks/`. Those directories hold reusable operational knowledge, not temporary analysis artifacts. The repository deliberately has no global file-count budget and does not forbid examples or architectural decisions merely to keep the tree small.

## Contract and precedence

Consumers pin the repository revision and the skill version recorded in `manifest.yaml`. A release-candidate skill is suitable for controlled pilots and independent review; a stable skill requires completed compatibility evidence, complete hashed dependency locks where Python is executed, and a validated adoption assessment for the immutable revision.

When resources disagree, use this order:

1. `STANDARD.md` and active normative decisions;
2. the applicable implementation profile;
3. `SKILL.md` workflow instructions;
4. generators and templates;
5. examples;
6. migration simulations.

A lower-ranked resource cannot weaken a higher-ranked requirement. Generators are verified baselines rather than policy owners, and examples do not create exceptions. Stop and request a standard decision when a conflict remains unresolved.

## Local validation

POSIX:

```bash
python3 -m venv .venv
.venv/bin/python scripts/install_locked.py
.venv/bin/python scripts/ci.py
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe scripts\install_locked.py
.venv\Scripts\python.exe scripts\ci.py
```

The installer selects the committed platform lock, installs the complete transitive graph with `--require-hashes`, and runs `pip check`. The validation command compiles Python sources, runs lint, formatting, typing, static security and dependency-vulnerability gates, validates governed Markdown, manifests, adoption contracts, and full stable rule coverage, executes exact-artifact generator tests, enforces critical-module branch coverage, and runs the complete non-container test suite.

## Adoption and compatibility evidence

Repository-wide adoption contracts live in [`contracts/`](contracts/README.md). Every skill manifest points to the same JSON Schema, generic assessment template, semantic validator, stable rule catalog, and normative-heading map. Skill-specific evidence is an extension of that base contract rather than an incompatible private form.

A completed assessment is accepted only when:

- every catalog rule appears exactly once;
- immutable repository and artifact revisions agree;
- exact OS, architecture, runtime, version, and lane results passed;
- approving assessments use provider-backed run, job, artifact, digest, and review evidence on the same SHA;
- deferred rules have live, owned waivers;
- rollback and residual risks are explicit;
- a canonical independent reviewer identity approves the immutable revision.

Run `python contracts/validate_adoption.py <assessment.yaml> --require-approval` in each adopting repository. The committed [`contracts/compatibility-matrix.yaml`](contracts/compatibility-matrix.yaml) maps every declared OS, architecture, runtime, version, provider, and container claim to a named GitHub Actions lane. Structural attestation cannot approve an adoption; `--require-approval` requires provider-backed evidence verified against GitHub.

## Design principles

- Keep one canonical owner for each rule, but preserve implementation detail in focused playbooks.
- Separate language-neutral invariants from SDK-specific patterns.
- Prefer executable templates and regression tests over aspirational prose.
- Treat tool metadata from remote systems as untrusted unless a trust boundary is explicit.
- Build and test the artifact that is actually published.
- Record failure patterns and the corrective rule when practical incidents reveal a reusable lesson.
- Preserve valuable history by integrating it into current guidance, not by shipping duplicate or obsolete standards.

## Recovery audit

[`RECOVERY_AUDIT.md`](RECOVERY_AUDIT.md) maps the knowledge removed by the cleanup commit to its new canonical location and records which unsafe legacy defaults were intentionally rejected.

## License

MIT. See [LICENSE](LICENSE).
