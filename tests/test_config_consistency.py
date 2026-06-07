"""Tests for skills/afds-doc-writer/afds_config.yaml.

Validates that the AFDS configuration:
  - Does NOT contain docs_standards.md in exempt_files
  - Contains all 7 required document types
  - Contains .omo in excluded_dirs
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def afds_config(repo_root):
    import yaml

    config_path = repo_root / "skills" / "afds-doc-writer" / "afds_config.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestExemptFiles:
    """Verify exempt_files does not contain docs_standards.md."""

    def test_docs_standards_not_exempt(self, afds_config):
        """afds_config.yaml must NOT exempt docs_standards.md from validation."""
        exempt = afds_config.get("exempt_files", [])
        assert "docs_standards.md" not in exempt, (
            f"docs_standards.md must NOT be in exempt_files. "
            f"Found exempt_files: {exempt}"
        )


class TestDocumentTypes:
    """Verify afds_config.yaml contains all 7 required document types."""

    REQUIRED_TYPES = {
        "workflow", "ref", "system", "guide",
        "integration", "decision", "contract",
    }

    def test_has_exactly_7_document_types(self, afds_config):
        """afds_config.yaml must define exactly 7 document types."""
        doc_types = set(afds_config.get("types", {}).keys())
        assert doc_types == self.REQUIRED_TYPES, (
            f"Expected exactly 7 document types {self.REQUIRED_TYPES}, "
            f"got {doc_types}"
        )


class TestExcludedDirs:
    """Verify excluded_dirs contains .omo."""

    def test_omo_in_excluded_dirs(self, afds_config):
        """afds_config.yaml must exclude .omo directory."""
        excluded = afds_config.get("excluded_dirs", [])
        assert ".omo" in excluded, (
            f".omo must be in excluded_dirs. Found: {excluded}"
        )
