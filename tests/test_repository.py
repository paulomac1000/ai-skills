"""Repository-level release contract tests."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SKILLS = {
    "afds-doc-writer",
    "ci-cd-architect",
    "mcp-server-architect",
    "mcp-server-consumer",
    "pre-commit-architect",
}
IGNORED_PARTS = {".git", ".venv", ".pytest_cache", "__pycache__", ".ruff_cache"}
EXPECTED_LAYOUT = {
    "afds-doc-writer": {"SKILL.md", "STANDARD.md", "validate.py"},
    "ci-cd-architect": {
        "SKILL.md",
        "STANDARD.md",
        "templates/ci.yml.template",
        "templates/docs-validation.yml.template",
        "templates/dotnet-ci.yml.template",
        "templates/publish.yml.template",
    },
    "mcp-server-architect": {"SKILL.md", "STANDARD.md"},
    "mcp-server-consumer": {
        "SKILL.md",
        "STANDARD.md",
        "tools/__init__.py",
        "tools/decision_engine.py",
    },
    "pre-commit-architect": {"SKILL.md", "STANDARD.md"},
}
PROJECT_SPECIFIC_TERMS = {
    "ha-" + "mcp-readonly",
    "kontomierz-" + "mcp",
    "openwrt-" + "mcp",
    "mikrus-" + "mcp",
    "local-home-devices-" + "mcp",
}
POLISH_MARKERS = re.compile("[\u0105\u0107\u0119\u0142\u0144\u00f3\u015b\u017a\u017c\u0104\u0106\u0118\u0141\u0143\u00d3\u015a\u0179\u017b]")


def load_validator():
    """Load the standalone validator without making skills a Python package."""
    path = ROOT / "skills/afds-doc-writer/validate.py"
    spec = importlib.util.spec_from_file_location("afds_validator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source_files() -> list[Path]:
    """Return release files while excluding local runtime artifacts."""
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and not IGNORED_PARTS.intersection(path.parts)
    ]


def test_release_structure_is_compact_and_intentional() -> None:
    """Reject development-stage artifacts and accidental repository growth."""
    files = source_files()
    assert len(files) <= 40
    assert not any("matrix" in path.name.lower() for path in files)
    assert (ROOT / "CHANGELOG.md").exists()
    assert not (ROOT / "decisions").exists()
    assert not (ROOT / "examples").exists()


def test_every_discovered_skill_is_governed() -> None:
    """Ensure newly added skill directories cannot bypass release checks."""
    skill_root = ROOT / "skills"
    discovered = {
        path.name
        for path in skill_root.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }
    assert discovered == EXPECTED_SKILLS

    for name in discovered:
        directory = skill_root / name
        actual = {
            path.relative_to(directory).as_posix()
            for path in directory.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        assert actual == EXPECTED_LAYOUT[name]


def test_all_standards_validate() -> None:
    """Validate every standard discovered from the filesystem."""
    validator = load_validator()
    findings = []
    for directory in sorted((ROOT / "skills").iterdir()):
        if directory.is_dir() and directory.name != "__pycache__":
            findings.extend(validator.validate(directory / "STANDARD.md"))
    assert findings == []


def test_skill_frontmatter_is_minimal_and_descriptive() -> None:
    """Keep discovery metadata portable across agent runtimes."""
    for directory in sorted((ROOT / "skills").iterdir()):
        if not directory.is_dir() or directory.name == "__pycache__":
            continue
        text = (directory / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        keys = {
            line.split(":", 1)[0].strip()
            for line in frontmatter.splitlines()
            if ":" in line
        }
        assert keys == {"name", "description"}
        assert len(text.splitlines()) <= 90


def test_release_contains_no_project_specific_or_polish_text() -> None:
    """Keep the public collection project-independent and English-only."""
    checked_suffixes = {".md", ".py", ".yml", ".yaml", ".j2", ".template", ".toml", ".txt"}
    for path in source_files():
        if path.suffix.lower() not in checked_suffixes:
            continue
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        assert not any(term in lowered for term in PROJECT_SPECIFIC_TERMS)
        assert not POLISH_MARKERS.search(text)
        assert ("schema_" + "version") not in text
        assert ("standard_" + "version") not in text


def test_changelog_preserves_history_with_one_new_release_change() -> None:
    """Keep prior milestones while limiting the new release entry to one change."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = text.split("## 1.0.0 - 2026-07-17", 1)[1].split("\n## ", 1)[0]
    assert latest.count("\n- ") == 1
    assert text.count("\n## ") >= 2
    assert "2026-06-06" in text
    assert "2026-05-13" in text


def test_repository_local_virtual_environment_is_ignored(tmp_path: Path) -> None:
    """Document the exclusion that prevents local environments breaking file budgets."""
    fake = ROOT / ".venv" / "lib" / "site-packages" / "generated.py"
    fake.parent.mkdir(parents=True, exist_ok=True)
    fake.write_text("# local artifact\n", encoding="utf-8")
    try:
        assert fake not in source_files()
    finally:
        fake.unlink()
        for parent in [fake.parent, fake.parent.parent, fake.parent.parent.parent, ROOT / ".venv"]:
            try:
                parent.rmdir()
            except OSError:
                pass
