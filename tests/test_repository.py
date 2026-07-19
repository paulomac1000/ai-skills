"""Repository architecture and recovered-knowledge contract tests."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SKILLS = {
    "afds-doc-writer",
    "ci-cd-architect",
    "mcp-server-architect",
    "mcp-server-consumer",
}
ALLOWED_CATEGORIES = {"core", "references", "templates", "examples", "tools"}
IGNORED_PARTS = {".git", ".venv", ".pytest_cache", "__pycache__", ".ruff_cache"}
POLISH_MARKERS = re.compile("[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")
PROJECT_SPECIFIC_TERMS = {
    "ha-" + "mcp-readonly",
    "kontomierz-" + "mcp",
    "openwrt-" + "mcp",
    "mikrus-" + "mcp",
    "local-home-devices-" + "mcp",
    "notebooklm-" + "mcp",
}
MCP_PARITY_HEADINGS = {
    "## Lifecycle ownership",
    "## Transport parity",
    "## Manifest coverage",
    "## Concurrency enforcement",
    "## Boundary sanitization",
    "## SDK compatibility",
    "## Verification",
}


def load_validator():
    path = ROOT / "skills/afds-doc-writer/validate.py"
    spec = importlib.util.spec_from_file_location("afds_validator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source_files(root: Path = ROOT) -> list[Path]:
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and not IGNORED_PARTS.intersection(path.parts)
    ]


def markdown_section(text: str, heading: str) -> str:
    """Return one second-level Markdown section body."""
    lines = text.splitlines()
    start = lines.index(heading) + 1
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end]).strip()


def test_skill_manifests_govern_extensible_resource_categories() -> None:
    skill_root = ROOT / "skills"
    discovered = {path.name for path in skill_root.iterdir() if path.is_dir()}
    assert discovered == EXPECTED_SKILLS
    for name in discovered:
        directory = skill_root / name
        manifest = yaml.safe_load((directory / "manifest.yaml").read_text(encoding="utf-8"))
        assert manifest["name"] == name
        required = manifest.get("required")
        categories = set(manifest.get("categories") or [])
        assert isinstance(required, list) and {"SKILL.md", "STANDARD.md"}.issubset(required)
        assert categories and categories.issubset(ALLOWED_CATEGORIES)
        for relative in required:
            assert (directory / relative).is_file(), (name, relative)
        actual_directories = {
            path.name
            for path in directory.iterdir()
            if path.is_dir() and path.name != "__pycache__"
        }
        assert actual_directories.issubset(categories), (name, actual_directories, categories)


def test_repository_allows_intentional_knowledge_growth() -> None:
    assert (ROOT / "RECOVERY_AUDIT.md").exists()
    assert any((ROOT / "skills" / name / "references").exists() for name in EXPECTED_SKILLS)
    assert (ROOT / "skills/mcp-server-architect/examples").exists()
    assert (ROOT / "skills/mcp-server-architect/tools/generate_python_server.py").is_file()
    assert len(source_files()) > 40


def test_all_governed_markdown_validates() -> None:
    validator = load_validator()
    paths, findings = validator.collect_files([ROOT / "RECOVERY_AUDIT.md", ROOT / "skills"])
    findings.extend(finding for path in paths for finding in validator.validate(path))
    assert findings == []


def test_skill_frontmatter_remains_portable() -> None:
    for name in EXPECTED_SKILLS:
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = yaml.safe_load(text.split("---", 2)[1])
        assert set(frontmatter) == {"name", "description"}
        assert frontmatter["name"] == name
        assert isinstance(frontmatter["description"], str) and frontmatter["description"].strip()
        assert len(text.splitlines()) <= 90


def test_release_contains_no_private_project_or_polish_examples() -> None:
    suffixes = {".md", ".py", ".yml", ".yaml", ".template", ".toml", ".txt", ".example"}
    for path in source_files():
        if path.suffix.lower() not in suffixes:
            continue
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        assert not any(term in lowered for term in PROJECT_SPECIFIC_TERMS), path
        assert not POLISH_MARKERS.search(text), path


def test_recovery_audit_covers_removed_operational_domains() -> None:
    text = (ROOT / "RECOVERY_AUDIT.md").read_text(encoding="utf-8").lower()
    required_topics = {
        "fastmcp",
        ".net",
        "cancellation",
        "semgrep",
        "dependabot",
        "coverage",
        "pagination",
        "partial execution",
        "pre-commit",
        "lifecycle",
        "conflict",
        "same image",
        "manifest",
        "concurrency",
        "transport parity",
        "compatibility",
        "generator",
        "real mcp client",
        "filesystem",
        "artifact",
        "task registries",
        "browser profiles",
        "ui drift",
        "embedded hosting",
    }
    assert all(topic in text for topic in required_topics)


def test_template_action_pins_have_an_update_path() -> None:
    config = __import__("json").loads((ROOT / "renovate.json").read_text(encoding="utf-8"))
    managers = config.get("customManagers") or []
    assert any(
        manager.get("customType") == "regex"
        and any("ci-cd-architect" in pattern for pattern in manager.get("managerFilePatterns", []))
        and "currentDigest" in " ".join(manager.get("matchStrings", []))
        for manager in managers
    )


def test_python_and_dotnet_profiles_cover_the_same_core_invariants() -> None:
    root = ROOT / "skills/mcp-server-architect/references"
    profiles = {
        "python": (root / "python-fastmcp.md").read_text(encoding="utf-8"),
        "dotnet": (root / "dotnet-mcp.md").read_text(encoding="utf-8"),
    }
    for name, text in profiles.items():
        missing = MCP_PARITY_HEADINGS - set(text.splitlines())
        assert not missing, (name, missing)
        for heading in MCP_PARITY_HEADINGS:
            body = markdown_section(text, heading)
            assert len(body) >= 120, (name, heading, body)

    required_platform_contracts = {
        "python": {
            "FastMCP",
            "asyncio",
            "contextvars",
            "event loop",
            "compatibility adapter",
            "Streamable HTTP",
        },
        "dotnet": {
            "ModelContextProtocol",
            "Generic Host",
            "CancellationToken",
            "Activity",
            "WithStdioServerTransport",
            "WithHttpTransport",
            "MapMcp",
        },
    }
    for name, required in required_platform_contracts.items():
        missing = required - set(token for token in required if token in profiles[name])
        assert not missing, (name, missing)

    standard = (ROOT / "skills/mcp-server-architect/STANDARD.md").read_text(encoding="utf-8")
    assert "capability-manifests-and-versioning.md" in standard
    assert "transport-lifecycle-and-conformance.md" in standard
    assert "runtime-boundaries-and-artifacts.md" in standard
    assert "Generated project acceptance" in standard


def test_mcp_examples_exercise_native_python_and_dotnet_hosting_surfaces() -> None:
    examples = ROOT / "skills/mcp-server-architect/examples"
    python_example = (examples / "python/server_composition.py.example").read_text(encoding="utf-8")
    stdio_example = (examples / "dotnet/StdioProgram.cs.example").read_text(encoding="utf-8")
    http_example = (examples / "dotnet/HttpProgram.cs.example").read_text(encoding="utf-8")
    tool_example = (examples / "dotnet/InventoryTools.cs.example").read_text(encoding="utf-8")

    for token in (
        "from mcp.server.fastmcp import Context, FastMCP",
        "lifespan",
        "stateless_http=True",
        "max_request_body_size=1_048_576",
        "@mcp.tool()",
    ):
        assert token in python_example
    for token in ("AddMcpServer", "WithStdioServerTransport", "WithTools<InventoryTools>"):
        assert token in stdio_example
    for token in ("WithHttpTransport", "options.Stateless = true", "MapMcp"):
        assert token in http_example
    for token in ("[McpServerToolType]", "[McpServerTool", "CancellationToken"):
        assert token in tool_example


def test_legacy_standard_paths_remain_resolvable_deprecation_stubs() -> None:
    entrypoints = {
        ROOT / "skills/mcp-server-architect/mcp-server-standards.md": "STANDARD.md",
        ROOT / "skills/afds-doc-writer/docs_standards.md": "STANDARD.md",
    }
    for path, target in entrypoints.items():
        text = path.read_text(encoding="utf-8")
        assert "status: deprecated" in text
        assert target in text
        assert len(text.splitlines()) < 50
