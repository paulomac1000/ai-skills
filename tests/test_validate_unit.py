"""Unit tests for individual functions in docs_validate.py."""

import pytest
from pathlib import Path

from docs_validate import (
    _extract_all_section_names,
    DEFAULT_CONFIG,
    check_balanced_fences,
    check_mandatory_sections,
    load_markdown_file,
    check_skill_frontmatter,
    check_relative_links,
)
from docs_validate import ValidationResult
from copy import deepcopy


class TestLoadMarkdownFile:
    """Unit tests for load_markdown_file — the off-by-one body parsing fix."""

    def test_simple_frontmatter_and_h1(self, tmp_path):
        """H1 heading is preserved as first line of body."""
        f = tmp_path / "test.md"
        f.write_text("---\na: b\n---\n# Hello World\nBody content")
        fm, body = load_markdown_file(f)
        assert fm is not None
        assert fm == {"a": "b"}
        assert "# Hello World" in body
        assert body.strip().startswith("# Hello World")

    def test_empty_frontmatter(self, tmp_path):
        """Empty frontmatter returns None (yaml.safe_load('') -> None)."""
        f = tmp_path / "test.md"
        f.write_text("---\n---\n# Title\nBody")
        fm, body = load_markdown_file(f)
        assert fm is None
        assert "# Title" in body

    def test_frontmatter_with_dashes_in_value(self, tmp_path):
        """Triple dashes inside a quoted YAML string do not break parsing."""
        f = tmp_path / "test.md"
        f.write_text('---\ndesc: "foo---bar"\n---\n# Title\nBody')
        fm, body = load_markdown_file(f)
        assert fm is not None
        assert fm["desc"] == "foo---bar"
        assert "# Title" in body

    def test_multiline_frontmatter_value(self, tmp_path):
        """Multi-line YAML values don't break body extraction."""
        f = tmp_path / "test.md"
        f.write_text("---\ndesc: |\n  line1\n  line2\n---\n# Title\nBody")
        fm, body = load_markdown_file(f)
        assert fm is not None
        assert fm["desc"] == "line1\nline2"  # YAML block scalar strips trailing newline
        assert "# Title" in body

    def test_no_frontmatter_returns_empty_dict(self, tmp_path):
        """File without any frontmatter returns empty dict and full content."""
        f = tmp_path / "test.md"
        f.write_text("# Just a heading\nContent")
        fm, body = load_markdown_file(f)
        assert fm == {}
        assert body == "# Just a heading\nContent"

    def test_unclosed_frontmatter_returns_none(self, tmp_path):
        """Missing closing --- returns None frontmatter and an error string."""
        f = tmp_path / "test.md"
        f.write_text("---\na: b\n")
        fm, body = load_markdown_file(f)
        assert fm is None
        assert isinstance(body, str)
        assert "Invalid" in body or "missing" in body.lower()

    def test_body_no_extra_newline_eaten(self, tmp_path):
        """The off-by-one fix means first character of H1 is NOT eaten."""
        f = tmp_path / "test.md"
        f.write_text("---\na: b\n---\n# Title\nContent")
        fm, body = load_markdown_file(f)
        assert body.lstrip().startswith("# Title")


class TestExtractAllSectionNames:
    """Unit tests for _extract_all_section_names — space-to-underscore normalization."""

    def test_edge_cases_with_space_normalized(self):
        """## Edge Cases becomes EDGE_CASES (space -> underscore)."""
        body = "## Edge Cases\ncontent\n## FAILURE MODES\ncontent"
        names = _extract_all_section_names(body)
        assert "EDGE_CASES" in names
        assert "FAILURE_MODES" in names
        assert "EDGE CASES" not in names

    def test_section_already_with_underscore(self):
        """## EDGE_CASES stays EDGE_CASES."""
        body = "## EDGE_CASES\ncontent"
        names = _extract_all_section_names(body)
        assert "EDGE_CASES" in names
        assert len(names) == 1

    def test_section_in_code_block_is_excluded(self):
        """## inside a ``` block is NOT treated as a section marker."""
        body = "```python\n## IGNORED_SECTION\n```\n\n## REAL_SECTION\n"
        names = _extract_all_section_names(body)
        assert "IGNORED_SECTION" not in names
        assert "REAL_SECTION" in names

    def test_section_inside_inline_code_not_excluded(self):
        """Inline backticks do NOT prevent section detection (only fenced blocks are blanked)."""
        body = "`## NOT_REAL` but this is:\n## REAL_SECTION\ncontent"
        names = _extract_all_section_names(body)
        assert "REAL_SECTION" in names


