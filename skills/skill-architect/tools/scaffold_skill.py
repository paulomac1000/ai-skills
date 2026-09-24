from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _repository_version(repository_root: Path) -> str:
    catalog = yaml.safe_load(
        (repository_root / "contracts/rule-catalog.yaml").read_text(encoding="utf-8")
    )
    return str(catalog["catalog_version"])


def _render(template: str, replacements: dict[str, str]) -> str:
    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def scaffold(repository_root: Path, name: str, description: str) -> Path:
    repository_root = repository_root.resolve()
    if not NAME.fullmatch(name) or len(name) > 64:
        raise ValueError("skill name must be lowercase kebab-case and <=64 characters")
    if not description.strip() or len(description) > 1024:
        raise ValueError("description must be non-empty and <=1024 characters")

    target = repository_root / "skills" / name
    if target.exists():
        raise FileExistsError(f"skill already exists: {target}")
    target.mkdir(parents=True)

    template_root = Path(__file__).resolve().parents[1] / "templates"
    replacements = {
        "<SKILL_NAME>": name,
        "<SKILL_TITLE>": name.replace("-", " ").title(),
        "<WHAT_THE_SKILL_DOES_AND_WHEN_IT_SHOULD_BE_SELECTED>": description,
        "<PRIMARY_ACTIVATION_BOUNDARY>": (
            "the request matches this skill's reusable semantic scope"
        ),
        "<CLASSIFY_THE_TASK>": (
            "Classify the task and preserve requested read/write scope."
        ),
        "<COLLECT_REQUIRED_EVIDENCE>": (
            "Collect evidence before making durable claims."
        ),
        "<LOAD_ONLY_APPLICABLE_REFERENCES>": (
            "Load only references needed for the selected path."
        ),
        "<EXECUTE_OR_DELEGATE_DETERMINISTIC_MECHANICS>": (
            "Use deterministic tools for repeatable mechanics."
        ),
        "<VERIFY_AND_REPORT>": (
            "Run applicable verification and report uncertainty."
        ),
        "<NEAREST_COLLISION_AND_OWNER>": (
            "Name the closest competing skill and its boundary."
        ),
        "<CRITICAL_ALWAYS_VISIBLE_CONSTRAINTS>": (
            "State only constraints that must remain visible on every invocation."
        ),
        "<SEMANTIC_RESPONSIBILITY>": (
            "Define the one durable responsibility this skill owns."
        ),
        "<CANONICAL_OWNER_AND_COMPOSITION_RULES>": (
            "Define precedence, dependencies, and non-goals."
        ),
        "<ASSESSABLE_INVARIANTS>": (
            "State durable requirements that can be reviewed or tested."
        ),
        "<WHAT_PROVES_THE_CONTRACT>": (
            "Define deterministic and behavioral evidence requirements."
        ),
        "<COMPLETION_CONDITIONS>": (
            "Define when the skill change is complete."
        ),
        "<EXACT_VERIFICATION_COMMAND_OR_PROCESS>": (
            "Run the repository skill audit and applicable behavioral evaluation."
        ),
        "<EXACT_VERIFICATION_STEPS>": (
            "Run focused checks and the repository completion gate."
        ),
        "<REPOSITORY_RELEASE_VERSION>": _repository_version(repository_root),
    }

    skill_template = (template_root / "SKILL.md.template").read_text(
        encoding="utf-8"
    )
    standard_template = (template_root / "STANDARD.md.template").read_text(
        encoding="utf-8"
    )
    manifest_template = (template_root / "manifest.yaml.template").read_text(
        encoding="utf-8"
    )

    (target / "SKILL.md").write_text(
        _render(skill_template, replacements),
        encoding="utf-8",
    )
    (target / "STANDARD.md").write_text(
        _render(standard_template, replacements),
        encoding="utf-8",
    )
    (target / "manifest.yaml").write_text(
        _render(manifest_template, replacements),
        encoding="utf-8",
    )
    return target


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the minimal core of a new ai-skills package."
    )
    parser.add_argument("name")
    parser.add_argument("description")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    target = scaffold(args.repository_root, args.name, args.description)
    print(target)
    print(
        "Next: define admission/routing evidence, register catalog rules, "
        "and add only resources the workflow actually needs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
