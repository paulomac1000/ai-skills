"""Repository contracts for the AGENTS.md architect skill."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/agents-md-architect"
VALIDATOR_PATH = SKILL / "tools/validate_agents_md.py"


def load_validator() -> Any:
    spec = importlib.util.spec_from_file_location("agents_md_standard_validator", VALIDATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def render(template: str, replacements: dict[str, str]) -> str:
    result = template
    for key, value in replacements.items():
        result = result.replace(key, value)
    assert "REPLACE_WITH" not in result
    assert "REPLACE_OR_REMOVE" not in result
    return result


def prepare_repository(tmp_path: Path) -> None:
    for relative in (
        "docs/platforms.md",
        "docs/entrypoint.md",
        "docs/focused.md",
        "docs/normative.md",
        "src/service.py",
        "tests/test_service.py",
        "packages/api/docs/local.md",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Contract\n", encoding="utf-8")
    for relative in ("scripts/setup.py", "scripts/ci.py", "packages/api/scripts/ci.py"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("print('ok')\n", encoding="utf-8")


def root_replacements() -> dict[str, str]:
    return {
        "REPLACE_WITH_PLATFORM_REFERENCE": "docs/platforms.md",
        "REPLACE_WITH_PRIMARY_SYSTEM_OUTCOME": "Maintain the public service contract",
        "REPLACE_WITH_SCOPE_BOUNDARY": "Do not publish or deploy without explicit scope",
        "REPLACE_OR_REMOVE_WITH_OTHER_REAL_MODE": "Release: bind evidence to the exact revision",
        "REPLACE_WITH_CANONICAL_ENTRYPOINT": "docs/entrypoint.md",
        "REPLACE_WITH_PURPOSE": "repository orientation",
        "REPLACE_WITH_AREA": "service architecture",
        "REPLACE_WITH_REFERENCE": "docs/focused.md",
        "REPLACE_WITH_DECISION_OWNED": "dependency direction",
        "REPLACE_WITH_NORMATIVE_OWNER": "docs/normative.md",
        "REPLACE_WITH_IMPLEMENTATION_OWNER": "src/service.py",
        "REPLACE_WITH_TEST_OWNER": "tests/test_service.py",
        "REPLACE_WITH_NON_OBVIOUS_DEPENDENCY_OR_GENERATED_FILE_RULE": "Generated files must not be edited directly",
        "REPLACE_WITH_PROTECTED_ASSET_AND_ALLOWED_COMPONENT": "Secrets remain outside tracked files",
        "REPLACE_WITH_FORBIDDEN_FLOW_OR_DESTRUCTIVE_ACTION": "Destructive operations require trusted approval",
        "REPLACE_WITH_SETUP_COMMAND": "python scripts/setup.py",
        "REPLACE_WITH_FOCUSED_COMMAND": "python -m pytest tests/test_service.py",
        "REPLACE_WITH_FULL_GATE": "python scripts/ci.py",
    }


def nested_replacements() -> dict[str, str]:
    return {
        "REPLACE_WITH_SUBTREE": "packages/api",
        "REPLACE_WITH_LOCAL_DIFFERENCE": "The API package owns HTTP adapters",
        "REPLACE_WITH_LOCAL_GENERATOR_OR_NONE": "Generated clients remain generator-owned",
        "REPLACE_WITH_LOCAL_BOUNDARY_OR_INHERITED": "Repository safety boundaries remain inherited",
        "REPLACE_WITH_LOCAL_FOCUSED_COMMAND": "python -m pytest packages/api/tests",
        "REPLACE_WITH_LOCAL_COMPLETION_COMMAND": "python packages/api/scripts/ci.py",
        "REPLACE_WITH_AREA": "API package architecture",
        "REPLACE_WITH_REFERENCE": "docs/local.md",
        "REPLACE_WITH_PURPOSE": "package ownership",
    }


def test_standard_covers_discovered_instruction_failures() -> None:
    text = (SKILL / "STANDARD.md").read_text(encoding="utf-8").casefold()
    required = {
        "scope and precedence",
        "operating modes and profiles",
        "canonical ownership and architecture boundaries",
        "safety and data boundaries",
        "context economy and routing",
        "nested instructions",
        "anti-patterns and drift",
        "definition of done",
        "keyword matching",
        "local pass does not guarantee remote ci",
        "exact revision",
        "utf-8 bytes",
        "symlink",
        "bounded structural and lexical checks",
    }
    assert all(token in text for token in required)


def test_platform_reference_and_conditional_mcp_dependency_are_published() -> None:
    manifest = yaml.safe_load((SKILL / "manifest.yaml").read_text(encoding="utf-8"))
    platform = "references/instruction-precedence-and-platforms.md"
    assert platform in manifest["required"]
    assert manifest["conditional_dependencies"]["profiles"]["mcp-server"]["skills"] == [
        "mcp-server-architect"
    ]
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    standard = (SKILL / "STANDARD.md").read_text(encoding="utf-8")
    assert platform in skill
    assert platform in standard


def test_rendered_application_template_passes_validator(tmp_path: Path) -> None:
    prepare_repository(tmp_path)
    template = (SKILL / "templates/AGENTS.md.template").read_text(encoding="utf-8")
    path = tmp_path / "AGENTS.md"
    path.write_text(render(template, root_replacements()), encoding="utf-8")
    validator = load_validator()
    assert validator.validate_path(path, "application", tmp_path) == []


def test_rendered_root_and_nested_templates_pass_together(tmp_path: Path) -> None:
    prepare_repository(tmp_path)
    root_template = (SKILL / "templates/AGENTS.md.template").read_text(encoding="utf-8")
    nested_template = (SKILL / "templates/nested-AGENTS.md.template").read_text(encoding="utf-8")
    root = tmp_path / "AGENTS.md"
    nested = tmp_path / "packages/api/AGENTS.md"
    nested.parent.mkdir(parents=True, exist_ok=True)
    root.write_text(render(root_template, root_replacements()), encoding="utf-8")
    nested.write_text(render(nested_template, nested_replacements()), encoding="utf-8")
    validator = load_validator()
    assert validator.validate_many([root, nested], "monorepo", tmp_path) == []


def test_skill_routes_detail_to_focused_references() -> None:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 90
    for reference in (
        "references/repository-discovery.md",
        "references/profiles-and-routing.md",
        "references/anti-patterns-and-drift.md",
        "references/lifecycle-and-evidence.md",
        "references/instruction-precedence-and-platforms.md",
    ):
        assert reference in text or (SKILL / reference).is_file()
    for tool in ("discover_repository.py", "audit_agents_md.py", "validate_agents_md.py"):
        assert tool in text