class TestCheckBalancedFences:
    """Unit tests for check_balanced_fences -- unbalanced ``` detection."""

    def test_balanced_fences_no_warning(self):
        """Even number of ``` markers -> no warning generated."""
        result = ValidationResult(file_path="test.md")
        body = "```python\ncode\n```\n\n## Section\n\n```bash\ncmd\n```"
        config = deepcopy(DEFAULT_CONFIG)
        check_balanced_fences(result, {}, body, Path("test.md"), config)
        assert len(result.warnings) == 0

    def test_unbalanced_fences_emits_warning(self):
        """Odd number of ``` markers -> exactly one warning."""
        result = ValidationResult(file_path="test.md")
        body = "```python\ncode\n```\n\n```\n## Section"
        config = deepcopy(DEFAULT_CONFIG)
        check_balanced_fences(result, {}, body, Path("test.md"), config)
        assert len(result.warnings) == 1
        assert "Unbalanced code fences" in result.warnings[0]
        assert "3" in result.warnings[0]

    def test_no_fences_no_warning(self):
        """No ``` markers at all -> no warning."""
        result = ValidationResult(file_path="test.md")
        body = "## Section\nSome content\n# Title"
        config = deepcopy(DEFAULT_CONFIG)
        check_balanced_fences(result, {}, body, Path("test.md"), config)
        assert len(result.warnings) == 0

    def test_single_fence_marker(self):
        """Just one ``` marker -> warning."""
        result = ValidationResult(file_path="test.md")
        body = "## Section\n```\n"
        config = deepcopy(DEFAULT_CONFIG)
        check_balanced_fences(result, {}, body, Path("test.md"), config)
        assert len(result.warnings) == 1
        assert "1" in result.warnings[0]


class TestCheckMandatorySectionsErrorFormat:
    """Unit tests for check_mandatory_sections -- improved error messages."""

    def test_error_message_shows_expected_found_missing(self):
        """Error shows what was expected, what was found, and what is missing."""
        result = ValidationResult(file_path="test.md")
        fm = {"type": "ref", "doc_id": "ref.test"}
        body = "## PURPOSE\nN/A\n\n## SCOPE\nN/A\n"
        config = deepcopy(DEFAULT_CONFIG)
        check_mandatory_sections(result, fm, body, Path("test.md"), config)
        assert not result.passed
        error_msg = result.errors[0]
        assert "expected" in error_msg
        assert "found" in error_msg
        assert "missing" in error_msg
        assert "DEFINITIONS" in error_msg

    def test_all_sections_present_no_error(self):
        """When all required sections exist, no error is raised."""
        result = ValidationResult(file_path="test.md")
        fm = {"type": "ref", "doc_id": "ref.test"}
        body = (
            "## PURPOSE\nN/A\n\n"
            "## SCOPE\nN/A\n\n"
            "## DEFINITIONS\nN/A\n\n"
            "## RULES\nN/A\n\n"
            "## INTERFACES\nN/A\n\n"
            "## STATE\nN/A\n\n"
            "## EDGE_CASES\nN/A\n\n"
            "## EXAMPLES\nN/A\n\n"
            "## NON_GOALS\nN/A\n"
        )
        config = deepcopy(DEFAULT_CONFIG)
        check_mandatory_sections(result, fm, body, Path("test.md"), config)
        assert result.passed
        assert len(result.errors) == 0

    def test_space_named_section_detected(self):
        """## Edge Cases (with space) is detected as EDGE_CASES (underscore)."""
        result = ValidationResult(file_path="test.md")
        fm = {"type": "ref", "doc_id": "ref.test"}
        body = (
            "## PURPOSE\nN/A\n\n"
            "## SCOPE\nN/A\n\n"
            "## DEFINITIONS\nN/A\n\n"
            "## RULES\nN/A\n\n"
            "## INTERFACES\nN/A\n\n"
            "## STATE\nN/A\n\n"
            "## Edge Cases\nN/A\n\n"
            "## EXAMPLES\nN/A\n\n"
            "## NON_GOALS\nN/A\n"
        )
        config = deepcopy(DEFAULT_CONFIG)
        check_mandatory_sections(result, fm, body, Path("test.md"), config)
        assert result.passed
        assert len(result.errors) == 0


