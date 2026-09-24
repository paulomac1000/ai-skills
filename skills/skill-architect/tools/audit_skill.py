from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ALLOWED_DIRECTORIES = {"references", "templates", "examples", "tools", "locks"}
FORBIDDEN_TOP_LEVEL = {
    "evals",
    "reports",
    "CHANGELOG.md",
    "README.md",
    "VERSION",
    "MANIFEST.json",
}
ROUTED_PATH = re.compile(
    r"(?P<path>STANDARD\.md|(?:references|templates|examples|tools|locks)/[A-Za-z0-9_.\-/]+\.(?:md|py|ya?ml|json|template|j2|txt|toml|lock|cs|csproj|sh|ps1))"
)


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    message: str


def _finding(severity: str, code: str, path: Path, message: str) -> Finding:
    return Finding(severity=severity, code=code, path=path.as_posix(), message=message)


def _frontmatter(path: Path) -> tuple[dict[str, Any] | None, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) != 3:
        return None, text
    try:
        value = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None, parts[2].lstrip("\n")
    return (value if isinstance(value, dict) else None), parts[2].lstrip("\n")


def _confined(relative: str) -> bool:
    path = Path(relative)
    return not path.is_absolute() and ".." not in path.parts


def _routed_paths(text: str) -> set[str]:
    return {match.group("path").rstrip(").,;:") for match in ROUTED_PATH.finditer(text)}


def _routing_graph(skill_dir: Path, roots: tuple[Path, ...]) -> tuple[set[str], list[tuple[Path, str]]]:
    reachable_references: set[str] = set()
    routes: list[tuple[Path, str]] = []
    pending = list(roots)
    visited: set[Path] = set()
    while pending:
        source = pending.pop()
        if source in visited or not source.is_file() or source.is_symlink():
            continue
        visited.add(source)
        text = source.read_text(encoding="utf-8")
        for relative in sorted(_routed_paths(text)):
            routes.append((source, relative))
            if not relative.startswith("references/") or not _confined(relative):
                continue
            target = skill_dir / relative
            if not target.is_file() or target.is_symlink():
                continue
            if relative not in reachable_references:
                reachable_references.add(relative)
                pending.append(target)
    return reachable_references, routes


def _resolved_inside(root: Path, target: Path) -> bool:
    try:
        target.resolve(strict=False).relative_to(root)
    except ValueError:
        return False
    return True


