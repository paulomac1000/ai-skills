---
name: skill-architect
description: >
  Create, refactor, audit, split, evaluate, and migrate Agent Skills and
  ai-skills packages. Use when deciding whether reusable agent behavior should
  become a skill, designing SKILL.md routing and progressive disclosure,
  restructuring an existing skill, or validating its triggering, resources,
  behavioral effectiveness, portability, and lifecycle.
---

# Skill architect

Use this skill for the engineering lifecycle of reusable Agent Skills, not for
project-local instructions or a one-off prompt.

Read STANDARD.md before making normative decisions.

## Workflow

1. Classify the request as create, audit, refactor, split, migrate, evaluate, or deprecate.
2. Read references/admission-and-scope.md and prove that a new skill is warranted before scaffolding one. Prefer an existing canonical owner, reference, profile, or project-local instruction when that is sufficient.
3. Inspect real task examples, nearby skills, existing failures, and repository constraints. Classify the skill as capability-uplift, workflow-policy, or hybrid.
4. Define one semantic owner and the nearest routing collisions. Read references/routing-and-context.md before writing description or splitting context.
5. Choose the lowest useful degree of freedom. Read references/resources-and-composition.md to decide what belongs in prose, a reference, template, schema, example, or executable tool.
6. Keep the portable runtime package small: SKILL.md, STANDARD.md, manifest.yaml, plus only justified resource directories. Keep eval corpora, benchmark output, reports, changelogs, and release bookkeeping outside the skill directory.
7. For executable or externally sourced content, read references/portability-and-trust.md. When targeting generic Agent Skills hosts, also read references/upstream-agent-skills-compatibility.md; adapters are projections, not policy owners.
8. Add routing and behavioral cases under evals/skills/<skill>/. Read references/behavioral-evaluation.md; compare against a no-skill baseline when capability uplift is the claim.
9. Run tools/audit_skill.py <skill-dir> --repository-root . --strict and tools/validate_skill_evals.py evals/skills/<skill>.
10. For an existing skill, read references/lifecycle-and-migration.md; change only the normative delta, preserve valid consumer behavior, and add regressions for real failures.
11. Run the repository focused checks and full completion gate, then report the exact revision, checks executed, unverified behavioral claims, and residual routing or portability risks.

## Routing boundaries

- Use agents-md-architect for repository instruction systems such as root or nested AGENTS.md; use this skill for reusable task-triggered skills.
- Use afds-doc-writer for general governed-document structure; this skill owns the semantics of skill packages.
- Use ci-cd-architect when the required change is CI infrastructure rather than the skill contract itself.
- Use changelog-release-architect for release-boundary and SemVer decisions after the skill change is complete.

## Constraints

Do not create a skill merely because a workflow is long. Do not hide activation
rules only in the body after selection. Do not duplicate another skill's
normative rules. Do not add empty resource directories or developer artifacts
to the published package. Do not treat examples, templates, generators, local
evals, or model self-review as higher authority than STANDARD.md.
