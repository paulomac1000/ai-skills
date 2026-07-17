"""Regression tests for governed Markdown validation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_validator():
    """Load the standalone validator module."""
    path = ROOT / "skills/afds-doc-writer/validate.py"
    spec = importlib.util.spec_from_file_location("validator_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def governed_body(*, verification: str = "Run `pytest`.\n") -> str:
    """Build a valid governed document for focused mutation tests."""
    return f"""---
description: Test document
doc_id: reference.test-document
type: reference
status: active
rigor: normative
owners: [maintainers]
---

# Test document

## Verification

{verification}
"""


def write(path: Path, content: str) -> Path:
    """Write one UTF-8 fixture and return its path."""
    path.write_text(content, encoding="utf-8")
    return path


def messages(findings) -> set[str]:
    """Return only finding messages for readable assertions."""
    return {finding.message for finding in findings}


def test_missing_explicit_input_is_an_error(tmp_path: Path) -> None:
    validator = load_validator()
    paths, findings = validator.collect_files([tmp_path / "missing.md"])
    assert paths == []
    assert messages(findings) == {"input does not exist"}


def test_non_markdown_explicit_input_is_an_error(tmp_path: Path) -> None:
    validator = load_validator()
    target = write(tmp_path / "notes.txt", "text")
    paths, findings = validator.collect_files([target])
    assert paths == []
    assert messages(findings) == {"explicit input is not a Markdown file"}


def test_fenced_headings_and_links_do_not_affect_structure(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + """
```markdown
# Example heading
[missing](not-a-real-file.md)
```
"""
    findings = validator.validate(write(tmp_path / "doc.md", document))
    assert findings == []


def test_longer_closing_fence_is_valid_and_ignored(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + """
````markdown
# Example heading
[missing](not-a-real-file.md)
`````
"""
    assert validator.validate(write(tmp_path / "doc.md", document)) == []


def test_normative_document_requires_concrete_verification(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body(verification="")
    document = document.replace("## Verification\n\n", "## Notes\n\nTests are unavailable.\n")
    assert "missing explicit verification method" in messages(
        validator.validate(write(tmp_path / "doc.md", document))
    )


def test_frontmatter_verification_is_accepted(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body(verification="").replace(
        "owners: [maintainers]\n",
        "owners: [maintainers]\nverification: Run the contract test suite.\n",
    ).replace("## Verification\n\n", "")
    assert validator.validate(write(tmp_path / "doc.md", document)) == []


def test_owners_must_be_a_non_empty_string_list(tmp_path: Path) -> None:
    validator = load_validator()
    for invalid in ("maintainers", "{}", "[]", "[maintainers, 7]"):
        document = governed_body().replace("owners: [maintainers]", f"owners: {invalid}")
        assert "owners must be a non-empty list of role or team names" in messages(
            validator.validate(write(tmp_path / "doc.md", document))
        )


def test_link_with_title_resolves_destination_only(tmp_path: Path) -> None:
    validator = load_validator()
    write(tmp_path / "spec.md", "# Specification\n")
    document = governed_body() + '\n[Specification](spec.md "details")\n'
    assert validator.validate(write(tmp_path / "doc.md", document)) == []


def test_angle_bracket_link_destination_is_supported(tmp_path: Path) -> None:
    validator = load_validator()
    write(tmp_path / "file name.md", "# Named file\n")
    document = governed_body() + "\n[Named file](<file%20name.md> 'details')\n"
    assert validator.validate(write(tmp_path / "doc.md", document)) == []


def test_nested_parentheses_in_link_destination_are_supported(tmp_path: Path) -> None:
    validator = load_validator()
    write(tmp_path / "spec(v2).md", "# Specification\n")
    document = governed_body() + "\n[Specification](spec(v2).md)\n"
    assert validator.validate(write(tmp_path / "doc.md", document)) == []


def test_tab_indented_backticks_do_not_open_a_fence(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + """
	```markdown
# Hidden duplicate heading
[Missing](missing.md)
```
"""
    result = messages(validator.validate(write(tmp_path / "doc.md", document)))
    assert "expected exactly one H1" in result
    assert "broken relative link: missing.md" in result


def test_exclamation_at_end_of_link_label_is_not_an_image(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + "\n[Important!](missing.md)\n"
    assert "broken relative link: missing.md" in messages(
        validator.validate(write(tmp_path / "doc.md", document))
    )


def test_image_destination_is_not_checked_as_a_document_link(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + "\n![Diagram](missing.png)\n"
    assert validator.validate(write(tmp_path / "doc.md", document)) == []


def test_broken_relative_link_is_reported(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + "\n[Missing](missing.md)\n"
    assert "broken relative link: missing.md" in messages(
        validator.validate(write(tmp_path / "doc.md", document))
    )


def test_unhashable_metadata_values_report_findings(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body().replace(
        "type: reference\nstatus: active\nrigor: normative",
        "type: [reference]\nstatus: [active]\nrigor: [normative]",
    )
    result = messages(validator.validate(write(tmp_path / "doc.md", document)))
    assert "invalid type: ['reference']" in result
    assert "invalid status: ['active']" in result
    assert "invalid rigor: ['normative']" in result


def test_inline_code_and_escaped_pseudo_links_are_ignored(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + (
        "\n`[example](missing-inline.md)`\n"
        "\n\\[example](missing-escaped.md)\n"
    )
    assert validator.validate(write(tmp_path / "doc.md", document)) == []


def test_real_link_next_to_inline_code_is_still_checked(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + (
        "\n`[example](ignored.md)` and [real](missing.md)\n"
    )
    assert "broken relative link: missing.md" in messages(
        validator.validate(write(tmp_path / "doc.md", document))
    )