def audit_skill(
    skill_dir: Path,
    repository_root: Path | None = None,
    *,
    strict: bool = False,
) -> list[Finding]:
    skill_dir = skill_dir.resolve()
    repository_root = (repository_root or skill_dir.parent.parent).resolve()
    findings: list[Finding] = []

    try:
        skill_dir.relative_to(repository_root)
    except ValueError:
        findings.append(
            _finding(
                "error",
                "skill.path.unconfined",
                skill_dir,
                "skill directory must remain inside the declared repository root",
            )
        )
        return findings

    for name in ("SKILL.md", "STANDARD.md", "manifest.yaml"):
        path = skill_dir / name
        if not path.is_file():
            findings.append(
                _finding(
                    "error",
                    "skill.core.missing",
                    path,
                    f"required core file is missing: {name}",
                )
            )

    if any(f.code == "skill.core.missing" for f in findings):
        return findings

    skill_path = skill_dir / "SKILL.md"
    frontmatter, body = _frontmatter(skill_path)
    if frontmatter is None:
        findings.append(
            _finding(
                "error",
                "skill.frontmatter.invalid",
                skill_path,
                "SKILL.md needs YAML frontmatter",
            )
        )
    else:
        if set(frontmatter) != {"name", "description"}:
            findings.append(
                _finding(
                    "error",
                    "skill.frontmatter.portable",
                    skill_path,
                    "portable SKILL.md frontmatter must contain exactly name and description",
                )
            )
        frontmatter_name = frontmatter.get("name")
        if not isinstance(frontmatter_name, str) or not NAME.fullmatch(frontmatter_name) or len(frontmatter_name) > 64:
            findings.append(
                _finding(
                    "error",
                    "skill.name.invalid",
                    skill_path,
                    "name must be lowercase kebab-case and <=64 characters",
                )
            )
        elif frontmatter_name != skill_dir.name:
            findings.append(
                _finding(
                    "error",
                    "skill.name.directory-mismatch",
                    skill_path,
                    "frontmatter name must match the skill directory",
                )
            )
        description = frontmatter.get("description")
        if not isinstance(description, str) or not description.strip():
            findings.append(
                _finding(
                    "error",
                    "skill.description.missing",
                    skill_path,
                    "description must be non-empty",
                )
            )
        elif len(description) > 1024:
            findings.append(
                _finding(
                    "error",
                    "skill.description.too-long",
                    skill_path,
                    "description must be <=1024 characters",
                )
            )

    skill_text = skill_path.read_text(encoding="utf-8")
    if len(skill_text.splitlines()) > 90:
        findings.append(
            _finding(
                "error",
                "skill.context.skill-budget",
                skill_path,
                "SKILL.md exceeds the repository 90-line budget",
            )
        )
    if "STANDARD.md" not in body:
        findings.append(
            _finding(
                "error",
                "skill.routing.standard",
                skill_path,
                "SKILL.md must route normative decisions to STANDARD.md",
            )
        )

    manifest_path = skill_dir / "manifest.yaml"
    try:
        loaded_manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        findings.append(
            _finding(
                "error",
                "skill.manifest.invalid",
                manifest_path,
                f"manifest.yaml could not be parsed: {exc}",
            )
        )
        loaded_manifest = {}
    if not isinstance(loaded_manifest, dict):
        findings.append(
            _finding(
                "error",
                "skill.manifest.invalid",
                manifest_path,
                "manifest.yaml must contain a mapping",
            )
        )
        manifest: dict[str, Any] = {}
    else:
        manifest = loaded_manifest

    if manifest.get("name") != skill_dir.name:
        findings.append(
            _finding(
                "error",
                "skill.manifest.name",
                manifest_path,
                "manifest name must match the skill directory",
            )
        )
    if manifest.get("normative_entrypoint") != "STANDARD.md":
        findings.append(
            _finding(
                "error",
                "skill.manifest.standard",
                manifest_path,
                "normative_entrypoint must be STANDARD.md",
            )
        )

    required = manifest.get("required")
    required_names = {item for item in required if isinstance(item, str)} if isinstance(required, list) else set()
    if not isinstance(required, list) or not {"SKILL.md", "STANDARD.md"}.issubset(required_names):
        findings.append(
            _finding(
                "error",
                "skill.manifest.required",
                manifest_path,
                "required must include SKILL.md and STANDARD.md",
            )
        )
        required = []
    for relative in required:
        if not isinstance(relative, str) or not _confined(relative):
            findings.append(
                _finding(
                    "error",
                    "skill.resource.unconfined",
                    manifest_path,
                    f"invalid required resource: {relative!r}",
                )
            )
            continue
        resource = skill_dir / relative
        if not _resolved_inside(skill_dir, resource):
            findings.append(
                _finding(
                    "error",
                    "skill.resource.unconfined",
                    resource,
                    "declared runtime resource resolves outside the skill directory",
                )
            )
        elif resource.is_symlink():
            findings.append(
                _finding(
                    "error",
                    "skill.resource.symlink",
                    resource,
                    "declared runtime resources must not be symlinks",
                )
            )
        elif not resource.is_file():
            findings.append(
                _finding(
                    "error",
                    "skill.resource.missing",
                    resource,
                    "declared required resource does not exist",
                )
            )

    categories = manifest.get("categories")
    category_set = {item for item in categories if isinstance(item, str)} if isinstance(categories, list) else set()
    if "core" not in category_set or not category_set <= {"core", *ALLOWED_DIRECTORIES}:
        findings.append(
            _finding(
                "error",
                "skill.categories.invalid",
                manifest_path,
                "categories must contain core and only supported runtime categories",
            )
        )

    actual_directories = {path.name for path in skill_dir.iterdir() if path.is_dir() and path.name != "__pycache__"}
    undeclared = actual_directories - category_set
    if undeclared:
        findings.append(
            _finding(
                "error",
                "skill.categories.undeclared",
                skill_dir,
                f"runtime directories are not declared in manifest categories: {sorted(undeclared)}",
            )
        )

    for name in FORBIDDEN_TOP_LEVEL:
        if (skill_dir / name).exists():
            findings.append(
                _finding(
                    "error",
                    "skill.package.pollution",
                    skill_dir / name,
                    "developer artifact does not belong in the runtime skill package",
                )
            )

    standard_path = skill_dir / "STANDARD.md"
    reachable_references, routes = _routing_graph(skill_dir, (skill_path, standard_path))
    for source, relative in routes:
        if not _confined(relative):
            findings.append(
                _finding(
                    "error",
                    "skill.routing.unconfined",
                    source,
                    f"unconfined routed path: {relative}",
                )
            )
            continue
        resource = skill_dir / relative
        if not _resolved_inside(skill_dir, resource):
            findings.append(
                _finding(
                    "error",
                    "skill.routing.unconfined",
                    source,
                    f"routed resource resolves outside the skill directory: {relative}",
                )
            )
        elif resource.is_symlink():
            findings.append(
                _finding(
                    "error",
                    "skill.routing.symlink",
                    resource,
                    "routed runtime resources must not be symlinks",
                )
            )
        elif not resource.exists():
            findings.append(
                _finding(
                    "error",
                    "skill.routing.missing",
                    source,
                    f"routed resource does not exist: {relative}",
                )
            )

    reference_dir = skill_dir / "references"
    if reference_dir.is_dir():
        for reference in sorted(reference_dir.rglob("*.md")):
            relative = reference.relative_to(skill_dir).as_posix()
            if relative not in reachable_references:
                severity = "error" if strict else "warning"
                findings.append(
                    _finding(
                        severity,
                        "skill.routing.orphan-reference",
                        reference,
                        "reference is not reachable from SKILL.md or STANDARD.md routing",
                    )
                )

    dependencies = manifest.get("dependencies")
    if isinstance(dependencies, dict):
        skills = dependencies.get("skills")
        tools = dependencies.get("tools")
        if not isinstance(skills, list):
            findings.append(
                _finding(
                    "error",
                    "skill.dependencies.skills",
                    manifest_path,
                    "dependencies.skills must be a list",
                )
            )
        if not isinstance(tools, list):
            findings.append(
                _finding(
                    "error",
                    "skill.dependencies.tools",
                    manifest_path,
                    "dependencies.tools must be a list",
                )
            )
    else:
        findings.append(
            _finding(
                "error",
                "skill.dependencies.invalid",
                manifest_path,
                "dependencies must be a mapping",
            )
        )

    return findings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit one ai-skills runtime package.")
    parser.add_argument("skill_dir", type=Path)
    parser.add_argument("--repository-root", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    findings = audit_skill(args.skill_dir, args.repository_root, strict=args.strict)
    if args.as_json:
        print(json.dumps([asdict(f) for f in findings], indent=2, sort_keys=True))
    else:
        for finding in findings:
            print(f"{finding.severity.upper()} {finding.code} {finding.path}: {finding.message}")
    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
