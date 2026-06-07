"""Tests for .github/workflows/ci.yml.

Validates that the CI workflow file:
  - Is valid YAML
  - Uses Python 3.14
  - Has SHA-pinned actions (not floating version tags)
  - Has no broken file references
"""

import re
import yaml
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def ci_path(repo_root):
    return repo_root / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="session")
def ci_content(ci_path):
    return ci_path.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def ci_yaml(ci_path):
    with open(ci_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestCIWorkflowYAML:
    """Verify ci.yml is valid YAML with expected structure."""

    def test_parseable_yaml(self, ci_yaml):
        """ci.yml must be valid YAML."""
        assert isinstance(ci_yaml, dict), "ci.yml did not parse as a YAML object"

    def test_has_expected_top_level_keys(self, ci_content):
        """ci.yml must have name, on, and jobs keys (raw content check —
           PyYAML parses 'on' as boolean True, so we regex the source)."""
        import re
        for key in ("name", "on", "jobs"):
            pattern = re.compile(rf"^{key}:\s", re.MULTILINE)
            assert pattern.search(ci_content), f"Missing top-level key: {key}"


class TestPythonVersion:
    """Verify ci.yml uses Python 3.14."""

    def test_uses_python_314(self, ci_content):
        """ci.yml must specify Python 3.14."""
        assert '"3.14"' in ci_content or "'3.14'" in ci_content, (
            "CI workflow must use Python 3.14"
        )


class TestActionPinning:
    """Verify all GitHub Actions uses are SHA-pinned."""

    def test_actions_are_sha_pinned(self, ci_content):
        """Every `uses:` line must reference actions by full commit SHA, not just version tags."""
        uses_lines = re.findall(r"uses:\s+([^\s#]+)", ci_content)
        assert len(uses_lines) > 0, "No uses: lines found in ci.yml"

        sha_pattern = re.compile(r"^[^@]+@[0-9a-f]{40}$")
        for line in uses_lines:
            assert sha_pattern.match(line), (
                f"Action not SHA-pinned (must be owner/repo@<40-char-hex>): {line}"
            )


class TestNoBrokenReferences:
    """Verify ci.yml doesn't reference non-existent files."""

    def test_no_broken_file_references(self, ci_content):
        """ci.yml must not reference mcp_standards.md or templates/docs-template.md."""
        assert "mcp_standards.md" not in ci_content, (
            "ci.yml references mcp_standards.md which does not exist"
        )
        assert "templates/docs-template.md" not in ci_content, (
            "ci.yml references templates/docs-template.md which does not exist"
        )
