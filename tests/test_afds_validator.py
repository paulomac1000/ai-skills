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


def test_missing_and_non_markdown_inputs_are_errors(tmp_path: Path) -> None:
    validator = load_validator()
    paths, findings = validator.collect_files([tmp_path / "missing.md"])
    assert paths == []
    assert messages(findings) == {"input does not exist"}
    target = write(tmp_path / "notes.txt", "text")
    paths, findings = validator.collect_files([target])
    assert paths == []
    assert messages(findings) == {"explicit input is not a Markdown file"}


def test_fenced_headings_and_links_do_not_affect_structure(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + """
````markdown
# Example heading
[missing](not-a-real-file.md)
`````
"""
    assert validator.validate(write(tmp_path / "doc.md", document)) == []


def test_tab_indented_backticks_do_not_open_a_fence(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + """
\t```markdown
# Hidden duplicate heading
[Missing](missing.md)
```
"""
    result = messages(validator.validate(write(tmp_path / "doc.md", document)))
    assert "expected exactly one H1" in result
    assert "broken relative link: missing.md" in result


def test_normative_document_requires_concrete_verification(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body(verification="").replace(
        "## Verification\n\n", "## Notes\n\nTests are unavailable.\n"
    )
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


def test_metadata_types_are_validated_without_crashing(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body().replace(
        "description: Test document\n",
        "description: [test]\n",
    ).replace(
        "type: reference\nstatus: active\nrigor: normative",
        "type: [reference]\nstatus: [active]\nrigor: [normative]",
    ).replace("owners: [maintainers]", "owners: [maintainers, 7]")
    result = messages(validator.validate(write(tmp_path / "doc.md", document)))
    assert "description must be a non-empty string" in result
    assert "owners must be a non-empty list of role or team names" in result
    assert "invalid type: ['reference']" in result
    assert "invalid status: ['active']" in result
    assert "invalid rigor: ['normative']" in result


def test_inline_link_variants_are_validated(tmp_path: Path) -> None:
    validator = load_validator()
    write(tmp_path / "spec.md", "# Specification\n")
    write(tmp_path / "file name.md", "# Named file\n")
    write(tmp_path / "spec(v2).md", "# Specification\n")
    document = governed_body() + (
        '\n[Specification](spec.md "details")\n'
        "\n[Named file](<file%20name.md> 'details')\n"
        "\n[Specification v2](spec(v2).md)\n"
    )
    assert validator.validate(write(tmp_path / "doc.md", document)) == []


def test_reference_style_links_are_validated_once(tmp_path: Path) -> None:
    validator = load_validator()
    broken = governed_body() + "\n[Guide][spec]\n\n[spec]: missing.md \"details\"\n"
    findings = validator.validate(write(tmp_path / "doc.md", broken))
    assert [finding.message for finding in findings].count("broken relative link: missing.md") == 1

    write(tmp_path / "guide.md", "# Guide\n")
    valid = governed_body() + "\n[Guide][]\n\n[guide]: guide.md\n"
    assert validator.validate(write(tmp_path / "doc.md", valid)) == []


def test_full_reference_images_are_ignored(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + "\n![Guide][spec]\n\n[spec]: missing.png\n"
    assert validator.validate(write(tmp_path / "doc.md", document)) == []


def test_shortcut_reference_links_are_validated(tmp_path: Path) -> None:
    validator = load_validator()
    broken = governed_body() + "\n[Guide]\n\n[guide]: missing.md \"details\"\n"
    assert "broken relative link: missing.md" in messages(
        validator.validate(write(tmp_path / "doc.md", broken))
    )
    write(tmp_path / "guide.md", "# Guide\n")
    valid = governed_body() + "\n[Guide]\n\n[guide]: guide.md\n"
    assert validator.validate(write(tmp_path / "doc.md", valid)) == []


def test_unused_reference_definition_is_not_treated_as_a_link(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + "\n[unused]: missing.md\n"
    assert validator.validate(write(tmp_path / "doc.md", document)) == []


def test_shortcut_images_code_and_escaped_labels_are_ignored(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + (
        "\n![Guide]\n"
        "\n`[Guide]`\n"
        "\n\\[Guide]\n"
        "\n[guide]: missing.md\n"
    )
    assert validator.validate(write(tmp_path / "doc.md", document)) == []


def test_images_code_and_escaped_pseudo_links_are_ignored(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + (
        "\n![Diagram](missing.png)\n"
        "\n`[example](missing-inline.md)`\n"
        "\n\\[example](missing-escaped.md)\n"
    )
    assert validator.validate(write(tmp_path / "doc.md", document)) == []


def test_backslash_does_not_escape_code_span_closer(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + "\n`code\\` [Missing](missing.md)\n"
    result = messages(validator.validate(write(tmp_path / "doc.md", document)))
    assert "broken relative link: missing.md" in result


def test_exclamation_at_end_of_link_label_is_not_an_image(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed_body() + "\n[Important!](missing.md)\n"
    assert "broken relative link: missing.md" in messages(
        validator.validate(write(tmp_path / "doc.md", document))
    )
