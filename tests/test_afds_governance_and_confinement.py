"""AFDS governance, confinement, and anchor regression tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_validator():
    path = ROOT / "skills/afds-doc-writer/validate.py"
    spec = importlib.util.spec_from_file_location("afds_hardening_validator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def governed(rigor: str = "normative", verification: str = "Run tests.") -> str:
    return f"""---
description: Test document
doc_id: reference.test-document
type: reference
status: active
rigor: {rigor}
owners: [maintainers]
---

# Test document

## Verification

{verification}
"""


def write(path: Path, value: str) -> Path:
    path.write_text(value, encoding="utf-8")
    return path


def messages(findings) -> list[str]:
    return [finding.message for finding in findings]


def test_readme_is_not_globally_exempt_without_governance(tmp_path: Path) -> None:
    validator = load_validator()
    path = write(tmp_path / "README.md", "# Readme\n[bad](missing.md)\n")
    assert "missing YAML frontmatter" in messages(validator.validate(path))


def test_human_facing_profile_still_checks_links(tmp_path: Path) -> None:
    validator = load_validator()
    path = write(tmp_path / "README.md", "# Readme\n[bad](missing.md)\n")
    findings = validator.validate(
        path,
        profile=validator.DEFAULT_PROFILES["human-facing"],
    )
    assert "broken relative link: missing.md" in messages(findings)


def test_missing_relative_anchor_is_rejected(tmp_path: Path) -> None:
    validator = load_validator()
    write(tmp_path / "target.md", "# Target\n\n## Present\n")
    source = write(
        tmp_path / "doc.md",
        governed() + "\n[Missing](target.md#not-present)\n",
    )
    assert "broken relative anchor: target.md#not-present" in messages(
        validator.validate(source)
    )


def test_relative_link_cannot_escape_repository(tmp_path: Path) -> None:
    validator = load_validator()
    repository = tmp_path / "repo"
    repository.mkdir()
    write(tmp_path / "outside.md", "# Outside\n")
    source = write(
        repository / "doc.md",
        governed() + "\n[Outside](../outside.md)\n",
    )
    findings = messages(validator.validate(source, repository))
    assert any(
        message.startswith("unsafe relative link: ../outside.md")
        for message in findings
    )


def test_relative_link_rejects_symlink_target(tmp_path: Path) -> None:
    validator = load_validator()
    target = write(tmp_path / "target.md", "# Target\n")
    link = tmp_path / "link.md"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    source = write(tmp_path / "doc.md", governed() + "\n[Target](link.md)\n")
    findings = messages(validator.validate(source))
    assert any(
        message.startswith("unsafe relative link: link.md") for message in findings
    )


def test_informative_document_does_not_require_verification(tmp_path: Path) -> None:
    validator = load_validator()
    document = governed(rigor="informative", verification="").replace(
        "## Verification\n\n\n",
        "",
    )
    assert validator.validate(write(tmp_path / "doc.md", document)) == []


def test_governance_profile_rejects_unknown_or_missing_options(tmp_path: Path) -> None:
    validator = load_validator()
    governance = tmp_path / "governance.yaml"
    governance.write_text(
        """schema_version: 1
default_profile: governed
profiles:
  governed:
    require_frontmatter: true
    check_structure: true
    check_links: true
    check_anchors: true
    typo_option: true
documents: []
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="declare exactly"):
        validator._load_governance(governance)


def test_relative_link_rejects_backslash_ambiguity(tmp_path: Path) -> None:
    validator = load_validator()
    write(tmp_path / "target.md", "# Target\n")
    source = write(tmp_path / "doc.md", governed() + "\n[Target](sub\\\\target.md)\n")
    findings = messages(validator.validate(source))
    assert any("POSIX separators" in message for message in findings)


def test_source_path_with_parent_component_is_rejected(tmp_path: Path) -> None:
    validator = load_validator()
    repository = tmp_path / "repo"
    repository.mkdir()
    source = write(repository / "doc.md", governed())
    ambiguous = repository / "nested" / ".." / source.name
    findings = messages(validator.validate(ambiguous, repository))
    assert "document path must remain inside repository root" in findings
