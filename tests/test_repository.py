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
    "agents-md-architect",
    "ci-cd-architect",
    "mcp-server-architect",
    "mcp-server-consumer",
}
ALLOWED_CATEGORIES = {"core", "references", "templates", "examples", "tools", "locks"}
IGNORED_PARTS = {".git", ".venv", ".pytest_cache", "__pycache__", ".ruff_cache"}
POLISH_MARKERS = re.compile(
    r"[\u0105\u0107\u0119\u0142\u0144\u00f3\u015b\u017a\u017c"
    r"\u0104\u0106\u0118\u0141\u0143\u00d3\u015a\u0179\u017b]"
)
LOCALIZED_LANGUAGE_CONTRACT_FILES = {
    Path("skills/agents-md-architect/tools/agents_md_types.py"),
    Path("skills/agents-md-architect/tools/agents_md_parse.py"),
    Path("skills/agents-md-architect/tools/agents_md_completion_evidence.py"),
    Path("tests/test_agents_md_composition_and_language.py"),
}
PROJECT_SPECIFIC_EVIDENCE_FILES = {Path("contracts/consumer-canaries.yaml")}
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
    return [path for path in root.rglob("*") if path.is_file() and not IGNORED_PARTS.intersection(path.parts)]


def markdown_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = lines.index(heading) + 1
    end = next((index for index in range(start, len(lines)) if lines[index].startswith("## ")), len(lines))
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
        actual_directories = {path.name for path in directory.iterdir() if path.is_dir() and path.name != "__pycache__"}
        assert actual_directories.issubset(categories), (name, actual_directories, categories)


def test_repository_allows_intentional_knowledge_growth() -> None:
    assert (ROOT / "RECOVERY_AUDIT.md").exists()
    assert any((ROOT / "skills" / name / "references").exists() for name in EXPECTED_SKILLS)
    assert (ROOT / "skills/mcp-server-architect/examples").exists()
    assert (ROOT / "skills/mcp-server-architect/tools/generate_python_server.py").is_file()
    assert (ROOT / "skills/mcp-server-architect/tools/generate_dotnet_server.py").is_file()
    assert (ROOT / "skills/mcp-server-architect/tools/dotnet-template").is_dir()
    assert len(source_files()) > 40


def test_all_governed_markdown_validates() -> None:
    validator = load_validator()
    paths, findings = validator.collect_files([ROOT / "RECOVERY_AUDIT.md", ROOT / "contracts", ROOT / "skills"])
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


def test_release_contains_no_private_project_or_unscoped_polish_examples() -> None:
    suffixes = {".md", ".py", ".cs", ".csproj", ".yml", ".yaml", ".template", ".toml", ".txt", ".example"}
    localized_files_seen: set[Path] = set()
    for path in source_files():
        if path.suffix.lower() not in suffixes:
            continue
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        relative = path.relative_to(ROOT)
        if relative not in PROJECT_SPECIFIC_EVIDENCE_FILES:
            assert not any(term in lowered for term in PROJECT_SPECIFIC_TERMS), path
        if POLISH_MARKERS.search(text):
            assert relative in LOCALIZED_LANGUAGE_CONTRACT_FILES, path
            localized_files_seen.add(relative)
    assert localized_files_seen == LOCALIZED_LANGUAGE_CONTRACT_FILES


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
        "legacy http+sse",
        "structured content",
    }
    missing = sorted(topic for topic in required_topics if topic not in text)
    assert missing == []
