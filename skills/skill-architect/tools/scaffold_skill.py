from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _render(template: str, replacements: dict[str, str]) -> str:
    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def _inside(root: Path, target: Path) -> bool:
    try:
        target.resolve(strict=False).relative_to(root)
    except ValueError:
        return False
    return True


def _skills_root(repository_root: Path) -> Path:
    skills_root = repository_root / "skills"
    if skills_root.is_symlink():
        raise ValueError("skills directory must not be a symlink")
    if not _inside(repository_root, skills_root):
        raise ValueError("skills directory resolves outside repository root")
    if skills_root.exists() and not skills_root.is_dir():
        raise NotADirectoryError(f"skills path is not a directory: {skills_root}")
    skills_root.mkdir(parents=True, exist_ok=True)
    return skills_root


def scaffold(repository_root: Path, name: str, description: str) -> Path:
    repository_root = repository_root.resolve()
    if not NAME.fullmatch(name) or len(name) > 64:
        raise ValueError("skill name must be lowercase kebab-case and <=64 characters")
    normalized_description = " ".join(description.split())
    if not normalized_description or len(normalized_description) > 1024:
        raise ValueError("description must be non-empty and <=1024 characters")

    skills_root = _skills_root(repository_root)
    target = skills_root / name
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"skill already exists: {target}")
    if not _inside(repository_root, target):
        raise ValueError("skill target resolves outside repository root")

    template_root = Path(__file__).resolve().parents[1] / "templates"
    replacements = {
        "<SKILL_NAME>": name,
        "<SKILL_TITLE>": name.replace("-", " ").title(),
        "<WHAT_THE_SKILL_DOES_AND_WHEN_IT_SHOULD_BE_SELECTED>": normalized_description,
        "<PRIMARY_ACTIVATION_BOUNDARY>": ("the request matches this skill's reusable semantic scope"),
        "<CLASSIFY_THE_TASK>": ("Classify the task and preserve requested read/write scope."),
        "<COLLECT_REQUIRED_EVIDENCE>": ("Collect evidence before making durable claims."),
        "<LOAD_ONLY_APPLICABLE_REFERENCES>": ("Load only references needed for the selected path."),
        "<EXECUTE_OR_DELEGATE_DETERMINISTIC_MECHANICS>": ("Use deterministic tools for repeatable mechanics."),
        "<VERIFY_AND_REPORT>": ("Run applicable verification and report uncertainty."),
        "<NEAREST_COLLISION_AND_OWNER>": ("Name the closest competing skill and its boundary."),
        "<CRITICAL_ALWAYS_VISIBLE_CONSTRAINTS>": (
            "State only constraints that must remain visible on every invocation."
        ),
        "<SEMANTIC_RESPONSIBILITY>": ("Define the one durable responsibility this skill owns."),
        "<CANONICAL_OWNER_AND_COMPOSITION_RULES>": ("Define precedence, dependencies, and non-goals."),
        "<ASSESSABLE_INVARIANTS>": ("State durable requirements that can be reviewed or tested."),
        "<WHAT_PROVES_THE_CONTRACT>": ("Define deterministic and behavioral evidence requirements."),
        "<COMPLETION_CONDITIONS>": ("Define when the skill change is complete."),
        "<EXACT_VERIFICATION_COMMAND_OR_PROCESS>": (
            "Run the repository skill audit and applicable behavioral evaluation."
        ),
        "<EXACT_VERIFICATION_STEPS>": ("Run focused checks and the repository completion gate."),
    }

    # Render everything before creating the destination. Template/read failures
    # therefore leave no half-created skill that blocks a safe retry.
    skill_text = _render((template_root / "SKILL.md.template").read_text(encoding="utf-8"), replacements)
    standard_text = _render((template_root / "STANDARD.md.template").read_text(encoding="utf-8"), replacements)
    manifest_text = _render((template_root / "manifest.yaml.template").read_text(encoding="utf-8"), replacements)

    target.mkdir()
    try:
        (target / "SKILL.md").write_text(skill_text, encoding="utf-8")
        (target / "STANDARD.md").write_text(standard_text, encoding="utf-8")
        (target / "manifest.yaml").write_text(manifest_text, encoding="utf-8")
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the minimal core of a new ai-skills package.")
    parser.add_argument("name")
    parser.add_argument("description")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        target = scaffold(args.repository_root, args.name, args.description)
    except (ValueError, OSError) as exc:
        print(f"ERROR skill.scaffold.failed: {exc}", file=sys.stderr)
        return 2
    print(target)
    print(
        "Next: define admission/routing evidence, register catalog rules, "
        "and add only resources the workflow actually needs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
