from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER = re.compile(
    r"^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)"
    r"(?:-(?:0|[1-9]\\d*|\\d*[A-Za-z-][0-9A-Za-z-]*)(?:\\.(?:0|[1-9]\\d*|\\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?$"
)
SUPPORTED_MATURITY = {"experimental", "release-candidate", "stable", "deprecated"}
ALLOWED_OPERATING_SYSTEMS = {"linux", "macos", "windows"}
ALLOWED_DIRECTORIES = {"references", "templates", "examples", "schemas", "tools", "locks"}
FORBIDDEN_TOP_LEVEL = {
    "evals",
    "reports",
    "CHANGELOG.md",
    "README.md",
    "VERSION",
    "MANIFEST.json",
}
ROUTED_PATH = re.compile(
    r"(?<![A-Za-z0-9_./:-])"
    r"(?P<path>(?:(?:\.\./)+|\./|/)?"
    r"(?:STANDARD\.md|(?:references|templates|examples|schemas|tools|locks)/"
    r"[A-Za-z0-9_.\-/]*[A-Za-z0-9_-]\.[A-Za-z0-9][A-Za-z0-9._-]*))"
)


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    message: str


def _finding(severity: str, code: str, path: Path, message: str) -> Finding:
    return Finding(severity=severity, code=code, path=path.as_posix(), message=message)


def _read_text(path: Path) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeError) as exc:
        return None, str(exc)


def _frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
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


def _without_fenced_blocks(text: str) -> str:
    kept: list[str] = []
    fence_char: str | None = None
    fence_length = 0
    for line in text.splitlines():
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        marker_char = stripped[:1]
        marker_length = 0
        if indent <= 3 and marker_char in {"`", "~"}:
            marker_length = len(stripped) - len(stripped.lstrip(marker_char))
        if fence_char is None:
            if marker_length >= 3:
                fence_char = marker_char
                fence_length = marker_length
                kept.append("")
            else:
                kept.append(line)
            continue
        if marker_char == fence_char and marker_length >= fence_length:
            fence_char = None
            fence_length = 0
        kept.append("")
    return "\n".join(kept)


def _routed_paths(text: str) -> set[str]:
    prose = _without_fenced_blocks(text)
    return {match.group("path").rstrip(").,;:") for match in ROUTED_PATH.finditer(prose)}


def _routing_graph(
    skill_dir: Path,
    roots: tuple[Path, ...],
) -> tuple[set[str], list[tuple[Path, str]], list[tuple[Path, str]]]:
    reachable_references: set[str] = set()
    routes: list[tuple[Path, str]] = []
    unreadable: list[tuple[Path, str]] = []
    pending = list(roots)
    visited: set[Path] = set()
    while pending:
        source = pending.pop()
        if source in visited or not source.is_file() or source.is_symlink():
            continue
        visited.add(source)
        text, error = _read_text(source)
        if text is None:
            unreadable.append((source, error or "unknown read failure"))
            continue
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
    return reachable_references, routes, unreadable


def _resolved_inside(root: Path, target: Path) -> bool:
    try:
        target.resolve(strict=False).relative_to(root)
    except ValueError:
        return False
    return True


