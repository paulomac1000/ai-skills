"""History-aware release boundary regressions."""

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
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
    assert findings == []


def test_published_section_survives_a_crlf_working_tree(tmp_path: Path) -> None:
    """A checkout that rewrites line endings must not look like a history change."""
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.4.0 - 2026-08-27\n\n- Added release governance.\n\n## 1.3.0 - 2026-08-01\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")
    # The checkout rewrites line endings; the committed content is unchanged.
    (root / "CHANGELOG.md").write_bytes(
        (root / "CHANGELOG.md").read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
    )

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert findings == []


def test_published_section_with_non_ascii_content_is_not_reported_as_modified(tmp_path: Path) -> None:
    """Reading the base revision must not depend on the platform locale."""
    tool = _load_tool()
    root, _ = _repo(tmp_path)
    published = "# Changelog\n\n## 1.3.0 - 2026-08-01\n\n- The published 1.3.0 outcome \u2014 with an em dash.\n"
    (root / "CHANGELOG.md").write_text(published, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "--amend", "-m", "base with non-ascii content")
    base = _git(root, "rev-parse", "HEAD")
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.4.0 - 2026-08-27\n\n- Added release governance.\n\n" + published.split("\n\n", 1)[1],
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert findings == []


def test_crlf_checkout_with_several_published_sections_is_not_reported_as_modified(tmp_path: Path) -> None:
    tool = _load_tool()
    root, _ = _repo(tmp_path)
    published = "## 1.3.0 - 2026-08-01\n\n- The 1.3.0 outcome.\n\n## 1.2.0 - 2026-07-01\n\n- The 1.2.0 outcome.\n"
    (root / "CHANGELOG.md").write_text("# Changelog\n\n" + published, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "--amend", "-m", "base with two published sections")
    base = _git(root, "rev-parse", "HEAD")
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.4.0 - 2026-08-27\n\n- Added release governance.\n\n" + published,
        encoding="utf-8",
    )
    _commit(root, "claim 1.3.0")
    (root / "CHANGELOG.md").write_bytes(
        (root / "CHANGELOG.md").read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
    )

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert findings == []


def test_editing_the_newest_published_section_without_a_new_heading_is_rejected(tmp_path: Path) -> None:
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.3.0 - 2026-08-01\n\n- The published 1.3.0 outcome was rewritten.\n",
        encoding="utf-8",
    )
    _commit(root, "rewrite the newest published section")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert any(item.startswith("PUBLISHED_SECTION_MODIFIED:") for item in findings)


def test_a_correction_for_another_version_does_not_silence_a_change(tmp_path: Path) -> None:
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## 1.4.0 - 2026-08-27\n\n"
        "- Correction: the 1.2.30 section was corrected.\n\n"
        "## 1.3.0 - 2026-08-01\n\n- The published 1.3.0 outcome was rewritten.\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert any(item.startswith("PUBLISHED_SECTION_MODIFIED:") for item in findings)


def test_deleting_a_published_section_is_rejected(tmp_path: Path) -> None:
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.4.0 - 2026-08-27\n\n- Added release governance.\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0 and drop the published section")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert any(item.startswith("PUBLISHED_SECTION_DELETED:") for item in findings)