class TestCheckSkillFrontmatter:
    """Unit tests for check_skill_frontmatter."""

    def test_non_skill_file_ignored(self):
        result = ValidationResult(file_path="other.md")
        check_skill_frontmatter(result, None, "", Path("other.md"), {})
        assert result.passed

    def test_missing_frontmatter(self):
        result = ValidationResult(file_path="skill.md")
        check_skill_frontmatter(result, None, "", Path("skill.md"), {})
        assert result.passed  # check_frontmatter_present handles None, we return early

    def test_empty_frontmatter(self):
        result = ValidationResult(file_path="skill.md")
        check_skill_frontmatter(result, {}, "", Path("skill.md"), {})
        assert not result.passed
        assert "empty" in result.errors[0]

    def test_missing_name_or_description(self):
        result = ValidationResult(file_path="skill.md")
        check_skill_frontmatter(result, {"name": "Test"}, "", Path("skill.md"), {})
        assert not result.passed
        assert "Missing required field: description" in result.errors[0]

    def test_valid_frontmatter(self):
        result = ValidationResult(file_path="SKILL.md")
        check_skill_frontmatter(result, {"name": "Test", "description": "Desc"}, "", Path("SKILL.md"), {})
        assert result.passed


class TestCheckRelativeLinks:
    """Unit tests for check_relative_links."""

    def test_disabled_by_default(self):
        result = ValidationResult(file_path="test.md")
        body = "[broken link](nonexistent.md)"
        check_relative_links(result, {}, body, Path("test.md"), {"_check_links": False})
        assert len(result.warnings) == 0

    def test_remote_links_ignored(self):
        result = ValidationResult(file_path="test.md")
        body = "[remote](https://google.com) [anchor](#anchor) [mail](mailto:test@example.com)"
        check_relative_links(result, {}, body, Path("test.md"), {"_check_links": True})
        assert len(result.warnings) == 0

    def test_valid_link_passes(self, tmp_path):
        doc = tmp_path / "doc.md"
        target = tmp_path / "target.md"
        target.write_text("hello")
        result = ValidationResult(file_path=str(doc))
        body = "[valid link](target.md)"
        check_relative_links(result, {}, body, doc, {"_check_links": True})
        assert len(result.warnings) == 0

    def test_broken_link_warns(self, tmp_path):
        doc = tmp_path / "doc.md"
        result = ValidationResult(file_path=str(doc))
        body = "[broken link](nonexistent.md)"
        check_relative_links(result, {}, body, doc, {"_check_links": True})
        assert len(result.warnings) == 1
        assert "nonexistent.md" in result.warnings[0]

    def test_bare_path_backticks(self, tmp_path):
        doc = tmp_path / "doc.md"
        result = ValidationResult(file_path=str(doc))
        body = "Refer to `../docs/nonexistent.md` for details"
        check_relative_links(result, {}, body, doc, {"_check_links": True})
        assert len(result.warnings) == 1
        assert "nonexistent.md" in result.warnings[0]
