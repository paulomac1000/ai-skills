"""History-aware release boundary regressions."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/changelog-release-architect/tools/check_release_branch.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("release_branch_test_target", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


def _commit(root: Path, message: str) -> None:
    _git(root, "add", ".")
    _git(root, "commit", "-m", message)


def _repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "release-test@example.invalid")
    _git(root, "config", "user.name", "Release Test")
    (root / "manifest.yaml").write_text("version: 1.3.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text("# Changelog\n\n## 1.3.0 - 2026-08-01\n", encoding="utf-8")
    _commit(root, "base")
    return root, _git(root, "rev-parse", "HEAD")


def test_single_claimed_version_can_receive_followup_commits(tmp_path: Path) -> None:
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.4.0 - 2026-08-27\n\n- Added release governance.\n\n## 1.3.0 - 2026-08-01\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")
    (root / "notes.txt").write_text("review fix\n", encoding="utf-8")
    _commit(root, "review fix")

    assert tool.validate_release_branch(root, base, ["manifest.yaml"]) == []


def test_second_version_bump_in_same_branch_is_rejected(tmp_path: Path) -> None:
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.4.0 - 2026-08-27\n\n## 1.3.0 - 2026-08-01\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")
    (root / "manifest.yaml").write_text("version: 1.5.0\n", encoding="utf-8")
    _commit(root, "incorrect second bump")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert any(item.startswith("MULTIPLE_VERSION_TRANSITIONS:") for item in findings)


def test_multiple_release_headings_are_rejected(tmp_path: Path) -> None:
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.5.0 - 2026-08-28\n\n## 1.4.0 - 2026-08-27\n\n## 1.3.0 - 2026-08-01\n",
        encoding="utf-8",
    )
    _commit(root, "two headings")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert any(item.startswith("MULTIPLE_RELEASE_HEADINGS:") for item in findings)


def test_duplicate_category_header_in_one_release_is_rejected(tmp_path: Path) -> None:
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## 1.4.0 - 2026-08-27\n\n"
        "### Fixed\n\n- first outcome.\n\n"
        "### Fixed\n\n- second outcome.\n\n"
        "## 1.3.0 - 2026-08-01\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert any(item.startswith("DUPLICATE_CATEGORY_HEADER:") for item in findings)


def test_changed_published_section_is_rejected_without_a_declared_correction(tmp_path: Path) -> None:
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## 1.4.0 - 2026-08-27\n\n- Added release governance.\n\n"
        "## 1.3.0 - 2026-08-01\n\n- The published 1.3.0 outcome was rewritten.\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert any(item.startswith("PUBLISHED_SECTION_MODIFIED:") for item in findings)


def test_declared_correction_allows_a_changed_published_section(tmp_path: Path) -> None:
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## 1.4.0 - 2026-08-27\n\n"
        "- Added release governance.\n"
        "- Correction: the 1.3.0 section repeated a category heading and was corrected.\n\n"
        "## 1.3.0 - 2026-08-01\n\n- The published 1.3.0 outcome was rewritten.\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert not [item for item in findings if item.startswith("PUBLISHED_SECTION_MODIFIED:")]
    assert not [item for item in findings if item.startswith("DUPLICATE_CATEGORY_HEADER:")]