def _strict_manifest_findings(
    manifest: dict[str, Any],
    manifest_path: Path,
) -> list[Finding]:
    findings: list[Finding] = []

    def invalid(message: str) -> None:
        findings.append(_finding("error", "skill.manifest.contract", manifest_path, message))

    if manifest.get("schema_version") != 1:
        invalid("schema_version must be 1")
    version = manifest.get("version")
    if not isinstance(version, str) or SEMVER.fullmatch(version) is None:
        invalid("version must be a canonical SemVer 2.0.0 string")
    if manifest.get("maturity") not in SUPPORTED_MATURITY:
        invalid(f"maturity must be one of {sorted(SUPPORTED_MATURITY)}")
    if manifest.get("skill_format") != "ai-skills/v1":
        invalid("skill_format must be ai-skills/v1")

    compatibility = manifest.get("compatibility")
    if not isinstance(compatibility, dict):
        invalid("compatibility must be a mapping")
    else:
        if compatibility.get("agent_contract") != "tool-capable-instruction-agent":
            invalid("compatibility.agent_contract must be tool-capable-instruction-agent")

        operating_systems = compatibility.get("operating_systems")
        if (
            not isinstance(operating_systems, list)
            or not operating_systems
            or not all(isinstance(item, str) for item in operating_systems)
            or not set(operating_systems) <= ALLOWED_OPERATING_SYSTEMS
        ):
            invalid("compatibility.operating_systems must be a non-empty supported OS list")
            operating_systems = []

        evidence_lanes = compatibility.get("evidence_lanes")
        if (
            not isinstance(evidence_lanes, list)
            or not evidence_lanes
            or not all(isinstance(item, str) and item for item in evidence_lanes)
        ):
            invalid("compatibility.evidence_lanes must be a non-empty string list")
            evidence_lanes = []

        tested = compatibility.get("tested_combinations")
        tested_operating_systems: set[str] = set()
        tested_runtimes: set[str] = set()
        if not isinstance(tested, list) or not tested:
            invalid("compatibility.tested_combinations must be a non-empty list")
        else:
            for index, combination in enumerate(tested):
                if not isinstance(combination, dict):
                    invalid(f"compatibility.tested_combinations[{index}] must be a mapping")
                    continue
                fields = {
                    key: combination.get(key)
                    for key in ("operating_system", "architecture", "runtime", "version", "lane")
                }
                if not all(isinstance(value, str) and value for value in fields.values()):
                    invalid(f"compatibility.tested_combinations[{index}] has missing fields")
                    continue
                operating_system = str(fields["operating_system"])
                lane = str(fields["lane"])
                runtime = str(fields["runtime"])
                if operating_system not in ALLOWED_OPERATING_SYSTEMS:
                    invalid(f"compatibility.tested_combinations[{index}] has unsupported operating_system")
                if evidence_lanes and lane not in evidence_lanes:
                    invalid(f"compatibility.tested_combinations[{index}].lane is not declared")
                tested_operating_systems.add(operating_system)
                tested_runtimes.add(runtime)

        if operating_systems and tested_operating_systems != set(operating_systems):
            invalid("tested combinations must cover exactly the declared operating_systems")

        runtimes = compatibility.get("runtimes") or {}
        if not isinstance(runtimes, dict):
            invalid("compatibility.runtimes must be a mapping when present")
        else:
            for runtime, specifier in runtimes.items():
                if not isinstance(runtime, str) or not runtime or not isinstance(specifier, str) or not specifier:
                    invalid("compatibility.runtimes entries must be non-empty strings")
                elif tested_runtimes and runtime not in tested_runtimes:
                    invalid(f"compatibility.runtimes declares untested runtime: {runtime}")

    adoption = manifest.get("adoption")
    if not isinstance(adoption, dict):
        invalid("adoption must be a mapping")
    else:
        if adoption.get("extension") not in {"generic", "mcp"}:
            invalid("adoption.extension must be generic or mcp")
        for field in ("template", "validator", "rule_catalog", "rule_map"):
            value = adoption.get(field)
            if not isinstance(value, str) or not value or not _confined(value):
                invalid(f"adoption.{field} must be a confined relative path")

    deprecation = manifest.get("deprecation")
    if not isinstance(deprecation, dict):
        invalid("deprecation must be a mapping")
    else:
        if deprecation.get("policy") != "semantic-versioning":
            invalid("deprecation.policy must be semantic-versioning")
        notice = deprecation.get("minimum_notice")
        if not isinstance(notice, str) or not notice.strip():
            invalid("deprecation.minimum_notice must be non-empty")

    return findings


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
        if path.is_symlink() or not _resolved_inside(skill_dir, path):
            findings.append(
                _finding(
                    "error",
                    "skill.core.unconfined",
                    path,
                    f"required core file must be a regular in-package file: {name}",
                )
            )
        elif not path.is_file():
            findings.append(
                _finding(
                    "error",
                    "skill.core.missing",
                    path,
                    f"required core file is missing: {name}",
                )
            )

    if any(f.code in {"skill.core.missing", "skill.core.unconfined"} for f in findings):
        return findings

    skill_path = skill_dir / "SKILL.md"
    skill_text, skill_read_error = _read_text(skill_path)
    if skill_text is None:
        findings.append(
            _finding(
                "error",
                "skill.file.unreadable",
                skill_path,
                f"SKILL.md could not be read as UTF-8 text: {skill_read_error or 'unknown read failure'}",
            )
        )
        return findings

    frontmatter, body = _frontmatter(skill_text)
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

    if strict:
        findings.extend(_strict_manifest_findings(manifest, manifest_path))

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

    top_level = [path for path in skill_dir.iterdir() if path.name != "__pycache__"]
    actual_directories = {path.name for path in top_level if path.is_dir()}
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

    for category in sorted(category_set - {"core"}):
        directory = skill_dir / category
        if directory.is_symlink():
            continue
        severity = "error" if strict else "warning"
        if not directory.is_dir():
            findings.append(
                _finding(
                    severity,
                    "skill.categories.missing",
                    directory,
                    f"declared runtime category has no directory: {category}",
                )
            )
            continue
        try:
            has_content = any(child.name != "__pycache__" for child in directory.iterdir())
        except OSError as exc:
            findings.append(
                _finding(
                    "error",
                    "skill.file.unreadable",
                    directory,
                    f"declared runtime category could not be inspected: {exc}",
                )
            )
            continue
        if not has_content:
            findings.append(
                _finding(
                    severity,
                    "skill.categories.empty",
                    directory,
                    f"declared runtime category is empty: {category}",
                )
            )

    for resource in top_level:
        if resource.is_symlink():
            findings.append(
                _finding(
                    "error",
                    "skill.package.symlink",
                    resource,
                    "published skill packages must not contain symlinked resources",
                )
            )

    allowed_top_level_files = {"SKILL.md", "STANDARD.md", "manifest.yaml"}
    for resource in top_level:
        if resource.is_file() and resource.name not in allowed_top_level_files:
            severity = "error" if strict else "warning"
            findings.append(
                _finding(
                    severity,
                    "skill.package.unexpected-file",
                    resource,
                    "top-level runtime files must use a declared resource directory",
                )
            )

    for resource in skill_dir.rglob("*"):
        if resource.name == "__pycache__":
            continue
        if resource.is_symlink():
            if resource.parent != skill_dir:
                findings.append(
                    _finding(
                        "error",
                        "skill.package.symlink",
                        resource,
                        "published skill packages must not contain symlinked resources",
                    )
                )
            continue
        if resource.name in FORBIDDEN_TOP_LEVEL:
            findings.append(
                _finding(
                    "error",
                    "skill.package.pollution",
                    resource,
                    "developer artifact does not belong in the runtime skill package",
                )
            )

    standard_path = skill_dir / "STANDARD.md"
    reachable_references, routes, unreadable_routes = _routing_graph(skill_dir, (skill_path, standard_path))
    for source, error in unreadable_routes:
        findings.append(
            _finding(
                "error",
                "skill.file.unreadable",
                source,
                f"routed Markdown resource could not be read as UTF-8 text: {error}",
            )
        )
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
        elif not resource.is_file():
            code = "skill.routing.missing" if not resource.exists() else "skill.routing.not-file"
            message = (
                f"routed resource does not exist: {relative}"
                if code == "skill.routing.missing"
                else f"routed resource must be a regular file: {relative}"
            )
            findings.append(
                _finding(
                    "error",
                    code,
                    source,
                    message,
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