def test_a_byte_order_mark_does_not_hide_the_first_release_section(tmp_path: Path) -> None:
    tool = _load_tool()
    root, _ = _repo(tmp_path)
    published = "# Changelog\n\n## 1.3.0 - 2026-08-01\n\n- The published 1.3.0 outcome.\n"
    (root / "CHANGELOG.md").write_text(published, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "--amend", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "\ufeff# Changelog\n\n## 1.4.0 - 2026-08-27\n\n- Added release governance.\n\n" + published.split("\n\n", 1)[1],
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0 with a byte-order mark")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert findings == []


def test_a_fenced_example_is_not_a_category_heading(tmp_path: Path) -> None:
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## 1.4.0 - 2026-08-27\n\n"
        "### Added\n\n- Added release governance.\n\n"
        "```markdown\n### Added\n```\n\n"
        "## 1.3.0 - 2026-08-01\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert not [item for item in findings if item.startswith("DUPLICATE_CATEGORY_HEADER:")]


def test_a_fenced_example_cannot_declare_a_correction(tmp_path: Path) -> None:
    """A correction line inside a fenced example must not silence the guard."""
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## 1.4.0 - 2026-08-27\n\n"
        "```text\n"
        "Correction: the 1.3.0 section was corrected.\n"
        "```\n\n"
        "## 1.3.0 - 2026-08-01\n\n- The published 1.3.0 outcome was rewritten.\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert any(item.startswith("PUBLISHED_SECTION_MODIFIED:") for item in findings)


def test_a_fence_closed_with_more_backticks_is_still_an_example(tmp_path: Path) -> None:
    """A closing fence may be longer than the opening one."""
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## 1.4.0 - 2026-08-27\n\n"
        "### Added\n\n- Added release governance.\n\n"
        "```markdown\n### Added\n````\n\n"
        "## 1.3.0 - 2026-08-01\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert not [item for item in findings if item.startswith("DUPLICATE_CATEGORY_HEADER:")]


def test_a_correction_hidden_in_an_html_comment_does_not_silence_the_guard(tmp_path: Path) -> None:
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## 1.4.0 - 2026-08-27\n\n"
        "<!--\n"
        "Correction: the 1.3.0 section was corrected.\n"
        "-->\n\n"
        "## 1.3.0 - 2026-08-01\n\n- The published 1.3.0 outcome was rewritten.\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert any(item.startswith("PUBLISHED_SECTION_MODIFIED:") for item in findings)


def test_a_correction_whose_version_ends_the_sentence_is_accepted(tmp_path: Path) -> None:
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## 1.4.0 - 2026-08-27\n\n"
        "- Correction: the section was corrected in 1.3.0.\n\n"
        "## 1.3.0 - 2026-08-01\n\n- The published 1.3.0 outcome was rewritten.\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert not [item for item in findings if item.startswith("PUBLISHED_SECTION_MODIFIED:")]


def test_a_correction_naming_a_prerelease_does_not_silence_the_release(tmp_path: Path) -> None:
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## 1.4.0 - 2026-08-27\n\n"
        "- Correction: the section was corrected in 1.3.0-rc.1.\n\n"
        "## 1.3.0 - 2026-08-01\n\n- The published 1.3.0 outcome was rewritten.\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert any(item.startswith("PUBLISHED_SECTION_MODIFIED:") for item in findings)


def test_updating_a_global_link_definition_is_not_a_published_section_change(tmp_path: Path) -> None:
    tool = _load_tool()
    root, _ = _repo(tmp_path)
    published = (
        "## 1.3.0 - 2026-08-01\n\n- The published 1.3.0 outcome.\n\n[release-notes]: https://example.invalid/notes\n"
    )
    (root / "CHANGELOG.md").write_text("# Changelog\n\n" + published, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "--amend", "-m", "base with a published section and a link definition")
    base = _git(root, "rev-parse", "HEAD")
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.4.0 - 2026-08-27\n\n- Added release governance.\n\n" + published,
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## 1.4.0 - 2026-08-27\n\n- Added release governance.\n\n"
        "## 1.3.0 - 2026-08-01\n\n- The published 1.3.0 outcome.\n\n"
        "[release-notes]: https://example.invalid/notes-v2\n",
        encoding="utf-8",
    )
    _commit(root, "update the link definition")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert not [item for item in findings if item.startswith("PUBLISHED_SECTION_MODIFIED:")]


def test_repository_changelog_keeps_every_published_section_intact() -> None:
    """The shipped changelog keeps every published section and one category each.

    This is the repository-level counterpart of the immutability rule: a
    published section may not disappear, and a section may not repeat a
    category heading.
    """
    tool = _load_tool()
    root = Path(__file__).resolve().parents[1]
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    sections = tool._release_sections(changelog)
    assert sections, "the changelog must contain release sections"
    for version, section in sections:
        categories = tool._category_headings(section)
        duplicated = sorted({name for name in categories if categories.count(name) > 1})
        assert not duplicated, f"{version} repeats a category heading: {duplicated}"
        assert categories, f"{version} has no category heading"
    versions = [version for version, _ in sections]
    ordered = sorted(versions, key=lambda value: tuple(int(part) for part in value.split(".")), reverse=True)
    assert versions == ordered
    for published in ("3.26.0", "3.27.0", "3.28.0", "3.29.0"):
        assert published in versions, f"the published section of {published} is missing"


def test_a_commented_declaration_or_heading_is_not_operative(tmp_path: Path) -> None:
    """A commented-out declaration must not silence the guard."""
    tool = _load_tool()
    root, base = _repo(tmp_path)
    (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## 1.4.0 - 2026-08-27\n\n"
        "<!-- Correction: the 1.3.0 section was corrected. -->\n"
        "<!-- ### Fixed -->\n\n"
        "## 1.3.0 - 2026-08-01\n\n- The published 1.3.0 outcome was rewritten.\n",
        encoding="utf-8",
    )
    _commit(root, "claim 1.4.0")

    findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
    assert any(item.startswith("PUBLISHED_SECTION_MODIFIED:") for item in findings)


def test_a_declaration_must_name_the_complete_version(tmp_path: Path) -> None:
    """A four-part or build-suffixed identifier is not the published version."""
    tool = _load_tool()
    for declared in ("1.3.0.4", "1.3.0+build", "1.3.0_rc"):
        with tempfile.TemporaryDirectory() as directory:
            root, base = _repo(Path(directory))
            (root / "manifest.yaml").write_text("version: 1.4.0\n", encoding="utf-8")
            (root / "CHANGELOG.md").write_text(
                "# Changelog\n\n"
                "## 1.4.0 - 2026-08-27\n\n"
                f"- Correction: the section was corrected in {declared}.\n\n"
                "## 1.3.0 - 2026-08-01\n\n- The published 1.3.0 outcome was rewritten.\n",
                encoding="utf-8",
            )
            _commit(root, "claim 1.4.0")

            findings = tool.validate_release_branch(root, base, ["manifest.yaml"])
            assert any(item.startswith("PUBLISHED_SECTION_MODIFIED:") for item in findings), declared
